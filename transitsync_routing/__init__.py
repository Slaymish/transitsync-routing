"""
TransitSync Routing

This module provides public transit route planning logic for Wellington, NZ.
Includes GTFS integration, geocoding, and prediction-based trip estimation.

To use, create a list of CalendarEvent-like objects and pass them to RoutePlanner.

Example:
    from transitsync_routing.route_planner import RoutePlanner
    from transitsync_routing.calendar_event import CalendarEvent

    events = [
        CalendarEvent("Math Lecture", "Kelburn Campus", start_time=..., end_time=...),
        CalendarEvent("Wellington Zoo", "Wellington Zoo", start_time=..., end_time=...)
    ]

    planner = RoutePlanner(events)
    transit_plans = planner.process_events()
"""

from .route_planner import RoutePlanner
from .event import Event
from .stop import Stop