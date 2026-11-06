"""Server-side webcam + MediaPipe (Python) tracking running in a background thread.

Used when the computer running GestureTalk has the camera. When MediaPipe's
Python 'solutions' API is not available, GestureTalk switches to the browser
camera mode instead (see browser_camera.py).
"""
import time
from typing import Optional

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
)
from eyes import face_ear
from gestures import GestureStore, landmarks_to_array
from recognizer import Recognizer


def _load_mediapipe():
    import mediapipe as mp
    return mp


def _load_face_mesh():
    """Create a Face Mesh tracker (used for blink detection)."""
    mp = _load_mediapipe()
    return mp.solutions.face_mesh.FaceMesh(
        max_num_faces=1, refine_landmarks=False,
        min_detection_confidence=0.5, min_tracking_confidence=0.5)


def _load_mediapipe_hands():
    try:
        import mediapipe as mp
    except ImportError as exc:
        raise RuntimeError("MediaPipe is not installed. Run: pip install -r requirements.txt") from exc

    if not hasattr(mp, "solutions"):
        raise RuntimeError(
            f"MediaPipe {getattr(mp, '__version__', '?')} no longer ships the 'solutions' API "
            "(needs Python 3.9 - 3.12 with the pinned version)."
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


class CameraProcessor(Recognizer):
    camera_mode = "server"

    def __init__(self, gesture_store: GestureStore, camera_index: int = CAMERA_INDEX,
                 builtin_enabled: bool = ENABLE_BUILTIN_GESTURES):
        super().__init__(gesture_store, builtin_enabled)
        self.camera_index = camera_index
        self.mp_hands, self.mp_drawing = _load_mediapipe_hands()
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=MAX_NUM_HANDS,
            min_detection_confidence=MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=MIN_TRACKING_CONFIDENCE,
        )
        self.face_mesh = None
        self.cap = None
        self.latest_annotated_frame: Optional[np.ndarray] = placeholder_frame("Starting camera...")
        self._open_camera()

    def set_eye_tracking(self, enabled: bool) -> None:
        if enabled and self.face_mesh is None:
            try:
                self.face_mesh = _load_face_mesh()
            except Exception as exc:
                self.eye_error = str(exc)
                print(f"[camera] Eye tracking unavailable: {exc}")
                return
        super().set_eye_tracking(enabled)

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

    def _eye_ear(self, rgb: np.ndarray, annotated: np.ndarray) -> Optional[float]:
        results = self.face_mesh.process(rgb)
        if not (results and results.multi_face_landmarks):
            return None
        face = results.multi_face_landmarks[0]
        pts = np.array([[lm.x, lm.y, lm.z] for lm in face.landmark], dtype=np.float32)
        pts[:, 0] *= annotated.shape[1]  # pixel space keeps the eye's aspect ratio
        pts[:, 1] *= annotated.shape[0]
        return face_ear(pts)

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

            hand_points, handedness = None, None
            if results and results.multi_hand_landmarks:
                hand = results.multi_hand_landmarks[0]
                if results.multi_handedness:
                    handedness = results.multi_handedness[0].classification[0].label
                hand_points = landmarks_to_array(hand)
                self.mp_drawing.draw_landmarks(annotated, hand, self.mp_hands.HAND_CONNECTIONS)

            ear = None
            if self.eye_tracking and self.face_mesh is not None:
                ear = self._eye_ear(rgb, annotated)

            stable = self.process_frame(hand_points, handedness, ear, time.time())

            if stable != "none":
                cv2.putText(annotated, stable, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                            (80, 220, 120), 2, cv2.LINE_AA)
            if self.eye_tracking:
                status = self.get_eye_status()
                if status["face"]:
                    colour = (60, 60, 230) if status["closed"] else (80, 220, 120)
                    label = "EYES CLOSED" if status["closed"] else "EYES OPEN"
                    cv2.putText(annotated, label, (10, annotated.shape[0] - 14), cv2.FONT_HERSHEY_SIMPLEX,
                                0.6, colour, 2, cv2.LINE_AA)
            with self.lock:
                self.latest_annotated_frame = annotated
            time.sleep(0.01)

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
