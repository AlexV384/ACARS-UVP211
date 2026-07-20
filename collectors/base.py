import re
from abc import ABC, abstractmethod
from typing import Any


_VALID_CALLSIGN = re.compile(r'^(?![0-9]+$)[A-Za-z0-9]{2,8}$')


def is_valid_callsign(callsign: str | None) -> bool:
    if not callsign:
        return False
    callsign = callsign.strip()
    return bool(_VALID_CALLSIGN.match(callsign))


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