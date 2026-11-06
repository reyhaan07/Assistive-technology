"""Exercise the camera pipeline with MediaPipe and the webcam stubbed out."""
import threading
import time
from types import SimpleNamespace

import numpy as np

import camera as camera_mod
from gestures import GestureStore
from tests.hands import make_hand


class FakeCapture:
    def __init__(self, index):
        self.opened = index == 0

    def isOpened(self):
        return self.opened

    def set(self, *args):
        pass

    def read(self):
        return True, np.zeros((480, 640, 3), dtype=np.uint8)

    def release(self):
        pass


class FakeHands:
    def __init__(self, **kwargs):
        pts = make_hand(thumb="up")
        self.result = SimpleNamespace(
            multi_hand_landmarks=[SimpleNamespace(landmark=[SimpleNamespace(x=p[0], y=p[1], z=p[2]) for p in pts])],
            multi_handedness=[SimpleNamespace(classification=[SimpleNamespace(label="Right")])],
        )

    def process(self, rgb):
        return self.result


def make_processor(monkeypatch, tmp_path, index=0):
    fake_hands_module = SimpleNamespace(Hands=FakeHands, HAND_CONNECTIONS=[])
    fake_drawing = SimpleNamespace(draw_landmarks=lambda *a, **k: None)
    monkeypatch.setattr(camera_mod, "_load_mediapipe_hands", lambda: (fake_hands_module, fake_drawing))
    monkeypatch.setattr(camera_mod.cv2, "VideoCapture", FakeCapture)
    return camera_mod.CameraProcessor(GestureStore(str(tmp_path / "g.json")), camera_index=index)


def test_pipeline_recognises_builtin_gesture(monkeypatch, tmp_path):
    proc = make_processor(monkeypatch, tmp_path)
    threading.Thread(target=proc.process_camera_loop, daemon=True).start()
    deadline = time.time() + 3
    while time.time() < deadline and proc.get_recognition()[0] == "none":
        time.sleep(0.05)
    assert proc.get_recognition()[0] == "thumbs_up"
    landmarks, frame_id = proc.get_latest_landmarks_with_id()
    assert landmarks.shape == (21, 3) and frame_id > 0
    chunk = next(proc.generate_mjpeg_stream())
    assert chunk.startswith(b"--frame") and b"image/jpeg" in chunk


def test_missing_camera_does_not_crash(monkeypatch, tmp_path):
    proc = make_processor(monkeypatch, tmp_path, index=5)
    assert proc.camera_ok is False
    chunk = next(proc.generate_mjpeg_stream())  # placeholder frame is streamed
    assert chunk.startswith(b"--frame")
