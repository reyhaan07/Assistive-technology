"""Camera capture + MediaPipe hand tracking running in a background thread."""
import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from config import (
    CAMERA_INDEX,
    ENABLE_BUILTIN_GESTURES,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    MAX_NUM_HANDS,
    MIN_DETECTION_CONFIDENCE,
    MIN_TRACKING_CONFIDENCE,
    RECOGNITION_THRESHOLD,
    STABLE_FRAMES,
)
from gestures import GestureSmoother, GestureStore, classify_builtin, normalize_landmarks


def _load_mediapipe_hands():
    try:
        import mediapipe as mp
    except ImportError as exc:
        raise RuntimeError("MediaPipe is not installed. Run: pip install -r requirements.txt") from exc

    if not hasattr(mp, "solutions"):
        raise RuntimeError(
            f"MediaPipe {getattr(mp, '__version__', '?')} no longer ships the 'solutions' API. "
            "Install the pinned version with: pip install -r requirements.txt "
            "(requires Python 3.9 - 3.12)."
        )
    return mp.solutions.hands, mp.solutions.drawing_utils


def placeholder_frame(message: str) -> np.ndarray:
    frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
    frame[:] = (40, 30, 20)
    y = FRAME_HEIGHT // 2 - 10
    for line in message.split("\n"):
        cv2.putText(frame, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 1, cv2.LINE_AA)
        y += 28
    return frame


class CameraProcessor:
    def __init__(self, gesture_store: GestureStore, camera_index: int = CAMERA_INDEX,
                 builtin_enabled: bool = ENABLE_BUILTIN_GESTURES):
        self.gesture_store = gesture_store
        self.camera_index = camera_index
        self.builtin_enabled = builtin_enabled

        self.mp_hands, self.mp_drawing = _load_mediapipe_hands()
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=MAX_NUM_HANDS,
            min_detection_confidence=MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=MIN_TRACKING_CONFIDENCE,
        )

        self.cap = None
        self.camera_ok = False
        self.lock = threading.Lock()
        self.latest_annotated_frame: Optional[np.ndarray] = placeholder_frame("Starting camera...")
        self.latest_landmarks: Optional[np.ndarray] = None
        self.frame_id = 0
        self.raw_gesture = "none"
        self.detected_gesture = "none"
        self.match_distance: Optional[float] = None
        self.smoother = GestureSmoother(STABLE_FRAMES)
        self._open_camera()

    def _open_camera(self) -> bool:
        if self.cap is not None:
            self.cap.release()
        self.cap = cv2.VideoCapture(self.camera_index)
        self.camera_ok = bool(self.cap.isOpened())
        if self.camera_ok:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        else:
            print(f"[camera] Unable to open camera index {self.camera_index}")
            with self.lock:
                self.latest_annotated_frame = placeholder_frame(
                    f"Camera {self.camera_index} unavailable\nRetrying...")
        return self.camera_ok

    def recognise(self, landmarks: np.ndarray) -> Tuple[str, Optional[float]]:
        """Trained gestures take priority; fall back to built-in shapes."""
        name, dist = self.gesture_store.match(landmarks, RECOGNITION_THRESHOLD)
        if name == "none" and self.builtin_enabled:
            builtin = classify_builtin(landmarks)
            if builtin:
                return builtin, None
        return name, dist

    def process_camera_loop(self):
        failures = 0
        while True:
            if not self.camera_ok:
                time.sleep(2.0)
                self._open_camera()
                continue

            ok, frame = self.cap.read()
            if not ok:
                failures += 1
                if failures > 50:
                    self.camera_ok = False
                    failures = 0
                time.sleep(0.02)
                continue
            failures = 0

            frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
            frame = cv2.flip(frame, 1)  # mirror for a selfie view
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb)
            annotated = frame

            raw_name, landmarks, dist = "none", None, None
            if results and results.multi_hand_landmarks:
                hand = results.multi_hand_landmarks[0]
                handedness = None
                if results.multi_handedness:
                    handedness = results.multi_handedness[0].classification[0].label
                landmarks = normalize_landmarks(hand, handedness)
                self.mp_drawing.draw_landmarks(annotated, hand, self.mp_hands.HAND_CONNECTIONS)
                raw_name, dist = self.recognise(landmarks)

            stable = self.smoother.update(raw_name)
            if stable != "none":
                cv2.putText(annotated, stable, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                            (80, 220, 120), 2, cv2.LINE_AA)

            with self.lock:
                self.latest_annotated_frame = annotated
                self.latest_landmarks = landmarks
                self.frame_id += 1
                self.raw_gesture = raw_name
                self.detected_gesture = stable
                self.match_distance = dist

            time.sleep(0.01)

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

    def generate_mjpeg_stream(self):
        while True:
            with self.lock:
                frame = None if self.latest_annotated_frame is None else self.latest_annotated_frame.copy()
            if frame is None:
                time.sleep(0.03)
                continue
            ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if ok:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            time.sleep(0.04)
