import requests
import logging
import math
import datetime
from .event import Event
from .stop import Stop
from .config import Config

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
            "CO238": "Cotton Building, Kelburn Campus, Victoria University, Wellington, New Zealand",
            "CO219": "Cotton Building, Kelburn Campus, Victoria University, Wellington, New Zealand",
            "CO118": "Cotton Building, Kelburn Campus, Victoria University, Wellington, New Zealand",
            "MYLT101": "Murphy Building, Kelburn Campus, Victoria University, Wellington, New Zealand",
            "MYLT102": "Murphy Building, Kelburn Campus, Victoria University, Wellington, New Zealand",
            "MYLT103": "Murphy Building, Kelburn Campus, Victoria University, Wellington, New Zealand",
            "MY": "Murphy Building, Kelburn Campus, Victoria University, Wellington, New Zealand",
            "KK": "Kirk Building, Kelburn Campus, Victoria University, Wellington, New Zealand",
            "HM": "Hugh Mackenzie Building, Kelburn Campus, Victoria University, Wellington, New Zealand",
            "EA": "Easterfield Building, Kelburn Campus, Victoria University, Wellington, New Zealand",
            "von zedlitz": "von Zedlitz Building, Kelburn Campus, Victoria University, Wellington, New Zealand",
            "VZ": "von Zedlitz Building, Kelburn Campus, Victoria University, Wellington, New Zealand",
            "CO": "Cotton Building, Kelburn Campus, Victoria University, Wellington, New Zealand",
            "zoo": "Wellington Zoo, 200 Daniell Street, Newtown, Wellington 6021, New Zealand",
            "Wellington Zoo": "Wellington Zoo, 200 Daniell Street, Newtown, Wellington 6021, New Zealand",
            "VUW": "Victoria University of Wellington, Kelburn Parade, Wellington, New Zealand",
            "Kelburn Campus": "Victoria University of Wellington, Kelburn Parade, Wellington, New Zealand"
        }
        
        normalized_address = address.strip()
        
        # Handle VUW building codes (e.g., CO246)
        import re
        vuw_code_pattern = re.compile(r'^([A-Za-z]{2,4})(\d{1,3})$')
        match = vuw_code_pattern.match(normalized_address)
        if match:
            building_code = match.group(1).upper()
            room_number = match.group(2)
            buildings = {
                "CO": "Cotton Building",
                "MY": "Murphy Building",
                "MYLT": "Murphy Lecture Theatre",
                "KK": "Kirk Building",
                "HM": "Hugh Mackenzie Building",
                "EA": "Easterfield Building",
                "VZ": "von Zedlitz Building",
                "MC": "Maclaurin Building",
                "AM": "Alan MacDiarmid Building"
            }
            if building_code in buildings:
                full_address = f"{buildings[building_code]}, Kelburn Campus, Victoria University, Wellington, New Zealand"
                logging.info(f"Recognized VUW room code {normalized_address} -> {full_address}")
                address = full_address
        elif normalized_address in wellington_locations:
            address = wellington_locations[normalized_address]
            logging.info(f"Normalized address '{normalized_address}' to '{address}'")
        else:
            for key, full_address in wellington_locations.items():
                if key.lower() in normalized_address.lower():
                    address = full_address
                    logging.info(f"Normalized address '{normalized_address}' to '{address}'")
                    break
                
        if "wellington" not in address.lower() and "new zealand" not in address.lower():
            if not any(loc.lower() in address.lower() for loc in ["street", "road", "avenue", "drive"]):
                original_address = address
                address = f"{address}, Wellington, New Zealand"
                logging.info(f"Added Wellington context: '{original_address}' -> '{address}'")
        
        url = Config.OSM_URL 
        if not url:
            url = "https://nominatim.openstreetmap.org/search"
        params = {"q": address, "format": "json", "limit": 1}
        headers = {"User-Agent": "TransitAwareCalendarBot/1.0"}
        
        try:
            import time
            time.sleep(1)
            response = requests.get(url, params=params, headers=headers)
            if response.status_code != 200:
                logging.error("Nominatim geocoding failed: %s", response.text)
                return None
            data = response.json()
            if not data:
                logging.error("No geocoding result for address: %s", address)
                # Fallback coordinates for common locations
                if "wellington zoo" in address.lower():
                    return (-41.3186, 174.7824)
                elif "victoria university" in address.lower() or "vuw" in address.lower() or "kelburn campus" in address.lower():
                    return (-41.2901, 174.7682)
                elif "cotton building" in address.lower():
                    return (-41.2900, 174.7686)
                elif "murphy" in address.lower():
                    return (-41.2896, 174.7677)
                return None
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            logging.info("Geocoded address '%s' to lat: %s, lon: %s", address, lat, lon)
            return (lat, lon)
        except Exception as e:
            logging.error("Exception during geocoding: %s", e)
            return None

    def query_otp_graphql(self, query: str, variables: dict):
        """
        Helper method to send a GraphQL query to OTP.
        """
        endpoint = Config.OTP_URL 
        if not endpoint:
            endpoint = "http://localhost:8080/otp/index/graphql"
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(endpoint, json={"query": query, "variables": variables}, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error("GraphQL query failed: %s", e)
            return None

    def plan_route_between_events(self, event1: Event, event2: Event):
        """
        Plans a transit route between event1 and event2 using OTP's GraphQL API,
        based on the desired arrival time (event2.start_time).
        """
        if not event1.location:
            logging.warning(f"Event '{event1.summary}' is missing a location")
            return None
        if not event2.location:
            logging.warning(f"Event '{event2.summary}' is missing a location")
            return None

        # Use event2.start_time as the desired arrival time (fallback to now if not set)
        if event2.start_time:
            arrival_dt = event2.start_time
        elif event1.end_time:
            arrival_dt = event1.end_time
        else:
            arrival_dt = datetime.datetime.now()

        # Geocode the event locations
        geo1 = self.geocode_address(event1.location)
        geo2 = self.geocode_address(event2.location)
        if geo1 is None:
            logging.error(f"Failed to geocode address for event: {event1.summary}, location: {event1.location}")
            return None
        if geo2 is None:
            logging.error(f"Failed to geocode address for event: {event2.summary}, location: {event2.location}")
            return None

        lat1, lon1 = geo1
        lat2, lon2 = geo2

        # Format time as required by OTP GraphQL (e.g., "08:45am") and date ("YYYY-MM-DD")
        time_str = arrival_dt.strftime("%I:%M%p").lower()  # e.g., "08:45am"
        date_str = arrival_dt.strftime("%Y-%m-%d")

        # Construct the GraphQL query, adding the arriveBy flag
        query = """
        query PlanExample($from: LocationInput!, $to: LocationInput!, $time: String!, $date: String!, $arriveBy: Boolean!) {
          plan(from: $from, to: $to, time: $time, date: $date, arriveBy: $arriveBy, mode: "TRANSIT,WALK") {
            itineraries {
              duration
              legs {
                mode
                startTime
                endTime
                from { name }
                to { name }
              }
            }
          }
        }
        """
        variables = {
            "from": {"lat": lat1, "lon": lon1},
            "to": {"lat": lat2, "lon": lon2},
            "time": time_str,
            "date": date_str,
            "arriveBy": True
        }

        result = self.query_otp_graphql(query, variables)
        if result is None or "data" not in result or "plan" not in result["data"]:
            logging.error("GraphQL route planning failed or returned no data.")
            return None

        itineraries = result["data"]["plan"].get("itineraries", [])
        if not itineraries:
            logging.error("No itineraries found from GraphQL planning.")
            return None

        # Choose the first itinerary (or implement custom selection logic)
        chosen = itineraries[0]
        if not chosen["legs"]:
            logging.error("Chosen itinerary contains no legs.")
            return None

        # Use the first leg's times as departure and arrival for simplicity
        first_leg = chosen["legs"][0]
        predicted_departure = datetime.datetime.fromtimestamp(first_leg["startTime"] / 1000).isoformat()
        estimated_arrival_time = datetime.datetime.fromtimestamp(first_leg["endTime"] / 1000).isoformat()

        route_info = {
            "from_event": event1.summary,
            "to_event": event2.summary,
            "from_location": event1.location,
            "to_location": event2.location,
            "from_geocoded": {"lat": lat1, "lon": lon1},
            "to_geocoded": {"lat": lat2, "lon": lon2},
            "predicted_departure": predicted_departure,
            "estimated_travel_time_minutes": chosen["duration"] / 60,
            "estimated_arrival_time": estimated_arrival_time,
            "itinerary": chosen
        }
        logging.info(f"GraphQL planned route between events: {route_info}")
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

    def process_events(self, home_address=None):
        """
        Processes the events to plan routes and returns a list of CalendarEvent objects
        representing transit events that can be added to the calendar.
        
        Args:
            home_address: The user's home address to use as origin/destination
        """
        if not self.events:
            logging.info("No events to process.")
            return []
        
        # Set HOME_ADDRESS for any events without a location
        for event in self.events:
            if not event.location or event.location.strip() == "":
                if home_address:
                    event.location = home_address
                    logging.info(f"Using user's home address for event without location: {event.summary}")
                else:
                    event.location = config.HOME_ADDRESS
                    logging.info(f"Using default home address for event without location: {event.summary}")

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
        
        # Use the user's home address if available
        user_home_address = home_address if home_address else config.HOME_ADDRESS
        
        # Check if the first event's location is not HOME_ADDRESS
        first_event = unique_events[0]
        if (first_event.location.strip().lower() != user_home_address.strip().lower() and
            not any(loc.lower() in first_event.location.lower() for loc in ["home", "house", "apartment", "flat"])):
            # Create a dummy home event
            home_event = Event({
                "summary": "Home",
                "location": user_home_address,
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
            if route.get("itinerary") and len(route["itinerary"].get("legs", [])) > 0:
                # Use walking styling if the only leg is walking (heuristic)
                if len(route["itinerary"]["legs"]) == 1 and route["itinerary"]["legs"][0]["mode"] == "WALK":
                    event_dict = {
                        "summary": f"Walking: {route['from_location']} to {route['to_location']}",
                        "location": f"Walk from {route['from_location']} to {route['to_location']}",
                        "start": {
                            "dateTime": route.get("predicted_departure"),
                            "timeZone": Config.TIMEZONE
                        },
                        "end": {
                            "dateTime": route.get("estimated_arrival_time"),
                            "timeZone": Config.TIMEZONE
                        },
                        "description": (
                            f"⏱️ WALKING DIRECTIONS ⏱️\n\n"
                            f"From: {route['from_event']} ({route['from_location']})\n"
                            f"To: {route['to_event']} ({route['to_location']})\n\n"
                            f"🚶 Estimated walking time: {route['estimated_travel_time_minutes']:.1f} minutes\n"
                        )
                    }
                else:
                    try:
                        dep_time = datetime.datetime.fromisoformat(route.get("predicted_departure"))
                        arr_time = datetime.datetime.fromisoformat(route.get("estimated_arrival_time"))
                        formatted_dep = dep_time.strftime("%I:%M %p")
                        formatted_arr = arr_time.strftime("%I:%M %p")
                    except Exception as e:
                        logging.error(f"Error formatting times: {e}")
                        formatted_dep = "Unknown"
                        formatted_arr = "Unknown"
                    
                    event_dict = {
                        "summary": f"Transit: {route.get('from_location')} to {route.get('to_location')}",
                        "location": f"Transit from {route.get('from_location')} to {route.get('to_location')}",
                        "start": {
                            "dateTime": route.get("predicted_departure"),
                            "timeZone": Config.TIMEZONE
                        },
                        "end": {
                            "dateTime": route.get("estimated_arrival_time"),
                            "timeZone": Config.TIMEZONE
                        },
                        "description": (
                            f"🚌 PUBLIC TRANSIT INFORMATION 🚌\n\n"
                            f"From: {route.get('from_event')} ({route.get('from_location')})\n"
                            f"To: {route.get('to_event')} ({route.get('to_location')})\n\n"
                            f"⏱️ Travel time: {route.get('estimated_travel_time_minutes'):.1f} minutes\n"
                            f"⏰ Depart at: {formatted_dep}\n"
                            f"🏁 Arrive by: {formatted_arr}\n"
                        )
                    }
                calendar_event = Event(event_dict)
                calendar_events.append(calendar_event)
        logging.info(f"Created {len(calendar_events)} calendar events from route planning")
        return calendar_events

