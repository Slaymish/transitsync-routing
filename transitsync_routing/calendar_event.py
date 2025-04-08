from datetime import datetime

class CalendarEvent:
    def __init__(self, summary, location, start_time=None, end_time=None, description=""):
        self.summary = summary
        self.location = location
        self.start_time = start_time  # datetime object
        self.end_time = end_time      # datetime object
        self.description = description