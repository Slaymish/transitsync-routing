import logging
import datetime
import math  # Required for haversine calculations in the fallback route planner
from .event import Event
from .api_client import APIClient
from .config import Config

class RoutePlanner:
    def __init__(self, events):
        """
        Initialize the RoutePlanner with a list of CalendarEvent objects.
        """
        self.events = events
        self.api_client = APIClient()

    def plan_route_between_events(self, event1: Event, event2: Event):
        """
        Plans a transit route between two events using OTP's GraphQL API,
        scheduling the route based on event2's start time (or fallback).
        """
        if not event1.location:
            logging.warning(f"Event '{event1.summary}' is missing a location")
            return None
        if not event2.location:
            logging.warning(f"Event '{event2.summary}' is missing a location")
            return None

        # Determine arrival time: event2.start_time > event1.end_time > now fallback
        if event2.start_time:
            arrival_dt = event2.start_time
        elif event1.end_time:
            arrival_dt = event1.end_time
        else:
            arrival_dt = datetime.datetime.now()

        # Log routing information for debugging
        logging.info(f"Planning route from '{event1.summary}' at '{event1.location}' to '{event2.summary}' at '{event2.location}'")
        logging.info(f"Target arrival time: {arrival_dt.isoformat()}")

        # Geocode both event locations
        logging.debug(f"Geocoding origin: {event1.location}")
        geo1 = self.api_client.geocode_address(event1.location)
        if geo1 is None:
            logging.error(f"Failed to geocode for event: {event1.summary} at {event1.location}")
            return None
            
        logging.debug(f"Geocoding destination: {event2.location}")
        geo2 = self.api_client.geocode_address(event2.location)
        if geo2 is None:
            logging.error(f"Failed to geocode for event: {event2.summary} at {event2.location}")
            return None

        lat1, lon1 = geo1
        lat2, lon2 = geo2
        logging.info(f"Origin coordinates: ({lat1}, {lon1}), Destination coordinates: ({lat2}, {lon2})")

        time_str = arrival_dt.strftime("%I:%M%p").lower()   # Example: "08:45am"
        date_str = arrival_dt.strftime("%Y-%m-%d")

        # Create GraphQL query with updated format for OTP v2+
        query = """
        query PlanRoute($fromLat: Float!, $fromLon: Float!, $toLat: Float!, $toLon: Float!, $time: String!, $date: String!, $arriveBy: Boolean!) {
          plan(
            fromPlace: {lat: $fromLat, lon: $fromLon},
            toPlace: {lat: $toLat, lon: $toLon},
            date: $date,
            time: $time,
            arriveBy: $arriveBy,
            transportModes: [{mode: WALK}, {mode: TRANSIT}]
          ) {
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
            "fromLat": lat1,
            "fromLon": lon1,
            "toLat": lat2,
            "toLon": lon2,
            "time": time_str,
            "date": date_str,
            "arriveBy": True
        }

        # Execute GraphQL query with better error handling
        try:
            logging.info(f"Executing GraphQL route query for {time_str} on {date_str}")
            result = self.api_client.query_otp_graphql(query, variables)
            
            if result is None:
                logging.error("GraphQL query returned None result")
                return self._create_fallback_route(event1, event2, arrival_dt)
                
            if "data" not in result:
                logging.error(f"GraphQL response missing 'data' field: {result}")
                return self._create_fallback_route(event1, event2, arrival_dt)
                
            if "plan" not in result["data"]:
                logging.error(f"GraphQL response missing 'plan' field: {result}")
                return self._create_fallback_route(event1, event2, arrival_dt)
                
            if "errors" in result:
                logging.error(f"GraphQL query returned errors: {result['errors']}")
                return self._create_fallback_route(event1, event2, arrival_dt)
            
            plan_data = result["data"]["plan"]
            if plan_data is None:
                logging.error("GraphQL plan data is None")
                return self._create_fallback_route(event1, event2, arrival_dt)
            
            itineraries = plan_data.get("itineraries", [])
            if not itineraries:
                logging.error("No itineraries found in GraphQL response")
                return self._create_fallback_route(event1, event2, arrival_dt)
            
            chosen = itineraries[0]
            if not chosen.get("legs"):
                logging.error("Chosen itinerary contains no legs")
                return self._create_fallback_route(event1, event2, arrival_dt)
            
            # Process the successful response
            first_leg = chosen["legs"][0]
            last_leg = chosen["legs"][-1]
            
            try:
                predicted_departure = datetime.datetime.fromtimestamp(first_leg["startTime"] / 1000).isoformat()
                estimated_arrival_time = datetime.datetime.fromtimestamp(last_leg["endTime"] / 1000).isoformat()
            except (KeyError, TypeError, ValueError) as e:
                logging.error(f"Error parsing leg times: {e}")
                return self._create_fallback_route(event1, event2, arrival_dt)
            
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
            logging.info(f"GraphQL planned route: {route_info['from_location']} → {route_info['to_location']} ({route_info['estimated_travel_time_minutes']:.1f} min)")
            return route_info
            
        except Exception as e:
            logging.error(f"Error planning route between events: {e}", exc_info=True)
            return self._create_fallback_route(event1, event2, arrival_dt)
            
    def _create_fallback_route(self, event1, event2, arrival_dt):
        """
        Creates a fallback route when GraphQL planning fails.
        Uses a simple straight-line distance estimation.
        """
        logging.info("Creating fallback route plan")
        
        try:
            # Get geocoded coordinates
            geo1 = self.api_client.geocode_address(event1.location)
            geo2 = self.api_client.geocode_address(event2.location)
            
            if not geo1 or not geo2:
                logging.error("Cannot create fallback route: missing coordinates")
                return None
                
            lat1, lon1 = geo1
            lat2, lon2 = geo2
            
            # Calculate straight-line distance (haversine)
            R = 6371  # Earth radius in km
            dLat = math.radians(lat2 - lat1)
            dLon = math.radians(lon2 - lon1)
            a = (math.sin(dLat/2) * math.sin(dLat/2) + 
                 math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
                 math.sin(dLon/2) * math.sin(dLon/2))
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            distance_km = R * c
            
            # Estimate travel time 
            # - Walking: ~5km/h = ~12 min/km
            # - Public transit: ~20km/h = ~3 min/km
            transit_time_minutes = 0
            
            if distance_km < 1.5:
                # Short trip - walking only
                estimated_time_minutes = distance_km * 12
                mode = "WALK"
            else:
                # Mix of transit and walking
                estimated_time_minutes = distance_km * 3 + 10  # Transit + 10 min buffer
                mode = "TRANSIT"
            
            # Set departure and arrival times
            estimated_arrival_time = arrival_dt
            predicted_departure = arrival_dt - datetime.timedelta(minutes=estimated_time_minutes)
            
            # Create a fake itinerary
            fake_leg = {
                "mode": mode,
                "startTime": int(predicted_departure.timestamp() * 1000),
                "endTime": int(estimated_arrival_time.timestamp() * 1000),
                "from": {"name": event1.location},
                "to": {"name": event2.location}
            }
            
            fake_itinerary = {
                "duration": estimated_time_minutes * 60,  # seconds
                "legs": [fake_leg]
            }
            
            # Return the route info in the same format as the normal function
            route_info = {
                "from_event": event1.summary,
                "to_event": event2.summary,
                "from_location": event1.location,
                "to_location": event2.location,
                "from_geocoded": {"lat": lat1, "lon": lon1},
                "to_geocoded": {"lat": lat2, "lon": lon2},
                "predicted_departure": predicted_departure.isoformat(),
                "estimated_travel_time_minutes": estimated_time_minutes,
                "estimated_arrival_time": estimated_arrival_time.isoformat(),
                "itinerary": fake_itinerary,
                "is_fallback": True
            }
            
            logging.info(f"Created fallback route with estimated travel time of {estimated_time_minutes:.1f} minutes")
            return route_info
            
        except Exception as e:
            logging.error(f"Error creating fallback route: {e}", exc_info=True)
            return None

    def plan_routes_for_events(self):
        """
        Plans transit routes for each consecutive pair of events.
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
        Processes the events, plans routes, and returns a list of CalendarEvent objects
        representing transit events to be added to the calendar.
        
        Args:
            home_address: The user's home address used as a starting/ending point.
        """
        if not self.events:
            logging.info("No events to process.")
            return []
        
        # Set default home address if none provided
        if not home_address:
            home_address = "1 Willis Street, Wellington, New Zealand"
            logging.info(f"No home address provided, using default: {home_address}")
        
        # Set a fallback home address if an event lacks one.
        for event in self.events:
            if not event.location or not event.location.strip():
                event.location = home_address
                logging.info(f"Using home address for event without location: {event.summary}")

        # Filter out events created by the bot
        filtered_events = [event for event in self.events if not (
            event.summary.startswith("Transit:") or event.summary.startswith("Walking:") or event.summary.startswith("[TransitBot]")
        ) and event.location and event.location.strip()]

        if len(filtered_events) < 1:
            logging.info("No valid events found after filtering.")
            return []

        sorted_events = sorted(filtered_events, key=lambda e: e.start_time or datetime.datetime.min)
        unique_events = [sorted_events[0]]
        for event in sorted_events[1:]:
            if event.location.strip().lower() != unique_events[-1].location.strip().lower():
                unique_events.append(event)
                
        routes = []
        
        # If first event isn't the home address, create a dummy home event.
        first_event = unique_events[0]
        if (first_event.location.strip().lower() != home_address.strip().lower() and
            not any(loc in first_event.location.lower() for loc in ["home", "house", "apartment", "flat"])):
            home_event = Event({
                "summary": "Home",
                "location": home_address,
                "start": {
                    "dateTime": (first_event.start_time - datetime.timedelta(hours=1)).isoformat() if first_event.start_time else datetime.datetime.now().isoformat(),
                    "timeZone": "Pacific/Auckland"
                }
            })
            home_route = self.plan_route_between_events(home_event, first_event)
            if home_route:
                routes.append(home_route)
                logging.info("Added route from home to first event: %s", home_route)
        
        for i in range(len(unique_events) - 1):
            route = self.plan_route_between_events(unique_events[i], unique_events[i+1])
            if route:
                routes.append(route)
        
        logging.info("Planned %d routes for events", len(routes))
        calendar_events = []
        for route in routes:
            if not route:
                continue
            # If the itinerary consists solely of walking legs, style accordingly.
            if route.get("itinerary") and len(route["itinerary"].get("legs", [])) > 0:
                legs = route["itinerary"]["legs"]
                if len(legs) == 1 and legs[0]["mode"] == "WALK":
                    event_dict = {
                        "summary": f"Walking: {route['from_location']} to {route['to_location']}",
                        "location": f"Walk from {route['from_location']} to {route['to_location']}",
                        "start": {"dateTime": route.get("predicted_departure"), "timeZone": Config.TIMEZONE},
                        "end": {"dateTime": route.get("estimated_arrival_time"), "timeZone": Config.TIMEZONE},
                        "description": (
                            "⏱️ WALKING DIRECTIONS ⏱️\n\n"
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
                        logging.error("Error formatting times: %s", e)
                        formatted_dep = "Unknown"
                        formatted_arr = "Unknown"
                    
                    event_dict = {
                        "summary": f"Transit: {route.get('from_location')} to {route.get('to_location')}",
                        "location": f"Transit from {route.get('from_location')} to {route.get('to_location')}",
                        "start": {"dateTime": route.get("predicted_departure"), "timeZone": Config.TIMEZONE},
                        "end": {"dateTime": route.get("estimated_arrival_time"), "timeZone": Config.TIMEZONE},
                        "description": (
                            "🚌 PUBLIC TRANSIT INFORMATION 🚌\n\n"
                            f"From: {route.get('from_event')} ({route.get('from_location')})\n"
                            f"To: {route.get('to_event')} ({route.get('to_location')})\n\n"
                            f"⏱️ Travel time: {route.get('estimated_travel_time_minutes'):.1f} minutes\n"
                            f"⏰ Depart at: {formatted_dep}\n"
                            f"🏁 Arrive by: {formatted_arr}\n"
                        )
                    }
                calendar_event = Event(event_dict)
                calendar_events.append(calendar_event)
        logging.info("Created %d calendar events from route planning", len(calendar_events))
        return calendar_events