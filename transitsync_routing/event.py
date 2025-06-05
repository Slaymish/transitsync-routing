from datetime import datetime, timedelta
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
            
    def to_dict(self) -> Dict[str, Any]:
        """Convert the event to a dictionary format for API calls"""
        event_dict = {
            "summary": self.summary if self.summary else "Untitled Event",
        }
        
        # Handle start time
        if self.start_time:
            event_dict["start"] = {
                "dateTime": self.start_time.isoformat(),
                "timeZone": self.time_zone,
            }
        elif self.start_str:
            # Use original string if available
            if 'T' in self.start_str:  # Contains time component
                event_dict["start"] = {
                    "dateTime": self.start_str,
                    "timeZone": self.time_zone,
                }
            else:  # Date only
                event_dict["start"] = {
                    "date": self.start_str,
                    "timeZone": self.time_zone,
                }
                
        # Handle end time
        if self.end_time:
            event_dict["end"] = {
                "dateTime": self.end_time.isoformat(),
                "timeZone": self.time_zone,
            }
        elif self.end_str:
            # Use original string if available
            if 'T' in self.end_str:  # Contains time component
                event_dict["end"] = {
                    "dateTime": self.end_str,
                    "timeZone": self.time_zone,
                }
            else:  # Date only
                event_dict["end"] = {
                    "date": self.end_str,
                    "timeZone": self.time_zone,
                }
        elif self.start_time:
            # Default to start_time + 1 hour if no end time is specified
            event_dict["end"] = {
                "dateTime": (self.start_time + timedelta(hours=1)).isoformat(),
                "timeZone": self.time_zone,
            }
        
        # Add location and description if available
        if self.location:
            event_dict["location"] = self.location
            
        if self.description:
            event_dict["description"] = self.description
            
        # Add ID if available (needed for updates)
        if self.id:
            event_dict["id"] = self.id
            
        return event_dict
            
    def __str__(self):
        """String representation of the event."""
        return f"Event({self.summary}, {self.start_time}, {self.location})"
    
    def __repr__(self):
        """Representation of the event."""
        return self.__str__()
