"""Temporal blink detector.

A single low-EAR frame is never a blink. The detector walks a small state
machine OPEN -> CLOSING -> CLOSED -> OPENING and only emits when the eyes close
and reopen, with the closure lasting a sensible time. Natural vs intentional is
decided by closure duration (an intentional blink is held a little longer). A
cooldown stops one physical blink from firing twice. Losing the face aborts any
in-progress closure without emitting.

Thresholds/durations come from calibration (per user) or config defaults; they
are not hard-coded here.
"""

from dataclasses import dataclass
from enum import Enum


class Phase(Enum):
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    OPENING = "OPENING"


@dataclass
class BlinkParams:
    open_thresh: float      # EAR >= this -> eyes open
    close_thresh: float     # EAR <= this -> eyes closed (close < open = hysteresis)
    min_close: float        # closure shorter than this -> ignored (noise)
    max_close: float        # closure longer than this -> not a command blink
    intentional_min: float  # closure >= this -> intentional, else natural
    cooldown: float         # refractory period after a blink


@dataclass
class Blink:
    kind: str        # "natural" or "intentional"
    duration: float


class BlinkDetector:
    def __init__(self, params: BlinkParams):
        self.p = params
        self.phase = Phase.OPEN
        self._closed_start = None
        self._last_blink_t = float("-inf")

    def update(self, ear, t, face_present=True):
        """Feed one frame. Returns a Blink when a full blink completes, else None."""
        if not face_present:
            self.phase = Phase.OPEN
            self._closed_start = None
            return None

        p = self.p
        if self.phase == Phase.OPEN:
            if ear <= p.close_thresh:
                self._enter_closed(t)
            elif ear < p.open_thresh:
                self.phase = Phase.CLOSING
                self._closed_start = t
        elif self.phase == Phase.CLOSING:
            if ear <= p.close_thresh:
                self._enter_closed(self._closed_start or t)
            elif ear >= p.open_thresh:
                self.phase = Phase.OPEN
                self._closed_start = None
        elif self.phase == Phase.CLOSED:
            if ear >= p.open_thresh:
                return self._reopen(t)
            elif ear > p.close_thresh:
                self.phase = Phase.OPENING
        elif self.phase == Phase.OPENING:
            if ear >= p.open_thresh:
                return self._reopen(t)
            elif ear <= p.close_thresh:
                self.phase = Phase.CLOSED
        return None

    def _enter_closed(self, start_t):
        self.phase = Phase.CLOSED
        self._closed_start = start_t

    def _reopen(self, t):
        duration = t - self._closed_start if self._closed_start is not None else 0.0
        self.phase = Phase.OPEN
        self._closed_start = None

        p = self.p
        if duration < p.min_close or duration > p.max_close:
            return None
        if t - self._last_blink_t < p.cooldown:
            return None

        self._last_blink_t = t
        kind = "intentional" if duration >= p.intentional_min else "natural"
        return Blink(kind=kind, duration=duration)
