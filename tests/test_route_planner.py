import datetime
from unittest.mock import patch, MagicMock

from transitsync_routing.event import Event
from transitsync_routing.route_planner import RoutePlanner


def make_event(summary, location, start):
    return Event({
        "summary": summary,
        "location": location,
        "start": {"dateTime": start.isoformat(), "timeZone": "Pacific/Auckland"},
        "end": {"dateTime": (start + datetime.timedelta(hours=1)).isoformat(), "timeZone": "Pacific/Auckland"},
    })


def test_is_suitable_event_filters():
    planner = RoutePlanner([])
    # event with no location
    e1 = make_event("A", "", datetime.datetime.now())
    assert not planner.is_suitable_event(e1)
    # event with online location
    e2 = make_event("B", "Online meeting", datetime.datetime.now())
    assert not planner.is_suitable_event(e2)


def test_plan_route_between_events():
    e1 = make_event("Start", "Loc1", datetime.datetime(2025,1,1,9,0))
    e2 = make_event("End", "Loc2", datetime.datetime(2025,1,1,10,0))

    planner = RoutePlanner([e1, e2])

    with patch.object(planner.api_client, 'geocode_address', side_effect=[(1,2),(3,4)]), \
         patch.object(planner.api_client, 'query_otp_graphql') as mock_query:
        mock_query.return_value = {
            "data": {
                "plan": {
                    "itineraries": [
                        {
                            "duration": 600,
                            "legs": [
                                {
                                    "mode": "WALK",
                                    "startTime": 1600000000000,
                                    "endTime": 1600000300000,
                                    "from": {"name": "A"},
                                    "to": {"name": "B"},
                                    "distance": 1000
                                }
                            ]
                        }
                    ]
                }
            }
        }
        route = planner.plan_route_between_events(e1, e2)
        assert route["from_event"] == "Start"
        assert route["to_event"] == "End"
        assert route["estimated_travel_time_minutes"] == 10
