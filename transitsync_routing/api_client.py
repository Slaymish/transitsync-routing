import requests
import logging
import time
import math
import datetime
import re
import os
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


class APIClient:
    """
    Client for interacting with Metlink and OpenStreetMap APIs.
    Handles geocoding, stop information, and departure predictions.
    """
    
    def __init__(self, offline_mode=None):
        """
        Initialize the API client.
        
        Args:
            offline_mode: If True, forces offline mode. If None, checks TRANSITSYNC_OFFLINE env var.
        """
        self.geocode_cache = {}  # key: normalized address, value: (lat, lon)
        
        # Determine offline mode - explicit parameter or environment variable
        if offline_mode is None:
            self.offline_mode = os.environ.get('TRANSITSYNC_OFFLINE', 'false').lower() in ('true', '1', 't')
        else:
            self.offline_mode = offline_mode
            
        if self.offline_mode:
            logging.info("APIClient initialized in OFFLINE MODE - using mock data")
            
        # Predefined geocoding results for offline mode
        self.offline_geocode_data = {
            "wellington zoo": (-41.3186, 174.7824),
            "wellington zoo, 200 daniell street, newtown, wellington 6021, new zealand": (-41.3186, 174.7824),
            "victoria university": (-41.2901, 174.7682),
            "victoria university of wellington, kelburn parade, wellington, new zealand": (-41.2901, 174.7682),
            "kelburn campus": (-41.2901, 174.7682),
            "kelburn campus, victoria university, wellington, new zealand": (-41.2901, 174.7682),
            "cotton building": (-41.2900, 174.7686),
            "murphy building": (-41.2896, 174.7677),
            "cuba street": (-41.2944, 174.7748),
            "cuba street, wellington, new zealand": (-41.2944, 174.7748),
            "willis street": (-41.2874, 174.7746),
            "willis street, wellington, new zealand": (-41.2874, 174.7746),
            "lambton quay": (-41.2836, 174.7757),
            "lambton quay, wellington, new zealand": (-41.2836, 174.7757),
            "wellington railway station": (-41.2790, 174.7851),
            "wellington station": (-41.2790, 174.7851),
            "123 the terrace, wellington": (-41.2820, 174.7730),
            "the terrace, wellington": (-41.2820, 174.7730)
        }
        
        # Common Wellington bus stops as fallbacks
        self.wellington_stops = [
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
            Stop('5500', 'Courtenay Place', -41.293713, 174.782042),
            
            # Cuba Street area
            Stop('5008', 'Cuba Street', -41.294532, 174.774829),
            Stop('5505', 'Cuba Street at Manners Street', -41.291466, 174.776570)
        ]
        
        # Sample stop prediction data for offline mode
        self.offline_predictions = {
            "4130": [
                {
                    "service_id": "21",
                    "departure_time": "10:05 AM",
                    "destination": "Courtenay Place",
                    "status": "On time",
                    "vehicle_id": "3011"
                },
                {
                    "service_id": "18e",
                    "departure_time": "10:12 AM",
                    "destination": "Karori Park",
                    "status": "On time",
                    "vehicle_id": "2068"
                }
            ],
            "6415": [
                {
                    "service_id": "1",
                    "departure_time": "10:07 AM",
                    "destination": "Wellington Station",
                    "status": "2 min late",
                    "vehicle_id": "3426"
                },
                {
                    "service_id": "3",
                    "departure_time": "10:15 AM",
                    "destination": "Lyall Bay",
                    "status": "On time",
                    "vehicle_id": "3750"
                }
            ],
            "5008": [
                {
                    "service_id": "2",
                    "departure_time": "10:03 AM",
                    "destination": "Miramar",
                    "status": "On time",
                    "vehicle_id": "3124"
                },
                {
                    "service_id": "18e",
                    "departure_time": "10:10 AM",
                    "destination": "Campus Connection",
                    "status": "On time",
                    "vehicle_id": "2072"
                }
            ],
            "5515": [
                {
                    "service_id": "1",
                    "departure_time": "10:00 AM",
                    "destination": "Island Bay",
                    "status": "On time",
                    "vehicle_id": "3501"
                },
                {
                    "service_id": "2",
                    "departure_time": "10:05 AM",
                    "destination": "Miramar",
                    "status": "On time",
                    "vehicle_id": "3502"
                },
                {
                    "service_id": "3",
                    "departure_time": "10:10 AM",
                    "destination": "Lyall Bay",
                    "status": "On time",
                    "vehicle_id": "3503"
                }
            ]
        }
        
    def _normalize_address(self, address: str) -> str:
        """
        Normalizes the address. Handles special Wellington locations and VUW building codes.
        Returns the normalized address string.
        """
        if not address:
            logging.error("Empty address provided for normalization")
            return ""
        
        normalized = address.strip()
        
        # Special mappings for abbreviated Wellington locations
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
        
        # Handle VUW building codes like "CO246"
        vuw_code_pattern = re.compile(r'^([A-Za-z]{2,4})(\d{1,3})$')
        match = vuw_code_pattern.match(normalized)
        if match:
            building_code = match.group(1).upper()
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
                normalized = f"{buildings[building_code]}, Kelburn Campus, Victoria University, Wellington, New Zealand"
                logging.info(f"Recognized VUW room code '{address}' -> '{normalized}'")
        elif normalized in wellington_locations:
            normalized = wellington_locations[normalized]
            logging.info(f"Normalized '{address}' to '{normalized}'")
        else:
            for key, full_address in wellington_locations.items():
                if key.lower() in normalized.lower():
                    normalized = full_address
                    logging.info(f"Normalized '{address}' to '{normalized}'")
                    break

        # Append Wellington/New Zealand context if missing details.
        if "wellington" not in normalized.lower() and "new zealand" not in normalized.lower():
            if not any(loc in normalized.lower() for loc in ["street", "road", "avenue", "drive"]):
                original = normalized
                normalized = f"{normalized}, Wellington, New Zealand"
                logging.info(f"Added Wellington context: '{original}' -> '{normalized}'")
        
        return normalized
    
    def geocode_address(self, address: str):
        """
        Geocodes an address using Nominatim.
        Uses a cache to avoid repeat API calls.
        In offline mode, uses predefined location data.
        """
        if not address:
            logging.error("Empty address provided for geocoding")
            return None
        
        normalized = self._normalize_address(address)
        
        # Check cache first
        if normalized in self.geocode_cache:
            logging.info("Cache hit for address '%s'", normalized)
            return self.geocode_cache[normalized]
        
        # In offline mode, check our predefined locations
        if self.offline_mode:
            normalized_lower = normalized.lower()
            # Try direct match first
            if normalized_lower in self.offline_geocode_data:
                coords = self.offline_geocode_data[normalized_lower]
                logging.info(f"[OFFLINE] Geocoded '{normalized}' to {coords}")
                self.geocode_cache[normalized] = coords
                return coords
            
            # Try partial match
            for key, coords in self.offline_geocode_data.items():
                if key in normalized_lower or normalized_lower in key:
                    logging.info(f"[OFFLINE] Partial match: Geocoded '{normalized}' to {coords} (matched with '{key}')")
                    self.geocode_cache[normalized] = coords
                    return coords
                    
            # Common fallbacks for popular locations
            if "zoo" in normalized_lower:
                coords = (-41.3186, 174.7824)
                logging.info(f"[OFFLINE] Fallback geocoding for '{normalized}' to Wellington Zoo")
                self.geocode_cache[normalized] = coords
                return coords
            elif any(keyword in normalized_lower for keyword in ["victoria", "university", "vuw", "kelburn campus"]):
                coords = (-41.2901, 174.7682)
                logging.info(f"[OFFLINE] Fallback geocoding for '{normalized}' to Victoria University")
                self.geocode_cache[normalized] = coords
                return coords
            elif "cotton" in normalized_lower:
                coords = (-41.2900, 174.7686)
                logging.info(f"[OFFLINE] Fallback geocoding for '{normalized}' to Cotton Building")
                self.geocode_cache[normalized] = coords
                return coords
            elif "murphy" in normalized_lower:
                coords = (-41.2896, 174.7677)
                logging.info(f"[OFFLINE] Fallback geocoding for '{normalized}' to Murphy Building")
                self.geocode_cache[normalized] = coords
                return coords
            elif "cuba" in normalized_lower:
                coords = (-41.2944, 174.7748)
                logging.info(f"[OFFLINE] Fallback geocoding for '{normalized}' to Cuba Street")
                self.geocode_cache[normalized] = coords
                return coords
                
            logging.warning(f"[OFFLINE] No geocoding match found for '{normalized}'")
            return (-41.2865, 174.7762)  # Wellington city center as fallback
        
        # Online mode - continue with regular API call
        url = Config.OSM_URL or "https://nominatim.openstreetmap.org/search"
        params = {"q": normalized, "format": "json", "limit": 1}
        headers = {"User-Agent": "TransitSync/1.0 (hamishapps@gmail.com)"}
        
        try:
            # Respect API limits
            time.sleep(1)
            response = requests.get(url, params=params, headers=headers)
            if response.status_code != 200:
                logging.error("Nominatim geocoding failed: %s", response.text)
                return None
            data = response.json()
            if not data:
                logging.error("No geocoding result for address: %s", normalized)
                # Fallbacks for popular locations
                if "wellington zoo" in normalized.lower():
                    coords = (-41.3186, 174.7824)
                elif any(keyword in normalized.lower() for keyword in ["victoria university", "vuw", "kelburn campus"]):
                    coords = (-41.2901, 174.7682)
                elif "cotton building" in normalized.lower():
                    coords = (-41.2900, 174.7686)
                elif "murphy" in normalized.lower():
                    coords = (-41.2896, 174.7677)
                else:
                    return None
                self.geocode_cache[normalized] = coords
                return coords
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            coords = (lat, lon)
            logging.info("Geocoded address '%s' to lat: %s, lon: %s", normalized, lat, lon)
            # Cache the result
            self.geocode_cache[normalized] = coords
            return coords
        except Exception as e:
            logging.error("Exception during geocoding: %s", e)
            # In case of network error, fall back to offline data if available
            normalized_lower = normalized.lower()
            for key, coords in self.offline_geocode_data.items():
                if key in normalized_lower or normalized_lower in key:
                    logging.info(f"[FALLBACK] Network error, using offline data for '{normalized}': {coords}")
                    self.geocode_cache[normalized] = coords
                    return coords
            return None
    
    def find_nearest_stop(self, lat: float, lon: float):
        """
        Fetches all stops from the Metlink GTFS stops API and returns the nearest Stop object.
        In offline mode, uses predefined stop data.
        """
        # In offline mode, just use our hardcoded stops
        if self.offline_mode:
            nearest_stop = min(self.wellington_stops, 
                              key=lambda s: haversine_distance(lat, lon, s.lat, s.lon))
            logging.info(f"[OFFLINE] Found nearest stop: {nearest_stop}")
            return nearest_stop
        
        url = "https://api.opendata.metlink.org.nz/v1/gtfs/stops"
        headers = {
            "accept": "application/json",
        }
        
        if hasattr(Config, 'API_KEY') and Config.API_KEY:
            headers["x-api-key"] = Config.API_KEY
            
        try:
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                logging.error("Failed to fetch stops: %s", response.text)
                return self._get_hardcoded_stop_near(lat, lon)
                
            data = response.json()
            
            # Handle both possible response formats (list or dictionary with 'stops' key)
            stops_data = []
            if isinstance(data, dict) and 'stops' in data:
                stops_data = data['stops']
            elif isinstance(data, list):
                stops_data = data
            else:
                logging.warning("Unexpected API response format, using fallback stop data")
                return self._get_hardcoded_stop_near(lat, lon)
                
            if not stops_data:
                logging.error("No stops found in response")
                return self._get_hardcoded_stop_near(lat, lon)
                
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
                return self._get_hardcoded_stop_near(lat, lon)
                
            nearest_stop = min(stops, key=lambda s: haversine_distance(lat, lon, s.lat, s.lon))
            logging.info(f"Nearest stop found: {nearest_stop}")
            return nearest_stop
            
        except Exception as e:
            logging.error(f"Exception in finding nearest stop: {e}")
            return self._get_hardcoded_stop_near(lat, lon)
    
    def _get_hardcoded_stop_near(self, lat: float, lon: float):
        """
        Returns a hardcoded stop based on the location, for when the API fails.
        """
        # Find the nearest one from our hardcoded list
        nearest_stop = min(self.wellington_stops, 
                          key=lambda s: haversine_distance(lat, lon, s.lat, s.lon))
        logging.info(f"Using fallback hardcoded stop: {nearest_stop}")
        return nearest_stop
    
    def query_otp_graphql(self, query: str, variables: dict):
        """
        Sends a GraphQL query to the OTP API.
        In offline mode, returns mock itineraries.
        """
        if self.offline_mode:
            # Generate a mock route response
            from_lat = variables.get('from', {}).get('lat', 0) 
            from_lon = variables.get('from', {}).get('lon', 0)
            to_lat = variables.get('to', {}).get('lat', 0)
            to_lon = variables.get('to', {}).get('lon', 0)
            
            # Calculate approximate travel time based on distance
            distance_km = haversine_distance(from_lat, from_lon, to_lat, to_lon)
            
            # Mock various parameters
            travel_time_minutes = max(10, int(distance_km * 6))  # ~10km/h for public transit including stops
            walking_speed = 5  # km/h
            transit_speed = 20  # km/h
            
            # Determine if it's walkable or needs transit
            is_walkable = distance_km < 2  # Less than 2km is walkable
            
            # Calculate timestamps
            arrive_by = variables.get('arriveBy', False)
            time_str = variables.get('time', '12:00pm')
            date_str = variables.get('date', datetime.date.today().strftime('%Y-%m-%d'))
            
            try:
                # Parse the time
                if ':' in time_str:
                    if 'am' in time_str.lower() or 'pm' in time_str.lower():
                        time_obj = datetime.datetime.strptime(time_str, '%I:%M%p')
                    else:
                        time_obj = datetime.datetime.strptime(time_str, '%H:%M')
                else:
                    time_obj = datetime.datetime.strptime('12:00', '%H:%M')
                
                # Parse the date
                date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                
                # Combine date and time
                target_time = datetime.datetime.combine(date_obj.date(), time_obj.time())
                
                # Convert to timestamp (milliseconds)
                target_timestamp = int(target_time.timestamp() * 1000)
                
                if arrive_by:
                    end_time = target_timestamp
                    start_time = end_time - (travel_time_minutes * 60 * 1000)
                else:
                    start_time = target_timestamp
                    end_time = start_time + (travel_time_minutes * 60 * 1000)
                
                # Create mock response based on the distance
                if is_walkable:
                    # Just a single walking leg
                    mock_response = {
                        "data": {
                            "plan": {
                                "itineraries": [
                                    {
                                        "duration": travel_time_minutes * 60,  # seconds
                                        "legs": [
                                            {
                                                "mode": "WALK",
                                                "startTime": start_time,
                                                "endTime": end_time,
                                                "from": {
                                                    "name": "Origin"
                                                },
                                                "to": {
                                                    "name": "Destination"
                                                }
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                    }
                else:
                    # Create a transit journey with walking to/from stops
                    walking_time = 5 * 60 * 1000  # 5 minutes in milliseconds
                    transit_time = (travel_time_minutes * 60 * 1000) - (walking_time * 2)
                    
                    walk1_start = start_time
                    walk1_end = walk1_start + walking_time
                    
                    transit_start = walk1_end
                    transit_end = transit_start + transit_time
                    
                    walk2_start = transit_end
                    walk2_end = walk2_start + walking_time
                    
                    # Find nearest stops
                    from_stop = self._get_hardcoded_stop_near(from_lat, from_lon)
                    to_stop = self._get_hardcoded_stop_near(to_lat, to_lon)
                    
                    mock_response = {
                        "data": {
                            "plan": {
                                "itineraries": [
                                    {
                                        "duration": travel_time_minutes * 60,  # seconds
                                        "legs": [
                                            {
                                                "mode": "WALK",
                                                "startTime": walk1_start,
                                                "endTime": walk1_end,
                                                "from": {
                                                    "name": "Origin"
                                                },
                                                "to": {
                                                    "name": from_stop.name
                                                }
                                            },
                                            {
                                                "mode": "BUS",
                                                "startTime": transit_start,
                                                "endTime": transit_end,
                                                "from": {
                                                    "name": from_stop.name
                                                },
                                                "to": {
                                                    "name": to_stop.name
                                                }
                                            },
                                            {
                                                "mode": "WALK",
                                                "startTime": walk2_start,
                                                "endTime": walk2_end,
                                                "from": {
                                                    "name": to_stop.name
                                                },
                                                "to": {
                                                    "name": "Destination"
                                                }
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                    }
                
                logging.info(f"[OFFLINE] Generated mock route with {travel_time_minutes} minutes travel time")
                return mock_response
                
            except Exception as e:
                logging.error(f"Error creating mock response: {e}")
                # Return a simple fallback response
                return {
                    "data": {
                        "plan": {
                            "itineraries": [
                                {
                                    "duration": 1200,  # 20 minutes
                                    "legs": [
                                        {
                                            "mode": "WALK",
                                            "startTime": int(time.time() * 1000),
                                            "endTime": int(time.time() * 1000) + 1200000,
                                            "from": {"name": "Origin"},
                                            "to": {"name": "Destination"}
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                }
        
        # Online mode - actual API call
        endpoint = Config.OTP_URL or "http://localhost:8080/otp/index/graphql"
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(endpoint, json={"query": query, "variables": variables}, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error("GraphQL query failed: %s", e)
            
            # Fall back to offline mode if online fails
            logging.info("Falling back to offline mode for route planning")
            self.offline_mode = True
            return self.query_otp_graphql(query, variables)
    
    def get_stop_predictions(self, stop_id: str):
        """
        Fetches stop departure predictions from the Metlink API for a given stop ID.
        In offline mode, returns mock predictions.
        """
        if self.offline_mode:
            if stop_id in self.offline_predictions:
                predictions = self.offline_predictions[stop_id]
                logging.info(f"[OFFLINE] Found {len(predictions)} predictions for stop {stop_id}")
                return predictions
            
            # Generate some mock predictions if not in our predefined data
            now = datetime.datetime.now()
            mock_predictions = [
                {
                    "service_id": "1",
                    "departure_time": (now + datetime.timedelta(minutes=5)).strftime("%I:%M %p"),
                    "destination": "Wellington Station",
                    "status": "On time",
                    "vehicle_id": "3001"
                },
                {
                    "service_id": "2",
                    "departure_time": (now + datetime.timedelta(minutes=12)).strftime("%I:%M %p"),
                    "destination": "Miramar",
                    "status": "On time",
                    "vehicle_id": "3002"
                }
            ]
            logging.info(f"[OFFLINE] Generated {len(mock_predictions)} mock predictions for stop {stop_id}")
            return mock_predictions
            
        # Online mode - actual API call
        url = f"https://api.opendata.metlink.org.nz/v1/stop-predictions?stop_id={stop_id}"
        headers = {
            "accept": "application/json",
        }
        
        if hasattr(Config, 'API_KEY') and Config.API_KEY:
            headers["x-api-key"] = Config.API_KEY
            
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
            # Fall back to offline predictions
            logging.info("Falling back to offline predictions")
            self.offline_mode = True
            return self.get_stop_predictions(stop_id)