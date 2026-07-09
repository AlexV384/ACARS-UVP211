from abc import ABC, abstractmethod
from typing import Any


class RawTrack:
    icao24: str
    callsign: str
    latitude: float
    longitude: float
    altitude: float | None
    velocity: float | None
    track_timestamp: Any
    source: str


class BaseCollector(ABC):

    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def fetch(self) -> list[RawTrack]:
        ...