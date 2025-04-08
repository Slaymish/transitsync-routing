import requests
import logging
import math
import datetime
import config
from calendar_event import CalendarEvent

class Stop:
    def __init__(self, stop_id, name, lat, lon):
        self.stop_id = stop_id
        self.name = name
        self.lat = float(lat)
        self.lon = float(lon)

    def __repr__(self):
        return f"Stop({self.stop_id}, {self.name}, {self.lat}, {self.lon})"

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two points on Earth.
    """
    R = 6371  # Earth radius in kilometers
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

class RoutePlanner:
    def __init__(self, events):
        """
        Initialize the RoutePlanner with a list of CalendarEvent objects.
        """
        self.events = events

    def geocode_address(self, address: str):
        """
        Uses Nominatim to convert an address into latitude and longitude.
        Includes special handling for common Wellington locations.
        """
        if not address:
            logging.error("Empty address provided for geocoding")
            return None
            
        # Special handling for Wellington locations that might be abbreviated
        wellington_locations = {
            "CO246": "Cotton Building, Kelburn Campus, Victoria University, Wellington, New Zealand",
            "zoo": "Wellington Zoo, 200 Daniell Street, Newtown, Wellington 6021, New Zealand",
            "Wellington Zoo": "Wellington Zoo, 200 Daniell Street, Newtown, Wellington 6021, New Zealand",
            "VUW": "Victoria University of Wellington, Kelburn Parade, Wellington, New Zealand",
            "Kelburn Campus": "Victoria University of Wellington, Kelburn Parade, Wellington, New Zealand"
        }
        
        # Check if the address matches any known locations
        normalized_address = address.strip()
        for key, full_address in wellington_locations.items():
            if key.lower() in normalized_address.lower():
                address = full_address
                logging.info(f"Normalized address '{normalized_address}' to '{address}'")
                break
                
        # For addresses without location details, add Wellington, NZ to improve geocoding success
        if "wellington" not in address.lower() and "new zealand" not in address.lower():
            if not any(loc.lower() in address.lower() for loc in ["street", "road", "avenue", "drive"]):
                original_address = address
                address = f"{address}, Wellington, New Zealand"
                logging.info(f"Added Wellington context: '{original_address}' -> '{address}'")
        
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": address, "format": "json", "limit": 1}
        headers = {"User-Agent": "TransitAwareCalendarBot/1.0"}
        
        try:
            # Add a delay to respect Nominatim's usage policy
            import time
            time.sleep(1)
            
            response = requests.get(url, params=params, headers=headers)
            if response.status_code != 200:
                logging.error("Nominatim geocoding failed: %s", response.text)
                return None
                
            data = response.json()
            if not data:
                logging.error("No geocoding result for address: %s", address)
                # Fallback geocoding for well-known Wellington locations
                if "wellington zoo" in address.lower():
                    logging.info("Using fallback coordinates for Wellington Zoo")
                    return (-41.3186, 174.7824)  # Wellington Zoo coordinates
                elif "victoria university" in address.lower() or "vuw" in address.lower() or "kelburn campus" in address.lower():
                    logging.info("Using fallback coordinates for Victoria University")
                    return (-41.2901, 174.7682)  # VUW Kelburn Campus coordinates
                return None
                
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            logging.info("Geocoded address '%s' to lat: %s, lon: %s", address, lat, lon)
            return (lat, lon)
        except Exception as e:
            logging.error("Exception during geocoding: %s", e)
            return None

    def find_nearest_stop(self, lat: float, lon: float):
        """
        Fetches all stops from the Metlink GTFS stops API and returns the nearest Stop object.
        """
        url = "https://api.opendata.metlink.org.nz/v1/gtfs/stops"
        headers = {
            "accept": "application/json",
            "x-api-key": config.METLINK_API_KEY
        }
        try:
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                logging.error("Failed to fetch stops: %s", response.text)
                return None
                
            data = response.json()
            
            # Log the data structure to diagnose the API response format
            logging.debug(f"Metlink API response type: {type(data)}")
            
            # Handle both possible response formats (list or dictionary with 'stops' key)
            stops_data = []
            if isinstance(data, dict) and 'stops' in data:
                stops_data = data['stops']
            elif isinstance(data, list):
                stops_data = data
            else:
                # Use hardcoded stops data for testing if API format changes
                logging.warning("Unexpected API response format, using fallback stop data")
                return self.get_hardcoded_stop_near(lat, lon)
                
            if not stops_data:
                logging.error("No stops found in response")
                return self.get_hardcoded_stop_near(lat, lon)
                
            stops = []
            for stop in stops_data:
                try:
                    if all(key in stop for key in ['stop_id', 'stop_name', 'stop_lat', 'stop_lon']):
                        stop_obj = Stop(
                            stop_id=stop['stop_id'],
                            name=stop['stop_name'],
                            lat=stop['stop_lat'],
                            lon=stop['stop_lon']
                        )
                        stops.append(stop_obj)
                except Exception as e:
                    logging.error(f"Error parsing stop: {e}")
                    
            if not stops:
                logging.error("No valid stops found in response")
                return self.get_hardcoded_stop_near(lat, lon)
                
            nearest_stop = min(stops, key=lambda s: haversine_distance(lat, lon, s.lat, s.lon))
            logging.info(f"Nearest stop found: {nearest_stop}")
            return nearest_stop
            
        except Exception as e:
            logging.error(f"Exception in finding nearest stop: {e}")
            return self.get_hardcoded_stop_near(lat, lon)

    def get_hardcoded_stop_near(self, lat: float, lon: float):
        """
        Returns a hardcoded stop based on the location, for when the API fails.
        """
        # Common Wellington bus stops as fallbacks
        wellington_stops = [
            # VUW Kelburn stops
            Stop('4130', 'Kelburn Parade at Gate 6', -41.290073, 174.768046),
            Stop('4129', 'Kelburn Parade opposite Gate 6', -41.289719, 174.768379),
            
            # Wellington CBD stops
            Stop('5515', 'Wellington Station', -41.278861, 174.780556),
            Stop('5000', 'Lambton Quay at Willis Street', -41.286622, 174.776923),
            
            # Newtown/Zoo area
            Stop('6415', 'Wellington Zoo', -41.319635, 174.782992),
            Stop('6416', 'Wellington Zoo', -41.319812, 174.782902),
            
            # Te Aro
            Stop('5500', 'Courtenay Place', -41.293713, 174.782042)
        ]
        
        # Find the nearest one from our hardcoded list
        nearest_stop = min(wellington_stops, key=lambda s: haversine_distance(lat, lon, s.lat, s.lon))
        logging.info(f"Using fallback hardcoded stop: {nearest_stop}")
        return nearest_stop

    def get_stop_predictions(self, stop_id: str):
        """
        Fetches stop departure predictions from the Metlink API for a given stop ID.
        """
        url = f"https://api.opendata.metlink.org.nz/v1/stop-predictions?stop_id={stop_id}"
        headers = {
            "accept": "application/json",
            "x-api-key": config.METLINK_API_KEY
        }
        try:
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                logging.error("Failed to fetch stop predictions: %s", response.text)
                return None
            data = response.json()
            predictions = data.get("departures", data)
            logging.info("Predictions for stop %s: %s", stop_id, predictions)
            return predictions
        except Exception as e:
            logging.error("Exception fetching stop predictions: %s", e)
            return None

    def plan_route_between_events(self, event1: CalendarEvent, event2: CalendarEvent):
        """
        Plans a transit route from event1 to event2.
        Returns a dictionary with route details including:
          - Geocoded coordinates of both event locations.
          - Nearest stops for departure and arrival.
          - Departure predictions from the departure stop.
          - Estimated travel time based on distance (assuming average bus speed).
        """
        # Check if events have location information
        if not event1.location:
            logging.warning(f"Event '{event1.summary}' is missing a location")
            return None
        if not event2.location:
            logging.warning(f"Event '{event2.summary}' is missing a location")
            return None

        # Check if event is tagged as fixed or flexible
        is_fixed = False
        buffer_minutes = 15  # Default buffer time
        
        # Look for tags in the event description
        if event2.description:
            if "#fixed" in event2.description.lower():
                is_fixed = True
                logging.info(f"Event '{event2.summary}' is marked as fixed")
                buffer_minutes = 20  # More buffer time for fixed appointments
            elif "#flexible" in event2.description.lower():
                is_fixed = False
                logging.info(f"Event '{event2.summary}' is marked as flexible")
                buffer_minutes = 10  # Less buffer time for flexible appointments
                
        # Also check summary for tags
        if "#fixed" in event2.summary.lower():
            is_fixed = True
            buffer_minutes = 20
        elif "#flexible" in event2.summary.lower():
            is_fixed = False
            buffer_minutes = 10

        # Try to infer location from event summary if missing
        if event1.location == "":
            if "lab" in event1.summary.lower() or "comp" in event1.summary.lower():
                event1.location = "Cotton Building, Kelburn Campus, Victoria University, Wellington"
                logging.info(f"Inferred location for '{event1.summary}': {event1.location}")
        
        if event2.location == "":
            if "lab" in event2.summary.lower() or "comp" in event2.summary.lower():
                event2.location = "Cotton Building, Kelburn Campus, Victoria University, Wellington"
                logging.info(f"Inferred location for '{event2.summary}': {event2.location}")

        # Geocode both addresses
        geo1 = self.geocode_address(event1.location)
        geo2 = self.geocode_address(event2.location)
        
        # Handle geocoding failures gracefully
        if geo1 is None:
            logging.error(f"Failed to geocode address for event: {event1.summary}, location: {event1.location}")
            return None
        if geo2 is None:
            logging.error(f"Failed to geocode address for event: {event2.summary}, location: {event2.location}")
            return None

        lat1, lon1 = geo1
        lat2, lon2 = geo2

        # Find nearest stops for departure and arrival
        departure_stop = self.find_nearest_stop(lat1, lon1)
        arrival_stop = self.find_nearest_stop(lat2, lon2)
        
        if departure_stop is None:
            logging.error(f"Failed to find nearest stop for location: {event1.location}")
            return None
        if arrival_stop is None:
            logging.error(f"Failed to find nearest stop for location: {event2.location}")
            return None

        # Calculate if the locations are within walking distance (less than 1km)
        direct_distance = haversine_distance(lat1, lon1, lat2, lon2)
        if direct_distance < 1.0:
            logging.info(f"Locations are within walking distance ({direct_distance:.2f} km). Creating a walking event.")
            # Calculate walking time using an average walking speed of 5 km/h
            walking_time_minutes = (direct_distance / 5) * 60
            walking_time = datetime.timedelta(minutes=walking_time_minutes)
            
            # Calculate departure time to arrive at the destination event start time
            predicted_departure = None
            if event2.start_time:
                # Back-calculate departure time to arrive at event2 start
                arrival_time = event2.start_time
                # Use the buffer time based on whether the event is fixed or flexible
                buffer_time = datetime.timedelta(minutes=buffer_minutes)
                dep_time = arrival_time - walking_time - buffer_time
                predicted_departure = dep_time.isoformat()
                estimated_arrival_time = (arrival_time - buffer_time).isoformat()
                
                logging.info(f"Calculated departure time {predicted_departure} to arrive at event: {event2.summary} by {estimated_arrival_time}")
            elif event1.end_time:
                # Fallback: If event2 has no start time, use event1's end time
                predicted_departure = event1.end_time.isoformat()
                logging.info(f"Using event end time as departure time for walking event: {predicted_departure}")
                
                # Calculate estimated arrival
                dep_time = event1.end_time
                est_arrival = dep_time + walking_time
                estimated_arrival_time = est_arrival.isoformat()
            else:
                logging.warning("No times available for planning; using current time as fallback.")
                predicted_departure = datetime.datetime.now().isoformat()
                try:
                    dep_time = datetime.datetime.fromisoformat(predicted_departure)
                    est_arrival = dep_time + walking_time
                    estimated_arrival_time = est_arrival.isoformat()
                except Exception as e:
                    logging.error(f"Error calculating estimated arrival time for walking event: {e}")
                    estimated_arrival_time = None

            route_info = {
                "from_event": event1.summary,
                "to_event": event2.summary,
                "from_location": event1.location,
                "to_location": event2.location,
                "from_geocoded": {"lat": lat1, "lon": lon1},
                "to_geocoded": {"lat": lat2, "lon": lon2},
                "departure_stop": None,
                "arrival_stop": None,
                "predicted_departure": predicted_departure,
                "estimated_travel_time_minutes": walking_time_minutes,
                "estimated_arrival_time": estimated_arrival_time,
                "mode": "walking"
            }
            logging.info(f"Planned walking route between events: {route_info}")
            return route_info

        # Get departure predictions from the departure stop
        predictions = self.get_stop_predictions(departure_stop.stop_id)

        # Estimate travel time based on distance between stops
        distance = haversine_distance(departure_stop.lat, departure_stop.lon, arrival_stop.lat, arrival_stop.lon)
        # Assume average bus speed of 30 km/h
        travel_time_minutes = (distance / 30) * 60
        travel_time = datetime.timedelta(minutes=travel_time_minutes)

        # Set departure time based on destination event's start time
        predicted_departure = None
        
        if event2.start_time:
            # Back-calculate departure time to arrive at event2 start
            arrival_time = event2.start_time
            # Use the buffer time based on whether the event is fixed or flexible
            buffer_time = datetime.timedelta(minutes=buffer_minutes)
            dep_time = arrival_time - travel_time - buffer_time
            predicted_departure = dep_time.isoformat()
            estimated_arrival_time = (arrival_time - buffer_time).isoformat()
            
            logging.info(f"Calculated departure time {predicted_departure} to arrive at event: {event2.summary} by {estimated_arrival_time}")
        elif event1.end_time:
            # Fallback: If event2 has no start time, use event1's end time
            predicted_departure = event1.end_time.isoformat()
            logging.info(f"Using event end time as departure time: {predicted_departure}")
            
            # Calculate estimated arrival
            dep_time = event1.end_time
            est_arrival = dep_time + travel_time
            estimated_arrival_time = est_arrival.isoformat()
        else:
            # If no predictions available and no event end time, use current time
            logging.warning("No times available for planning; using a prediction or current time.")
            
            # Pick the first available departure prediction if available
            if predictions and isinstance(predictions, list) and len(predictions) > 0:
                try:
                    predicted_departure = predictions[0].get("expected_departure_time")
                    dep_time = datetime.datetime.fromisoformat(predicted_departure)
                    est_arrival = dep_time + travel_time
                    estimated_arrival_time = est_arrival.isoformat()
                except Exception as e:
                    logging.error(f"Error parsing departure prediction: {e}")
                    predicted_departure = datetime.datetime.now().isoformat()
                    dep_time = datetime.datetime.now()
                    est_arrival = dep_time + travel_time
                    estimated_arrival_time = est_arrival.isoformat()
            else:
                predicted_departure = datetime.datetime.now().isoformat()
                dep_time = datetime.datetime.now()
                est_arrival = dep_time + travel_time
                estimated_arrival_time = est_arrival.isoformat()

        route_info = {
            "from_event": event1.summary,
            "to_event": event2.summary,
            "from_location": event1.location,
            "to_location": event2.location,
            "from_geocoded": {"lat": lat1, "lon": lon1},
            "to_geocoded": {"lat": lat2, "lon": lon2},
            "departure_stop": {
                "stop_id": departure_stop.stop_id,
                "name": departure_stop.name,
                "lat": departure_stop.lat,
                "lon": departure_stop.lon,
            },
            "arrival_stop": {
                "stop_id": arrival_stop.stop_id,
                "name": arrival_stop.name,
                "lat": arrival_stop.lat,
                "lon": arrival_stop.lon,
            },
            "predicted_departure": predicted_departure,
            "estimated_travel_time_minutes": travel_time_minutes,
            "estimated_arrival_time": estimated_arrival_time,
        }

        logging.info(f"Planned route between events: {route_info}")
        return route_info

    def plan_routes_for_events(self):
        """
        Plans transit routes for all consecutive pairs of events.
        Assumes events are sorted by start time.
        Returns a list of route_info dictionaries.
        """
        if not self.events or len(self.events) < 2:
            logging.info("Not enough events to plan routes.")
            return []

        sorted_events = sorted(self.events, key=lambda e: e.start_time or datetime.datetime.min)
        routes = []
        for i in range(len(sorted_events) - 1):
            route = self.plan_route_between_events(sorted_events[i], sorted_events[i+1])
            if route:
                routes.append(route)
        logging.info("Planned routes for events: %s", routes)
        return routes

    def process_events(self):
        """
        Processes the events to plan routes and returns a list of CalendarEvent objects
        representing transit events that can be added to the calendar.
        """
        if not self.events:
            logging.info("No events to process.")
            return []
        # Set HOME_ADDRESS for any events without a location
        for event in self.events:
            if not event.location or event.location.strip() == "":
                event.location = config.HOME_ADDRESS

        # Filter out events created by the bot to avoid processing them again
        filtered_events = [event for event in self.events if not (
            event.summary.startswith("Transit:") or event.summary.startswith("Walking:") or 
            event.summary.startswith("[TransitBot]")
        ) and event.location and event.location.strip()]
        
        if len(filtered_events) < 1:
            logging.info("No valid events found after filtering out bot-created events.")
            return []

        # Sort events by start time
        sorted_events = sorted(filtered_events, key=lambda e: e.start_time or datetime.datetime.min)
        
        # Get unique events (different locations)
        unique_events = [sorted_events[0]]
        for event in sorted_events[1:]:
            if event.location.strip().lower() != unique_events[-1].location.strip().lower():
                unique_events.append(event)
                
        routes = []
        
        # Check if the first event's location is not HOME_ADDRESS
        first_event = unique_events[0]
        if (first_event.location.strip().lower() != config.HOME_ADDRESS.strip().lower() and
            not any(loc.lower() in first_event.location.lower() for loc in ["home", "house", "apartment", "flat"])):
            # Create a dummy home event
            home_event = CalendarEvent({
                "summary": "Home",
                "location": config.HOME_ADDRESS,
                "start": {
                    "dateTime": (first_event.start_time - datetime.timedelta(hours=1)).isoformat() 
                    if first_event.start_time else datetime.datetime.now().isoformat(),
                    "timeZone": "Pacific/Auckland"
                }
            })
            # Plan route from home to first event
            home_route = self.plan_route_between_events(home_event, first_event)
            if home_route:
                routes.append(home_route)
                logging.info(f"Added route from home to first event: {home_route}")
        
        # Plan routes between all remaining events
        for i in range(len(unique_events) - 1):
            route = self.plan_route_between_events(unique_events[i], unique_events[i+1])
            if route:
                routes.append(route)
        
        logging.info(f"Planned {len(routes)} routes for events")

        # Convert route information into CalendarEvent objects
        calendar_events = []
        for route in routes:
            if not route:
                continue
            if route.get("mode") == "walking":
                event_dict = {
                    "summary": f"Walking: {route['from_location']} to {route['to_location']}",
                    "location": f"Walk from {route['from_location']} to {route['to_location']}",
                    "start": {
                        "dateTime": route.get("predicted_departure"),
                        "timeZone": "Pacific/Auckland"
                    },
                    "end": {
                        "dateTime": route.get("estimated_arrival_time"),
                        "timeZone": "Pacific/Auckland"
                    },
                    "description": (
                        f"⏱️ WALKING DIRECTIONS ⏱️\n\n"
                        f"From: {route['from_event']} ({route['from_location']})\n"
                        f"To: {route['to_event']} ({route['to_location']})\n\n"
                        f"🚶 Estimated walking time: {route['estimated_travel_time_minutes']:.1f} minutes\n"
                        f"⏰ Depart by: {datetime.datetime.fromisoformat(route['predicted_departure']).strftime('%I:%M %p')}\n"
                        f"🏁 Arrive by: {datetime.datetime.fromisoformat(route['estimated_arrival_time']).strftime('%I:%M %p')}\n\n"
                        f"Distance: {haversine_distance(*route['from_geocoded'].values(), *route['to_geocoded'].values()):.2f} km\n"
                    )
                }
            else:
                # Format the event time in a readable way
                try:
                    dep_time = datetime.datetime.fromisoformat(route.get("predicted_departure"))
                    arr_time = datetime.datetime.fromisoformat(route.get("estimated_arrival_time"))
                    formatted_dep = dep_time.strftime("%I:%M %p")
                    formatted_arr = arr_time.strftime("%I:%M %p")
                except:
                    formatted_dep = "Unknown"
                    formatted_arr = "Unknown"
                
                event_dict = {
                    "summary": f"Transit: {route['departure_stop']['name']} to {route['arrival_stop']['name']}",
                    "location": f"Bus from {route['departure_stop']['name']} to {route['arrival_stop']['name']}",
                    "start": {
                        "dateTime": route.get("predicted_departure"),
                        "timeZone": "Pacific/Auckland"
                    },
                    "end": {
                        "dateTime": route.get("estimated_arrival_time"),
                        "timeZone": "Pacific/Auckland"
                    },
                    "description": (
                        f"🚌 PUBLIC TRANSIT INFORMATION 🚌\n\n"
                        f"From: {route['from_event']} ({route['from_location']})\n"
                        f"To: {route['to_event']} ({route['to_location']})\n\n"
                        f"🚏 Departure stop: {route['departure_stop']['name']} (stop {route['departure_stop']['stop_id']})\n"
                        f"🚏 Arrival stop: {route['arrival_stop']['name']} (stop {route['arrival_stop']['stop_id']})\n\n"
                        f"⏱️ Travel time: {route['estimated_travel_time_minutes']:.1f} minutes\n"
                        f"⏰ Depart by: {formatted_dep}\n"
                        f"🏁 Arrive by: {formatted_arr}\n\n"
                        f"Distance: {haversine_distance(route['departure_stop']['lat'], route['departure_stop']['lon'], route['arrival_stop']['lat'], route['arrival_stop']['lon']):.2f} km\n"
                        f"Routes: Check Metlink app or website for specific buses\n"
                    )
                }
            # Create a CalendarEvent object from the dictionary
            calendar_event = CalendarEvent(event_dict)
            calendar_events.append(calendar_event)

        logging.info(f"Created {len(calendar_events)} calendar events from route planning")
        return calendar_events