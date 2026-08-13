"""Input events.

One small data structure for input, plus a simulated-event helper for
development and tests. In Stage 1 every event is SIMULATION; Stage 2's ocular
detection will produce the same InputEvent with source="ocular".
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

SIMULATION = "simulation"
OCULAR = "ocular"


class EventType(Enum):
    BLINK = "BLINK"      # activate the current target (ocular: intentional blink)
    SELECT = "SELECT"    # same as BLINK; explicit activate
    CONFIRM = "CONFIRM"
    REJECT = "REJECT"
    CANCEL = "CANCEL"
    LEFT = "LEFT"        # navigation only (never selects)
    RIGHT = "RIGHT"      # navigation only (never selects)


@dataclass
class InputEvent:
    type: EventType
    timestamp: float = field(default_factory=time.time)
    value: object = None
    source: str = SIMULATION


def sim_event(name: str) -> Optional[InputEvent]:
    """Build a simulated InputEvent from an event name, or None if unknown."""
    try:
        event_type = EventType[name]
    except KeyError:
        return None
    return InputEvent(event_type, source=SIMULATION)
