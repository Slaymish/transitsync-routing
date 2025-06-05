import datetime
import pytest
from transitsync_routing.event import Event


def test_parse_datetime_valid_and_invalid():
    e = Event({"summary": "test", "start": {"dateTime": "2025-01-01T10:00:00"}})
    assert e.start_time == datetime.datetime(2025, 1, 1, 10, 0)

    # invalid string should produce None
    e2 = Event({"summary": "bad", "start": {"dateTime": "notadate"}})
    assert e2.start_time is None


def test_to_dict_roundtrip():
    data = {
        "summary": "meeting",
        "location": "Place",
        "description": "Desc",
        "start": {"dateTime": "2025-01-01T09:00:00", "timeZone": "Pacific/Auckland"},
        "end": {"dateTime": "2025-01-01T10:00:00", "timeZone": "Pacific/Auckland"},
    }
    event = Event(data)
    result = event.to_dict()
    assert result["summary"] == data["summary"]
    assert result["location"] == data["location"]
    assert result["start"]["dateTime"].startswith("2025-01-01T09:00:00")
    assert result["end"]["dateTime"].startswith("2025-01-01T10:00:00")
