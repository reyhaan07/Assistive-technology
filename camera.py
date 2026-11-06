"""Camera capture + MediaPipe hand tracking running in a background thread."""
import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from config import (
    AUTO_LEARN,
    AUTO_LEARN_INTERVAL_SECONDS,
    AUTO_LEARN_MIN_NOVELTY,
    MAX_SAMPLES_PER_GESTURE,
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
from collections import deque

from eyes import BlinkDetector, face_ear
from gestures import GestureSmoother, GestureStore, classify_builtin, normalize_landmarks


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
        self.auto_learn = AUTO_LEARN
        self.last_learn_time = 0.0
        self.learned_samples = 0
        self.last_recognised_landmarks: Optional[np.ndarray] = None

        # Eye tracking (only runs while an eye mode is active)
        self.eye_tracking = False
        self.face_mesh = None
        self.eye_error = ""
        self.blink_detector = BlinkDetector()
        self.blink_events: deque = deque(maxlen=50)
        self.blink_id = 0
        self.eye_status = {"face": False, "closed": False, "ear": None}
        self._open_camera()

    # -- eyes -----------------------------------------------------------------
    def set_eye_tracking(self, enabled: bool) -> None:
        if enabled and self.face_mesh is None:
            try:
                self.face_mesh = _load_face_mesh()
            except Exception as exc:
                self.eye_error = str(exc)
                print(f"[camera] Eye tracking unavailable: {exc}")
                return
        self.eye_tracking = enabled
        if not enabled:
            self.blink_detector.reset()
            with self.lock:
                self.eye_status = {"face": False, "closed": False, "ear": None}

    def process_eyes(self, rgb: np.ndarray, annotated: np.ndarray, now: float) -> None:
        results = self.face_mesh.process(rgb)
        status = {"face": False, "closed": False, "ear": None}
        event = None
        if results and results.multi_face_landmarks:
            face = results.multi_face_landmarks[0]
            pts = np.array([[lm.x, lm.y, lm.z] for lm in face.landmark], dtype=np.float32)
            pts[:, 0] *= annotated.shape[1]  # pixel space keeps the eye's aspect ratio
            pts[:, 1] *= annotated.shape[0]
            ear = face_ear(pts)
            event = self.blink_detector.update(ear, now)
            status = {"face": True, "closed": self.blink_detector.closed, "ear": round(ear, 3)}
            colour = (60, 60, 230) if status["closed"] else (80, 220, 120)
            label = "EYES CLOSED" if status["closed"] else "EYES OPEN"
            cv2.putText(annotated, label, (10, annotated.shape[0] - 14), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, colour, 2, cv2.LINE_AA)
        else:
            self.blink_detector.reset()

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

    def maybe_learn(self, stable: str, raw: str, landmarks: Optional[np.ndarray],
                    dist: Optional[float], now: float) -> bool:
        """Self-improvement: store confident recognitions as extra samples."""
        if not self.auto_learn or stable == "none" or raw != stable or landmarks is None:
            return False
        if now - self.last_learn_time < AUTO_LEARN_INTERVAL_SECONDS:
            return False
        confident = dist is None or dist < RECOGNITION_THRESHOLD * 0.6
        if not confident:
            return False
        self.last_learn_time = now
        if self.gesture_store.learn_sample(stable, landmarks, AUTO_LEARN_MIN_NOVELTY,
                                           MAX_SAMPLES_PER_GESTURE):
            self.learned_samples += 1
            return True
        return False

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

            if self.eye_tracking and self.face_mesh is not None:
                self.process_eyes(rgb, annotated, time.time())

            stable = self.smoother.update(raw_name)
            if stable != "none" and raw_name == stable and landmarks is not None:
                with self.lock:
                    self.last_recognised_landmarks = landmarks
                self.maybe_learn(stable, raw_name, landmarks, dist, time.time())
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
