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
    Handles geocoding, stop information, and OTP route planning.
    """
    
    def __init__(self, offline_mode=None):
        """
        Initialize the API client.
        """
        self.geocode_cache = {}  # key: normalized address, value: (lat, lon)
            
        # List of possible GraphQL endpoint paths to try (in order of preference)
        self.graphql_endpoints = [
            "/otp/routers/default/index/graphql",  # Common path for OTP 2.x
            "/otp/index/graphql",                  # Original path used in code
            "/otp/graphql",                        # Alternative path
            "/graphql"                             # Newer versions simplified path
        ]
        # We'll find the working endpoint on first GraphQL call
        self.working_graphql_endpoint = None
            
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
        """
        if not address:
            logging.error("Empty address provided for geocoding")
            return None
        
        normalized = self._normalize_address(address)
        
        # Check cache first
        if normalized in self.geocode_cache:
            logging.info("Cache hit for address '%s'", normalized)
            return self.geocode_cache[normalized]
        
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
                return None
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            coords = (lat, lon)
            logging.info("Geocoded address '%s' to lat: %s, lon: %s", normalized, lat, lon)
            # Cache the result
            self.geocode_cache[normalized] = coords
            return coords
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
        }
        
        if hasattr(Config, 'API_KEY') and Config.API_KEY:
            headers["x-api-key"] = Config.API_KEY
            
        try:
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                logging.error("Failed to fetch stops: %s", response.text)
                return None
                
            data = response.json()
            
            # Handle both possible response formats (list or dictionary with 'stops' key)
            stops_data = []
            if isinstance(data, dict) and 'stops' in data:
                stops_data = data['stops']
            elif isinstance(data, list):
                stops_data = data
            else:
                logging.warning("Unexpected API response format")
                return None
                
            if not stops_data:
                logging.error("No stops found in response")
                return None
                
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
                return None
                
            nearest_stop = min(stops, key=lambda s: haversine_distance(lat, lon, s.lat, s.lon))
            logging.info(f"Nearest stop found: {nearest_stop}")
            return nearest_stop
            
        except Exception as e:
            logging.error(f"Exception in finding nearest stop: {e}")
            return None
    
    def query_otp_graphql(self, query: str, variables: dict):
        """
        Sends a GraphQL query to the OTP API.
        Will try multiple endpoints to find the working one for the OTP server.
        
        Returns the GraphQL query result or None if the query fails.
        """
        # Online mode - actual API call
        base_url = Config.OTP_URL or "http://localhost:8080"
        headers = {"Content-Type": "application/json"}

        # Log the GraphQL query to help with debugging
        logging.info(f"Sending GraphQL query to OTP: variables={variables}")
        logging.debug(f"GraphQL query: {query}")
        
        # If we already found a working endpoint, try it first
        if self.working_graphql_endpoint:
            try:
                endpoint = f"{base_url}{self.working_graphql_endpoint}"
                logging.info(f"Using previously working GraphQL endpoint: {endpoint}")
                response = requests.post(
                    endpoint, 
                    json={"query": query, "variables": variables}, 
                    headers=headers,
                    timeout=30  # Add timeout to prevent hanging requests
                )
                
                # Log the response status and details
                logging.debug(f"GraphQL response status: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    # Check for GraphQL errors in the response
                    if 'errors' in result:
                        logging.error(f"GraphQL errors in response: {result['errors']}")
                        # Continue to try other endpoints if there are GraphQL errors
                        self.working_graphql_endpoint = None
                    else:
                        return result
                else:
                    # If it's not working anymore, reset and try all endpoints
                    logging.warning(f"Previously working GraphQL endpoint {endpoint} returned {response.status_code}: {response.text[:200]}")
                    self.working_graphql_endpoint = None
            except requests.exceptions.Timeout:
                logging.warning(f"Timeout connecting to GraphQL endpoint {base_url}{self.working_graphql_endpoint}")
                self.working_graphql_endpoint = None
            except requests.exceptions.ConnectionError:
                logging.warning(f"Connection error with GraphQL endpoint {base_url}{self.working_graphql_endpoint}")
                self.working_graphql_endpoint = None
            except Exception as e:
                logging.warning(f"Error with previously working endpoint: {str(e)}")
                self.working_graphql_endpoint = None
        
        # Try each endpoint path until we find a working one
        last_error = None
        for path in self.graphql_endpoints:
            endpoint = f"{base_url}{path}"
            try:
                logging.info(f"Trying GraphQL endpoint: {endpoint}")
                response = requests.post(
                    endpoint, 
                    json={"query": query, "variables": variables}, 
                    headers=headers,
                    timeout=30  # Add timeout to prevent hanging requests
                )
                
                logging.debug(f"Endpoint {path} returned status {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    # Check for GraphQL errors in the response
                    if 'errors' in result:
                        error_messages = [error.get('message', 'Unknown GraphQL error') for error in result.get('errors', [])]
                        logging.error(f"GraphQL errors in response from {path}: {error_messages}")
                        # Continue to next endpoint
                        last_error = f"GraphQL errors: {error_messages}"
                    else:
                        logging.info(f"Found working GraphQL endpoint: {path}")
                        self.working_graphql_endpoint = path
                        return result
                else:
                    response_text = response.text[:200]  # Limit to first 200 chars to avoid huge logs
                    logging.warning(f"Endpoint {path} returned {response.status_code}: {response_text}...")
                    last_error = f"HTTP {response.status_code}: {response_text}"
            except requests.exceptions.Timeout:
                logging.warning(f"Timeout connecting to GraphQL endpoint {endpoint}")
                last_error = f"Connection timeout for {endpoint}"
            except requests.exceptions.ConnectionError as e:
                logging.warning(f"Connection error with GraphQL endpoint {endpoint}: {str(e)}")
                last_error = f"Connection error: {str(e)}"
            except requests.exceptions.RequestException as e:
                logging.warning(f"Request error with GraphQL endpoint {endpoint}: {str(e)}")
                last_error = f"Request error: {str(e)}"
            except Exception as e:
                logging.warning(f"Failed to connect to GraphQL endpoint {endpoint}: {str(e)}")
                last_error = str(e)
        
        # If we get here, no endpoint worked
        logging.error(f"All GraphQL endpoints failed. Last error: {last_error}")
        
        # Add some troubleshooting diagnostics
        logging.error(f"OTP GraphQL connection troubleshooting:")
        logging.error(f"- Base URL configured: {base_url}")
        logging.error(f"- Tried endpoints: {self.graphql_endpoints}")
        logging.error(f"- Check if OTP server is running and accessible")
        logging.error(f"- Check network connectivity to OTP server")
        logging.error(f"- Check if OTP server has GraphQL API enabled")
                
        # Return None to indicate failure, no fallback to avoid incorrect data
        return None
    
    def get_stop_predictions(self, stop_id: str):
        """
        Fetches stop departure predictions from the Metlink API for a given stop ID.
        """
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
            return None