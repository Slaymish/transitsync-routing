import json
from unittest.mock import patch, MagicMock

import pytest

from transitsync_routing.api_client import APIClient, haversine_distance


def test_haversine_distance_basic():
    # Distance between (0,0) and (0,1) approx 111.19km
    dist = haversine_distance(0, 0, 0, 1)
    assert 111 <= dist <= 112


def test_normalize_address_context():
    client = APIClient()
    result = client._normalize_address('Te Papa')
    assert 'Wellington' in result


def test_normalize_address_vuw_code():
    client = APIClient()
    result = client._normalize_address('CO246')
    assert 'Kelburn Parade' in result


def test_geocode_address_cache():
    client = APIClient()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [{"lat": "-41.1", "lon": "174.9"}]

    with patch('requests.get', return_value=mock_response) as mock_get:
        coords1 = client.geocode_address('Some Place')
        assert coords1 == (-41.1, 174.9)
        # second call should use cache
        coords2 = client.geocode_address('Some Place')
        assert coords2 == coords1
        mock_get.assert_called_once()


def test_find_nearest_stop():
    client = APIClient()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"stop_id": "1", "stop_name": "A", "stop_lat": -41.0, "stop_lon": 174.0},
        {"stop_id": "2", "stop_name": "B", "stop_lat": -41.1, "stop_lon": 174.1},
    ]
    with patch('requests.get', return_value=mock_response):
        stop = client.find_nearest_stop(-41.05, 174.05)
        assert stop.stop_id == "2"
