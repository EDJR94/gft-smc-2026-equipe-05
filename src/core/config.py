import os
from dotenv import load_dotenv

# Path to the .env file in the core directory
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")

def load_config():
    """Loads environment variables from .env file."""
    load_dotenv(ENV_PATH)
    
# Initialize config on module import
load_config()
