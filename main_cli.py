#!/usr/bin/env python3
import argparse
import logging
import datetime
import json
import sys
import os

# Add the parent directory to the path so we can import the package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from transitsync_routing.route_planner import RoutePlanner
from transitsync_routing.event import Event
from transitsync_routing.config import Config
from transitsync_routing.api_client import APIClient


def setup_logging(debug=False):
    """Configure logging based on debug flag."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


def format_time(time_str):
    """Format time string into datetime object."""
    try:
        # Try parsing ISO format
        return datetime.datetime.fromisoformat(time_str)
    except ValueError:
        try:
            # Try parsing common formats
            formats = [
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%d/%m/%Y %H:%M",
                "%H:%M"
            ]
            
            for fmt in formats:
                try:
                    if len(time_str) <= 5:  # Handle just time like "14:30"
                        today = datetime.date.today()
                        time_only = datetime.datetime.strptime(time_str, "%H:%M").time()
                        return datetime.datetime.combine(today, time_only)
                    return datetime.datetime.strptime(time_str, fmt)
                except ValueError:
                    continue
            
            # If we get here, none of the formats worked
            raise ValueError(f"Could not parse time string: {time_str}")
        except Exception as e:
            logging.error(f"Error parsing time: {e}")
            return None


def geocode_address(address, offline=False):
    """Test geocoding a single address."""
    client = APIClient(offline_mode=offline)
    result = client.geocode_address(address)
    
    if result:
        lat, lon = result
        print(f"✅ Address successfully geocoded:")
        print(f"  📍 {address}")
        print(f"  🌐 Latitude: {lat}")
        print(f"  🌐 Longitude: {lon}")
        
        # Try to find the nearest stop
        print("\nFinding nearest bus stop...")
        nearest_stop = client.find_nearest_stop(lat, lon)
        if nearest_stop:
            print(f"✅ Found nearest stop: {nearest_stop.name} (ID: {nearest_stop.stop_id})")
            
            # Try to get predictions for this stop
            print("\nFetching stop predictions...")
            predictions = client.get_stop_predictions(nearest_stop.stop_id)
            if predictions and len(predictions) > 0:
                print(f"✅ Found {len(predictions)} departures from this stop:")
                for i, pred in enumerate(predictions[:5]):  # Show max 5 predictions
                    route = pred.get('service_id', 'Unknown Route')
                    dest = pred.get('destination', 'Unknown Destination')
                    time = pred.get('arrival_time', pred.get('departure_time', 'Unknown Time'))
                    print(f"  {i+1}. Route {route} to {dest} at {time}")
            else:
                print("❌ No predictions available for this stop.")
        else:
            print("❌ Could not find a nearby stop.")
    else:
        print(f"❌ Failed to geocode address: {address}")


def route_between(from_location, to_location, arrival_time=None, offline=False):
    """Test routing between two locations."""
    # Create dummy events for the routing
    if arrival_time:
        parsed_time = format_time(arrival_time)
        if not parsed_time:
            print(f"❌ Invalid arrival time format: {arrival_time}")
            return
    else:
        parsed_time = datetime.datetime.now() + datetime.timedelta(minutes=30)
    
    # Debug log to verify locations
    logging.debug(f"Creating events with locations: '{from_location}' to '{to_location}'")
    
    from_event = Event({
        "summary": "Start Location",
        "location": from_location,
        "start": {
            "dateTime": (parsed_time - datetime.timedelta(hours=1)).isoformat(),
            "timeZone": Config.TIMEZONE
        },
        "end": {
            "dateTime": parsed_time.isoformat(),
            "timeZone": Config.TIMEZONE
        }
    })
    
    to_event = Event({
        "summary": "Destination",
        "location": to_location,
        "start": {
            "dateTime": parsed_time.isoformat(),
            "timeZone": Config.TIMEZONE
        }
    })
    
    # Verify that locations were properly set
    if not from_event.location or not to_event.location:
        logging.error(f"Failed to set event locations: from='{from_event.location}', to='{to_event.location}'")
        # Try to set them directly
        from_event.location = from_location
        to_event.location = to_location
    
    planner = RoutePlanner([from_event, to_event])
    # Set APIClient to offline mode
    planner.api_client.offline_mode = offline
    
    # Debug log before calling the planning function
    logging.debug(f"Planning route between: '{from_event.location}' and '{to_event.location}'")
    
    route = planner.plan_route_between_events(from_event, to_event)
    
    if route:
        print(f"✅ Route planned successfully:")
        print(f"  🚶 From: {from_location}")
        print(f"  🏁 To: {to_location}")
        print(f"  ⏱️ Travel time: {route['estimated_travel_time_minutes']:.1f} minutes")
        print(f"  🕒 Departure: {route['predicted_departure']}")
        print(f"  🕒 Arrival: {route['estimated_arrival_time']}")
        
        print("\nItinerary details:")
        for i, leg in enumerate(route["itinerary"]["legs"]):
            mode = leg["mode"]
            start_time = datetime.datetime.fromtimestamp(leg["startTime"] / 1000).strftime("%H:%M")
            end_time = datetime.datetime.fromtimestamp(leg["endTime"] / 1000).strftime("%H:%M")
            from_name = leg["from"]["name"]
            to_name = leg["to"]["name"]
            
            print(f"  Leg {i+1}: {mode} from {from_name} to {to_name} ({start_time} - {end_time})")
    else:
        print(f"❌ Failed to plan route between {from_location} and {to_location}")


def plan_day(events_file, home_address=None, offline=False):
    """Plan a full day of transit between multiple events."""
    try:
        with open(events_file, 'r') as f:
            events_data = json.load(f)
        
        events = []
        for event_data in events_data:
            # Make sure required fields exist
            if "summary" not in event_data or "location" not in event_data:
                print(f"❌ Event data missing required fields: {event_data}")
                continue
                
            # Add start/end time if they don't exist
            if "start" not in event_data:
                event_data["start"] = {
                    "dateTime": datetime.datetime.now().isoformat(),
                    "timeZone": Config.TIMEZONE
                }
            
            events.append(Event(event_data))
        
        if not events:
            print("❌ No valid events found in the provided file")
            return
            
        print(f"📅 Planning routes for {len(events)} events...")
        planner = RoutePlanner(events)
        # Set APIClient to offline mode
        planner.api_client.offline_mode = offline
        
        transit_events = planner.process_events(home_address=home_address)
        
        if transit_events:
            print(f"✅ Created {len(transit_events)} transit events:")
            for i, event in enumerate(transit_events):
                print(f"\n🚌 Transit Event {i+1}:")
                print(f"  📝 Summary: {event.summary}")
                print(f"  📍 Location: {event.location}")
                print(f"  🕒 Start: {event.start_time}")
                print(f"  🕒 End: {event.end_time}")
        else:
            print("❌ No transit events were created")
    
    except FileNotFoundError:
        print(f"❌ Events file not found: {events_file}")
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in events file: {events_file}")
    except Exception as e:
        print(f"❌ Error planning day: {e}")


def test_connectivity():
    """Test if we can reach external APIs."""
    import socket
    
    def check_host(host, port=80, timeout=2):
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except Exception as e:
            return False
    
    # Check connectivity to OpenStreetMap and a fallback
    osm_available = check_host('nominatim.openstreetmap.org')
    google_available = check_host('www.google.com')
    
    return osm_available or google_available


def main():
    parser = argparse.ArgumentParser(
        description="TransitSync Routing CLI - Test and demo tool for route planning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Geocode an address
  ./main_cli.py geocode "Wellington Zoo"
  
  # Plan a route between two locations
  ./main_cli.py route "Victoria University, Wellington" "Wellington Zoo" --time "14:30"
  
  # Plan a full day with multiple events from a JSON file
  ./main_cli.py plan events.json --home "123 The Terrace, Wellington"
        """
    )
    
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--offline', action='store_true', help='Force offline mode with mock data')
    
    subparsers = parser.add_subparsers(dest='command', help='Sub-command help')
    
    # Geocode command
    geocode_parser = subparsers.add_parser('geocode', help='Geocode an address')
    geocode_parser.add_argument('address', type=str, help='Address to geocode')
    
    # Route command
    route_parser = subparsers.add_parser('route', help='Plan a route between two locations')
    route_parser.add_argument('from_location', type=str, help='Starting location')
    route_parser.add_argument('to_location', type=str, help='Destination location')
    route_parser.add_argument('--time', type=str, help='Arrival time (e.g., "14:30" or ISO format)')
    
    # Plan command
    plan_parser = subparsers.add_parser('plan', help='Plan a full day of transit')
    plan_parser.add_argument('events_file', type=str, help='JSON file with events data')
    plan_parser.add_argument('--home', type=str, help='Home address to start/end from')
    
    args = parser.parse_args()
    setup_logging(args.debug)
    
    # Check connectivity and set offline mode if needed
    offline_mode = args.offline
    if not offline_mode and not test_connectivity():
        print("⚠️  Network connectivity issues detected - switching to OFFLINE mode")
        offline_mode = True
        # Set environment variable for other components
        os.environ['TRANSITSYNC_OFFLINE'] = 'true'
    
    if offline_mode:
        print("🔌 Running in OFFLINE mode with mock data")
    
    if args.command == 'geocode':
        geocode_address(args.address, offline=offline_mode)
    elif args.command == 'route':
        route_between(args.from_location, args.to_location, args.time, offline=offline_mode)
    elif args.command == 'plan':
        plan_day(args.events_file, args.home, offline=offline_mode)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()