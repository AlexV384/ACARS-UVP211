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

OPENSKY_CLIENT_ID = os.getenv("OPENSKY_CLIENT_ID", "")
OPENSKY_CLIENT_SECRET = os.getenv("OPENSKY_CLIENT_SECRET", "")

COLLECT_INTERVAL = int(os.getenv("COLLECT_INTERVAL", 300))

COLLECTORS = []

AIRLINE_ICAO_CODES = [
    "AFL",  # Аэрофлот
    "PBD",  # Победа
    "SBI",  # S7 Airlines
    "SDM",  # Россия
    "SVR",  # Уральские авиалинии
    "UTA",  # Utair
    "NWS",  # Nordwind
    "AUL",  # Smartavia
    "RWZ",  # Red Wings
    "AZO",  # Азимут
    "THY",  # Turkish Airlines
    "UAE",  # Emirates
    "QTR",  # Qatar Airways
    "ETD",  # Etihad Airways
    "CCA",  # Air China
    "CSN",  # China Southern Airlines
    "MSR",  # EgyptAir
    "ETH",  # Ethiopian Airlines
    "ELY",  # El Al
    "HVN",  # Vietnam Airlines
]

AIRLINE_IATA_CODES = [
    "SU",  # Аэрофлот
    "DP",  # Победа
    "S7",  # S7 Airlines
    "FV",  # Россия
    "U6",  # Уральские авиалинии
    "UT",  # Utair
    "N4",  # Nordwind
    "5N",  # Smartavia
    "WZ",  # Red Wings
    "A4",  # Азимут
    "TK",  # Turkish Airlines
    "EK",  # Emirates
    "QR",  # Qatar Airways
    "EY",  # Etihad Airways
    "CA",  # Air China
    "CZ",  # China Southern Airlines
    "MS",  # EgyptAir
    "ET",  # Ethiopian Airlines
    "LY",  # El Al
    "VN",  # Vietnam Airlines
]