"""Recognition shared by every camera source (server webcam or the user's browser).

Feed it hand landmarks + eye points for each frame; it handles gesture
matching, built-in gestures, smoothing, self-learning and blink detection.
No OpenCV / MediaPipe imports here, so it runs anywhere.
"""
import threading
import time
from collections import deque
from typing import Optional, Sequence, Tuple

import numpy as np

from config import (
    AUTO_LEARN,
    AUTO_LEARN_INTERVAL_SECONDS,
    AUTO_LEARN_MIN_NOVELTY,
    ENABLE_BUILTIN_GESTURES,
    MAX_SAMPLES_PER_GESTURE,
    RECOGNITION_THRESHOLD,
    STABLE_FRAMES,
)
from eyes import BlinkDetector
from gestures import BUILTIN_GESTURES, GestureSmoother, GestureStore, classify_builtin, normalize_landmarks


class Recognizer:
    camera_mode = "base"

    def __init__(self, gesture_store: GestureStore, builtin_enabled: bool = ENABLE_BUILTIN_GESTURES):
        self.gesture_store = gesture_store
        self.builtin_enabled = builtin_enabled
        self.lock = threading.Lock()
        self.camera_ok = False

        self.latest_landmarks: Optional[np.ndarray] = None
        self.frame_id = 0
        self.raw_gesture = "none"
        self.detected_gesture = "none"
        self.match_distance: Optional[float] = None
        self.smoother = GestureSmoother(STABLE_FRAMES)

        self.auto_learn = AUTO_LEARN
        self.last_learn_time = 0.0
        self.learned_samples = 0
        self.last_recognised_landmarks: Optional[np.ndarray] = None

        self.eye_tracking = False
        self.eye_error = ""
        self.blink_detector = BlinkDetector()
        self.blink_events: deque = deque(maxlen=50)
        self.blink_id = 0
        self.eye_status = {"face": False, "closed": False, "ear": None}

    # -- hands -------------------------------------------------------------------
    def recognise(self, landmarks: np.ndarray) -> Tuple[str, Optional[float]]:
        """Trained gestures first, built-in rules as fallback.

        A sample GestureTalk learned *by itself* can never overrule the built-in
        rules for a built-in gesture – only samples the user taught can.
        """
        detail = self.gesture_store.match_detail(landmarks, RECOGNITION_THRESHOLD)
        rule = classify_builtin(landmarks) if self.builtin_enabled else None
        name = detail["name"]
        if name != "none":
            if detail["auto"] and name in BUILTIN_GESTURES and rule and rule != name:
                return rule, None
            return name, detail["dist"]
        if rule:
            return rule, None
        return "none", detail["dist"]

    def maybe_learn(self, stable: str, raw: str, landmarks: Optional[np.ndarray],
                    dist: Optional[float], now: float) -> bool:
        """Self-improvement: store confident recognitions as extra samples."""
        if not self.auto_learn or stable == "none" or raw != stable or landmarks is None:
            return False
        if now - self.last_learn_time < AUTO_LEARN_INTERVAL_SECONDS:
            return False
        if stable in BUILTIN_GESTURES:
            # Only learn a built-in gesture when the rules agree – never reinforce a mistake.
            if classify_builtin(landmarks) != stable:
                return False
        elif dist is None or dist >= RECOGNITION_THRESHOLD * 0.6:
            return False
        self.last_learn_time = now
        if self.gesture_store.learn_sample(stable, landmarks, AUTO_LEARN_MIN_NOVELTY,
                                           MAX_SAMPLES_PER_GESTURE):
            self.learned_samples += 1
            return True
        return False

    def process_frame(self, hand_points=None, handedness: Optional[str] = None,
                      ear: Optional[float] = None, now: Optional[float] = None) -> str:
        """Process one frame. `hand_points`: 21x3 image coords of a mirrored (selfie) view."""
        now = time.time() if now is None else now
        raw_name, landmarks, dist = "none", None, None
        if hand_points is not None:
            landmarks = normalize_landmarks(hand_points, handedness)
            raw_name, dist = self.recognise(landmarks)

        stable = self.smoother.update(raw_name)
        if stable != "none" and raw_name == stable and landmarks is not None:
            with self.lock:
                self.last_recognised_landmarks = landmarks
            self.maybe_learn(stable, raw_name, landmarks, dist, now)

        if self.eye_tracking:
            self.process_ear(ear, now)

        with self.lock:
            self.latest_landmarks = landmarks
            self.frame_id += 1
            self.raw_gesture = raw_name
            self.detected_gesture = stable
            self.match_distance = dist
        return stable

    # -- eyes ----------------------------------------------------------------------
    def set_eye_tracking(self, enabled: bool) -> None:
        self.eye_tracking = enabled
        if not enabled:
            self.blink_detector.reset()
            with self.lock:
                self.eye_status = {"face": False, "closed": False, "ear": None}

    def process_ear(self, ear: Optional[float], now: float) -> None:
        event = None
        if ear is None:
            self.blink_detector.reset()
            status = {"face": False, "closed": False, "ear": None}
        else:
            event = self.blink_detector.update(ear, now)
            status = {"face": True, "closed": self.blink_detector.closed, "ear": round(ear, 3)}
        with self.lock:
            self.eye_status = status
            if event:
                self.blink_id += 1
                event["id"] = self.blink_id
                self.blink_events.append(event)

    def pop_blink_events(self) -> list:
        with self.lock:
            events = list(self.blink_events)
            self.blink_events.clear()
            return events

    def get_eye_status(self) -> dict:
        with self.lock:
            return dict(self.eye_status, enabled=self.eye_tracking, error=self.eye_error)

    # -- accessors -------------------------------------------------------------------
    def get_latest_landmarks(self) -> Optional[np.ndarray]:
        with self.lock:
            return None if self.latest_landmarks is None else self.latest_landmarks.copy()

    def get_latest_landmarks_with_id(self) -> Tuple[Optional[np.ndarray], int]:
        with self.lock:
            lm = None if self.latest_landmarks is None else self.latest_landmarks.copy()
            return lm, self.frame_id

    def get_recognition(self) -> Tuple[str, Optional[float]]:
        with self.lock:
            return self.detected_gesture, self.match_distance


def as_points(data: Optional[Sequence], n: int, dims: int) -> Optional[np.ndarray]:
    """Validate an incoming list of points; returns an (n, dims) float array or None."""
    if data is None:
        return None
    try:
        arr = np.asarray(data, dtype=np.float32)
    except (TypeError, ValueError):
        return None
    if arr.shape != (n, dims) or not np.all(np.isfinite(arr)):
        return None
    return arr
