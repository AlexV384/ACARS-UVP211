import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "acars"),
    "user": os.getenv("DB_USER", "acars"),
    "password": os.getenv("DB_PASSWORD", "acars"),
}

OPENSKY_USERNAME = os.getenv("OPENSKY_USERNAME", "")
OPENSKY_PASSWORD = os.getenv("OPENSKY_PASSWORD", "")

COLLECT_INTERVAL = int(os.getenv("COLLECT_INTERVAL", 300))

COLLECTORS = []