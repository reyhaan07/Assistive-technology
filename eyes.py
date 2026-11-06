"""Eye-blink detection and blink-pattern decoding.

Uses the Eye Aspect Ratio (EAR) of MediaPipe Face Mesh eyelid landmarks:
EAR = (|p2-p6| + |p3-p5|) / (2 |p1-p4|) drops sharply when the eye closes.
The "open eye" baseline adapts to each user, so no calibration is needed.
"""
from typing import Optional, Sequence

import numpy as np

from config import (
    BLINK_GROUP_GAP_SECONDS,
    EYE_CLOSED_RATIO,
    LONG_BLINK_SECONDS,
    MAX_BLINK_SECONDS,
    MIN_BLINK_SECONDS,
    VERY_LONG_BLINK_SECONDS,
)

# Face Mesh indices (p1..p6) for each eye
LEFT_EYE = (33, 160, 158, 133, 153, 144)
RIGHT_EYE = (362, 385, 387, 263, 373, 380)

EYE_MODES = ("off", "patterns", "board")
# Blink "gestures" that patterns mode can speak (phrases live in PhraseBook)
EYE_GESTURES = ["blink_x2", "blink_x3", "long_blink"]


def eye_aspect_ratio(points: np.ndarray, idx: Sequence[int]) -> float:
    p1, p2, p3, p4, p5, p6 = (points[i][:2] for i in idx)
    width = np.linalg.norm(p1 - p4)
    if width < 1e-6:
        return 0.0
    return float((np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)) / (2.0 * width))


def face_ear(points: np.ndarray) -> float:
    """Average EAR of both eyes for a (468+, 3) landmark array."""
    return (eye_aspect_ratio(points, LEFT_EYE) + eye_aspect_ratio(points, RIGHT_EYE)) / 2.0


def ear_from_eye_points(points: np.ndarray) -> float:
    """EAR from 12 points: LEFT_EYE p1..p6 followed by RIGHT_EYE p1..p6 (pixel coords)."""
    pts = np.asarray(points, dtype=np.float32)
    idx = (0, 1, 2, 3, 4, 5)
    return (eye_aspect_ratio(pts[:6], idx) + eye_aspect_ratio(pts[6:], idx)) / 2.0


class BlinkDetector:
    """Turns a stream of EAR values into 'short' / 'long' / 'very_long' blink events."""

    def __init__(self, closed_ratio: float = EYE_CLOSED_RATIO,
                 long_seconds: float = LONG_BLINK_SECONDS,
                 very_long_seconds: float = VERY_LONG_BLINK_SECONDS,
                 min_seconds: float = MIN_BLINK_SECONDS,
                 max_seconds: float = MAX_BLINK_SECONDS):
        self.closed_ratio = closed_ratio
        self.long_seconds = long_seconds
        self.very_long_seconds = very_long_seconds
        self.min_seconds = min_seconds
        self.max_seconds = max_seconds
        self.baseline: Optional[float] = None
        self.closed = False
        self.closed_since = 0.0
        self.last_ear = 0.0

    @property
    def threshold(self) -> float:
        return (self.baseline or 0.3) * self.closed_ratio

    def reset(self) -> None:
        self.closed = False

    def update(self, ear: float, now: float) -> Optional[dict]:
        self.last_ear = ear
        if self.baseline is None:
            self.baseline = ear
            return None

        if not self.closed:
            if ear < self.threshold:
                self.closed, self.closed_since = True, now
            else:  # learn the open-eye level slowly
                self.baseline = 0.95 * self.baseline + 0.05 * ear
            return None

        if ear < self.threshold * 1.1:  # small hysteresis
            return None

        self.closed = False
        duration = now - self.closed_since
        if duration < self.min_seconds or duration > self.max_seconds:
            return None  # noise, or eyes simply shut (resting / looking down)
        if duration >= self.very_long_seconds:
            kind = "very_long"
        elif duration >= self.long_seconds:
            kind = "long"
        else:
            kind = "short"
        return {"kind": kind, "duration": round(duration, 2), "time": now}


class BlinkPatternDecoder:
    """Groups blink events into patterns.

    * very long blink (~2 s)   -> "open_board" (switch to the blink board)
    * long blink               -> "long_blink" (immediately)
    * 2 quick blinks in a row  -> "blink_x2"
    * 3 quick blinks in a row  -> "blink_x3"
    A single blink is ignored, since people blink naturally all the time.
    """

    def __init__(self, gap_seconds: float = BLINK_GROUP_GAP_SECONDS):
        self.gap_seconds = gap_seconds
        self.count = 0
        self.last_time = 0.0

    def feed(self, event: dict) -> Optional[str]:
        if event["kind"] in ("long", "very_long"):
            self.count = 0
            return "open_board" if event["kind"] == "very_long" else "long_blink"
        if self.count and event["time"] - self.last_time > self.gap_seconds:
            self.count = 0
        self.count += 1
        self.last_time = event["time"]
        return None

    def tick(self, now: float) -> Optional[str]:
        if self.count and now - self.last_time > self.gap_seconds:
            count, self.count = self.count, 0
            if count == 2:
                return "blink_x2"
            if count >= 3:
                return "blink_x3"
        return None
