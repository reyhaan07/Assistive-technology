"""MediaPipe Face Mesh adapter.

The only mediapipe-dependent module. Import is guarded so the rest of the app
(and all pure-logic tests) run without mediapipe or opencv installed. Uses the
Face Mesh solutions API (refine_landmarks adds iris points for experimental
gaze). Returns pixel-space (x, y) landmarks so downstream geometry is correct.

Not exercised against a real face in this headless environment.
"""

try:
    import mediapipe as mp
except Exception:
    mp = None

try:
    import cv2
except Exception:
    cv2 = None


class FaceMesh:
    def __init__(self, refine=True):
        self.available = mp is not None and cv2 is not None
        self.refine = refine
        self._mesh = None

    def start(self):
        if not self.available:
            return False
        self._mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=self.refine,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        return True

    def landmarks(self, frame):
        """Return [(x_px, y_px), ...] for a BGR frame, or None if no face."""
        if self._mesh is None:
            return None
        height, width = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._mesh.process(rgb)
        if not result.multi_face_landmarks:
            return None
        points = result.multi_face_landmarks[0].landmark
        return [(lm.x * width, lm.y * height) for lm in points]

    def stop(self):
        if self._mesh is not None:
            self._mesh.close()
            self._mesh = None
