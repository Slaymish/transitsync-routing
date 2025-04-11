import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

class Config:
    """
    Configuration class for TransitSync Routing.
    This class loads configuration values from environment variables or uses default values.
    """
    # General configuration
    DEBUG = os.environ.get('DEBUG', 'False') == 'True'
    PORT = int(os.environ.get('PORT', 5000))

    # Timezone configuration
    TIMEZONE = os.environ.get('TIMEZONE', 'Pacific/Auckland')

    OTP_URL = os.environ.get('OTP_URL', 'http://localhost:8080')
    OSM_URL = os.environ.get('OSM_URL', 'https://nominatim.openstreetmap.org/search')