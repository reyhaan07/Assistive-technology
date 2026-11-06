"""Landmark normalisation, trained-gesture storage/matching and built-in gestures."""
import json
import os
import threading
from collections import deque
from typing import Dict, List, Optional, Tuple

import numpy as np

from config import GESTURES_FILE

# MediaPipe hand landmark indices
WRIST = 0
THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 1, 2, 3, 4
FINGERS = {  # name: (mcp, pip, dip, tip)
    "index": (5, 6, 7, 8),
    "middle": (9, 10, 11, 12),
    "ring": (13, 14, 15, 16),
    "pinky": (17, 18, 19, 20),
}

BUILTIN_GESTURES = ["thumbs_up", "thumbs_down", "stop", "peace", "point", "fist"]


def landmarks_to_array(hand_landmarks) -> np.ndarray:
    """Accept a MediaPipe landmark list or anything array-like of shape (21, 3)."""
    if hasattr(hand_landmarks, "landmark"):
        return np.array([[lm.x, lm.y, lm.z] for lm in hand_landmarks.landmark], dtype=np.float32)
    return np.asarray(hand_landmarks, dtype=np.float32)


def normalize_landmarks(hand_landmarks, handedness: Optional[str] = None) -> np.ndarray:
    """Translate to the wrist, scale to unit size and mirror left hands.

    Mirroring makes a gesture trained with one hand recognisable with the other.
    """
    coords = landmarks_to_array(hand_landmarks).copy()
    if handedness and handedness.lower() == "left":
        coords[:, 0] = 1.0 - coords[:, 0]

    centered = coords - coords[WRIST]
    max_dist = float(np.max(np.linalg.norm(centered, axis=1)))
    if max_dist < 1e-6:
        return centered
    return centered / max_dist


def gesture_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.linalg.norm(a - b, axis=1)))


# ---------------------------------------------------------------------------
# Built-in, rule based gestures (work without any training)
# ---------------------------------------------------------------------------
def _dist(c: np.ndarray, i: int, j: int) -> float:
    return float(np.linalg.norm(c[i] - c[j]))


def finger_states(c: np.ndarray) -> Dict[str, bool]:
    """Return which fingers are extended for a (21, 3) landmark array."""
    states = {}
    for name, (_mcp, pip, _dip, tip) in FINGERS.items():
        states[name] = _dist(c, WRIST, tip) > _dist(c, WRIST, pip) * 1.15

    palm = max(_dist(c, WRIST, 9), 1e-6)
    v1 = c[THUMB_IP] - c[THUMB_MCP]
    v2 = c[THUMB_TIP] - c[THUMB_IP]
    denom = float(np.linalg.norm(v1) * np.linalg.norm(v2)) or 1e-6
    straight = float(np.dot(v1, v2)) / denom > 0.6
    away = _dist(c, THUMB_TIP, 9) > 0.55 * palm
    states["thumb"] = straight and away
    return states


def classify_builtin(landmarks: np.ndarray) -> Optional[str]:
    """Classify a normalised (or raw) landmark array into a built-in gesture."""
    c = np.asarray(landmarks, dtype=np.float32)
    if c.shape != (21, 3):
        return None

    s = finger_states(c)
    idx, mid, ring, pinky, thumb = s["index"], s["middle"], s["ring"], s["pinky"], s["thumb"]
    n_fingers = sum([idx, mid, ring, pinky])

    if n_fingers == 4:
        return "stop"
    if idx and mid and not ring and not pinky:
        return "peace"
    if idx and not mid and not ring and not pinky:
        return "point"
    if n_fingers == 0:
        knuckle_ys = c[[6, 10, 14, 18], 1]
        palm = max(_dist(c, WRIST, 9), 1e-6)
        if thumb and c[THUMB_TIP, 1] < knuckle_ys.min() - 0.15 * palm:
            return "thumbs_up"
        if thumb and c[THUMB_TIP, 1] > knuckle_ys.max() + 0.15 * palm:
            return "thumbs_down"
        if not thumb:
            return "fist"
    return None


# ---------------------------------------------------------------------------
# Trained gestures
# ---------------------------------------------------------------------------
class GestureStore:
    """Thread-safe store of trained landmark samples, persisted to JSON."""

    def __init__(self, file_path: str = GESTURES_FILE):
        self._gestures: Dict[str, List[np.ndarray]] = {}
        self.file_path = file_path
        self._lock = threading.RLock()
        self.load()

    def add_gesture(self, name: str, landmarks) -> None:
        self.add_samples(name, [landmarks])

    def add_samples(self, name: str, samples) -> None:
        name = name.lower().strip()
        with self._lock:
            bucket = self._gestures.setdefault(name, [])
            for sample in samples:
                bucket.append(np.asarray(sample, dtype=np.float32).copy())
            self.save()

    def delete_gesture(self, name: str) -> bool:
        with self._lock:
            removed = self._gestures.pop(name.lower().strip(), None) is not None
            if removed:
                self.save()
            return removed

    def names(self) -> List[str]:
        with self._lock:
            return sorted(self._gestures)

    def sample_counts(self) -> Dict[str, int]:
        with self._lock:
            return {name: len(samples) for name, samples in sorted(self._gestures.items())}

    def count(self) -> int:
        with self._lock:
            return sum(len(v) for v in self._gestures.values())

    def match(self, live_landmarks: np.ndarray, threshold: float) -> Tuple[str, Optional[float]]:
        with self._lock:
            if not self._gestures:
                return "none", None

            best_name, best_dist = "none", float("inf")
            for name, samples in self._gestures.items():
                for saved in samples:
                    dist = gesture_distance(live_landmarks, saved)
                    if dist < best_dist:
                        best_dist, best_name = dist, name

        if best_dist < threshold:
            return best_name, best_dist
        return "none", best_dist

    def save(self) -> None:
        with self._lock:
            data = {name: [lm.tolist() for lm in samples] for name, samples in self._gestures.items()}
        directory = os.path.dirname(self.file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = self.file_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, self.file_path)

    def load(self) -> None:
        if not os.path.exists(self.file_path):
            return
        try:
            with open(self.file_path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError) as exc:
            print(f"[gestures] Could not read {self.file_path}: {exc}")
            return

        with self._lock:
            self._gestures = {
                name: [np.array(lm, dtype=np.float32) for lm in samples]
                for name, samples in data.items()
                if samples
            }


class GestureSmoother:
    """Only report a gesture once it has been seen in `stable_frames` consecutive frames."""

    def __init__(self, stable_frames: int = 4):
        self.stable_frames = max(1, stable_frames)
        self._recent: deque = deque(maxlen=self.stable_frames)
        self.current = "none"

    def update(self, label: str) -> str:
        self._recent.append(label)
        if len(self._recent) == self.stable_frames and len(set(self._recent)) == 1:
            self.current = label
        return self.current
