from datetime import datetime
from typing import Dict, Any

class Event:
    def __init__(self, event_dict: Dict[str, Any]) -> None:
        # Initialize the event with data from a dictionary
        self.id = event_dict.get('id')
        self.summary = event_dict.get('summary', '')
        self.location = event_dict.get('location')
        self.description = event_dict.get('description', '')
        self.time_zone = "Pacific/Auckland"  # Default timezone
        
        # Handle start time
        start = event_dict.get('start', {})
        if isinstance(start, dict):
            self.start_str = start.get('dateTime')
            if 'timeZone' in start:
                self.time_zone = start.get('timeZone')
        else:
            self.start_str = start
            
        # Handle end time
        end = event_dict.get('end', {})
        if isinstance(end, dict):
            self.end_str = end.get('dateTime')
        else:
            self.end_str = end
            
        # Parse datetime objects
        self.start_time = self._parse_datetime(self.start_str)
        self.end_time = self._parse_datetime(self.end_str)
        
    def _parse_datetime(self, datetime_str):
        """Parse an ISO format datetime string."""
        if not datetime_str:
            return None
        try:
            return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None
            
    def __str__(self):
        """String representation of the event."""
        return f"Event({self.summary}, {self.start_time}, {self.location})"
    
    def __repr__(self):
        """Representation of the event."""
        return self.__str__()
