"""Camera abstraction.

Importing this module and constructing Camera() touch no hardware. The camera
only opens on start(), and start() reports failure cleanly (missing opencv, no
camera, no permission) instead of raising. Face/blink/gaze detection are NOT
here yet — this is only the capture boundary.
"""

import threading

try:
    import cv2
except Exception:
    cv2 = None


class Camera:
    def __init__(self, index: int = 0):
        self.index = index
        self._cap = None
        self._frame = None
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._status = "NOT INITIALIZED"

    def start(self) -> bool:
        if cv2 is None:
            self._status = "ERROR: opencv not installed"
            return False

        cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            cap.release()
            self._status = "ERROR: camera unavailable"
            return False

        self._cap = cap
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._status = "RUNNING"
        return True

    def _loop(self):
        while self._running:
            ok, frame = self._cap.read()
            if ok:
                with self._lock:
                    self._frame = frame

    def frame(self):
        with self._lock:
            return self._frame

    def stop(self):
        self._running = False
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._status = "STOPPED"

    def status(self) -> str:
        return self._status
