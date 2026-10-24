# TransitSync Routing

Route planning for Wellington public transport, as a standalone Python package. It geocodes addresses with OpenStreetMap, finds nearby stops from Metlink GTFS data, checks departures, and works out whether you can get from one calendar event to the next.

This is the routing half of TransitSync. The calendar integration, auth and frontend stay private.

## What is in it

- `api_client.py`: OpenTripPlanner, Nominatim and Metlink calls.
- `route_planner.py`: stop search, walking legs and route assembly.
- `event.py`: the event model the planner works against.
- `stop.py` and `config.py`: stop data and settings.
- `main_cli.py`: a command line over the package, with a sample events file.

## Install

```bash
pip install git+https://github.com/Slaymish/transitsync-routing.git
```

## Running it

```bash
python main_cli.py --events events_sample.json
```

It talks to an OpenTripPlanner instance for the routing, with `OTP_URL` set to its address, which defaults to `http://localhost:8080`. Add `--debug` for request level logging.

## Tests

```bash
pytest tests/
```

## State

Written in April 2025 as a prototype and split out so the routing could be open source. The Metlink stop lookups send an `x-api-key` header when `API_KEY` is set in the environment, and work without one at a lower rate limit.

MIT licensed.
