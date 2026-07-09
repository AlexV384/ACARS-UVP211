from dataclasses import dataclass
from datetime import datetime


@dataclass
class Track:
    icao24: str
    callsign: str
    latitude: float
    longitude: float
    altitude: float | None
    velocity: float | None
    timestamp: datetime
    source: str