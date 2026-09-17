import os
from dotenv import load_dotenv

# Paths to potential .env locations
CORE_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CORE_DIR, "..", ".."))

ROOT_ENV = os.path.join(PROJECT_ROOT, ".env")
CORE_ENV = os.path.join(CORE_DIR, ".env")

def load_config():
    """Loads environment variables from .env file (root or core directory)."""
    if os.path.exists(ROOT_ENV):
        load_dotenv(ROOT_ENV)
    elif os.path.exists(CORE_ENV):
        load_dotenv(CORE_ENV)
    else:
        # Fallback to default load_dotenv behavior
        load_dotenv()
    
# Initialize config on module import
load_config()

