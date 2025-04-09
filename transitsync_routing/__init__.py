"""
TransitSync Routing

This module provides public transit route planning logic for Wellington, NZ.
Includes GTFS integration, geocoding, and prediction-based trip estimation.

To use, create a list of CalendarEvent-like objects and pass them to RoutePlanner.

Example:
    from transitsync_routing.route_planner import RoutePlanner
    from transitsync_routing.event import Event

    events = [
        Event("Math Lecture", "Kelburn Campus", start_time=..., end_time=...),
        Event("Wellington Zoo", "Wellington Zoo", start_time=..., end_time=...)
    ]

    planner = RoutePlanner(events)
    # You can optionally provide a home_address parameter
    transit_plans = planner.process_events(home_address="123 Main St, Wellington, NZ")
"""

from .route_planner import RoutePlanner
from .event import Event
from .stop import Stop

# Ensure the RoutePlanner class is available at the package level
__all__ = ['RoutePlanner', 'Event', 'Stop']