from datetime import datetime
from typing import Dict, Any

class Event:
    def __init__(self, event_dict: Dict[str, Any]) -> None:
        # Initialize the event with data from a dictionary
        self.id = None
        self.summary = ""
        self.location = None
        self.description = ""
        self.start_str = None
        self.end_str = None
        self.time_zone = "UTC"
        self.start_time = None
        self.end_time = None
