"""Communication state machine + session.

One state variable is the single source of truth. Invalid transitions raise.
The only way to produce a ConfirmedMessage (the sole thing speech accepts) is
CommunicationSession.speak_confirmed(), which requires the READY_TO_SPEAK state
reached by an explicit user confirmation. This is how the architecture enforces:
unconfirmed message != speech.
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class State(Enum):
    IDLE = "IDLE"
    PREDICTING = "PREDICTING"
    PREDICTION_SHOWN = "PREDICTION_SHOWN"
    CONFIRM_MODE = "CONFIRM_MODE"
    CHOICE_MODE = "CHOICE_MODE"
    FALLBACK_MODE = "FALLBACK_MODE"
    READY_TO_SPEAK = "READY_TO_SPEAK"
    SPEAKING = "SPEAKING"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


# Allowed transitions. Anything not listed is rejected.
TRANSITIONS = {
    State.IDLE: {State.PREDICTING, State.FALLBACK_MODE, State.ERROR},
    State.PREDICTING: {State.PREDICTION_SHOWN, State.ERROR},
    State.PREDICTION_SHOWN: {
        State.CONFIRM_MODE, State.CHOICE_MODE, State.FALLBACK_MODE,
        State.REJECTED, State.CANCELLED, State.ERROR,
    },
    State.CONFIRM_MODE: {State.READY_TO_SPEAK, State.REJECTED, State.CANCELLED, State.ERROR},
    State.CHOICE_MODE: {State.READY_TO_SPEAK, State.REJECTED, State.CANCELLED, State.ERROR},
    State.FALLBACK_MODE: {State.READY_TO_SPEAK, State.CANCELLED, State.ERROR},
    # READY_TO_SPEAK -> FALLBACK_MODE lets the user cancel and keep editing.
    State.READY_TO_SPEAK: {State.SPEAKING, State.FALLBACK_MODE, State.CANCELLED, State.ERROR},
    State.SPEAKING: {State.IDLE, State.ERROR},
    State.REJECTED: {State.IDLE, State.ERROR},
    State.CANCELLED: {State.IDLE, State.ERROR},
    State.ERROR: {State.IDLE},
}


class InvalidTransition(Exception):
    pass


# Private key: only speak_confirmed() below can mint a ConfirmedMessage.
_confirm_key = object()


@dataclass(frozen=True)
class ConfirmedMessage:
    """A message the user explicitly confirmed. Speech accepts nothing else."""
    text: str
    key: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if self.key is not _confirm_key:
            raise PermissionError("ConfirmedMessage is created only by CommunicationSession.speak_confirmed()")


@dataclass
class CommunicationSession:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    state: State = State.IDLE
    start_time: float = field(default_factory=time.time)
    final_message: Optional[str] = None

    def can(self, target: State) -> bool:
        return target in TRANSITIONS[self.state]

    def to(self, target: State) -> None:
        if target not in TRANSITIONS[self.state]:
            raise InvalidTransition(f"{self.state.name} -> {target.name}")
        self.state = target

    def speak_confirmed(self, text: str) -> ConfirmedMessage:
        """Final explicit confirmation: READY_TO_SPEAK -> SPEAKING, mints the message."""
        if self.state != State.READY_TO_SPEAK:
            raise InvalidTransition(f"cannot speak from {self.state.name}")
        self.to(State.SPEAKING)
        self.final_message = text
        return ConfirmedMessage(text, _confirm_key)

    def reset(self) -> None:
        self.state = State.IDLE
        self.final_message = None
