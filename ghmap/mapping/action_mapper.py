import json
import re
from datetime import datetime, timezone
from typing import Dict, Any


class ActionMapper:
    """
    A class to map GitHub events to high-level actions based on predefined event types and conditions.

    Attributes:
        action_mapping (Dict): Predefined mapping of actions and event rules.
    """

    def __init__(self, action_mapping: Dict):
        self.action_mapping = action_mapping

    @staticmethod
    def _deserialize_payload(event_record: Dict) -> Dict:
        """
        Deserializes the 'payload' field of the event record if it's a string.
        """
        event_record['payload'] = json.loads(event_record['payload'])
        return event_record

    @staticmethod
    def _convert_date_to_iso(event_record: Dict) -> Dict:
        """
        Converts 'created_at' field from Unix timestamp to ISO 8601 format.
        """
        event_record['created_at'] = datetime.fromtimestamp(event_record['created_at'] / 1000, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        return event_record

    @staticmethod
    def _match_condition(event_value: Any, mapping_value: Any) -> bool:
        """
        Matches an event value against a mapping value, supporting regex and nested matching.
        """
        if isinstance(mapping_value, dict):
            return all(ActionMapper._match_condition(event_value.get(k), v) for k, v in mapping_value.items() if k in event_value)

        if isinstance(mapping_value, list):
            return all(ActionMapper._match_condition(ev, mv) for ev, mv in zip(event_value, mapping_value)) if event_value else False

        if isinstance(mapping_value, str) and mapping_value.startswith('^') and mapping_value.endswith('$'):
            return bool(re.match(mapping_value, event_value))

        return event_value == mapping_value

    def _extract_attributes(self, event_record: Dict, action_details: Dict, action_name: str) -> Dict:
        """
        Extracts attributes and common fields from the event record.
        """
        mapped_action = {'action': action_name}

        if action_details['attributes'].get('include_common_fields'):
            mapped_action.update(self._extract_fields(event_record, self.action_mapping['common_fields']))

        mapped_action['details'] = self._extract_fields(event_record, action_details['attributes'].get('details', {}))

        return mapped_action

    def _extract_fields(self, event_record: Dict, field_mapping: Dict) -> Dict:
        """
        Extracts values based on the provided mapping, handling nested dictionaries and lists.
        """
        extracted_data = {}

        for field_key, mapping_value in field_mapping.items():
            if isinstance(mapping_value, dict):
                extracted_data[field_key] = self._extract_fields(event_record, mapping_value)
            elif isinstance(mapping_value, list):
                extracted_data[field_key] = self._extract_list(event_record, mapping_value)
            else:
                extracted_data[field_key] = self._extract_field(event_record, mapping_value)

        return extracted_data

    def _extract_list(self, event_record: Dict, list_mapping: list) -> list:
        """
        Handles extracting lists of values from the event record.
        """
        base_list = self._extract_field(event_record, list_mapping[0][list(list_mapping[0].keys())[0]].split('.')[0:-1])
        if not isinstance(base_list, list):
            return []

        return [{key: item.get(path.split('.')[-1], None) for key, path in list_mapping[0].items()} for item in base_list]

    @staticmethod
    def _extract_field(event_record: Dict, field_path: str) -> Any:
        """
        Extracts a value from the event record using a dotted field path.
        """
        keys = field_path.split('.') if isinstance(field_path, str) else field_path
        value = event_record
        for key in keys:
            if isinstance(value, list):
                return value
            value = value.get(key)
            if value is None:
                return None

        return value

    def map(self, event_record: Dict) -> Dict:
        """
        Maps an event to a high-level action based on event type and attributes.
        """
        event_record = self._deserialize_payload(event_record)
        event_record = self._convert_date_to_iso(event_record)
        event_type = event_record.get('type')

        for action_name, action_details in self.action_mapping['actions'].items():
            if event_type == action_details['event']['type'] and \
                    all(self._match_condition(self._extract_field(event_record, k), v)
                        for k, v in action_details['event'].items() if k != 'type'):
                return self._extract_attributes(event_record, action_details, action_name)

        return self._extract_attributes(event_record, self.action_mapping['actions']['UnknownAction'], 'UnknownAction')