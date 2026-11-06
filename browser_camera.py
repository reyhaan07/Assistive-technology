"""Camera source for when the *browser* owns the webcam.

The page runs MediaPipe (hand + face landmarks) on the user's own device and
POSTs only the landmark coordinates here – no video leaves the device. This
lets GestureTalk run on any server (or a laptop without the Python MediaPipe
package), as long as the person opens the page in a browser with a camera.
"""
import time

from eyes import ear_from_eye_points
from gestures import GestureSmoother
from recognizer import Recognizer, as_points

STALE_SECONDS = 3.0


class BrowserCamera(Recognizer):
    camera_mode = "browser"

    def __init__(self, gesture_store):
        super().__init__(gesture_store)
        self.last_frame_time = 0.0

    @property
    def camera_ok(self) -> bool:
        return time.time() - self.last_frame_time < STALE_SECONDS

    @camera_ok.setter
    def camera_ok(self, value) -> None:  # set by Recognizer.__init__; derived from frames instead
        pass

    def ingest(self, data: dict, now: float = None) -> dict:
        """One frame from the browser: {"hand": 21x[x,y,z] | null, "handedness", "eye": 12x[x,y] | null}."""
        now = time.time() if now is None else now
        if now - self.last_frame_time > STALE_SECONDS:
            # Camera (re)connected after a gap: forget what was seen before it.
            self.smoother = GestureSmoother(self.smoother.stable_frames)
            self.blink_detector.reset()
        self.last_frame_time = now
        hand = as_points(data.get("hand"), 21, 3)
        handedness = data.get("handedness") if data.get("handedness") in ("Left", "Right") else None
        eye = as_points(data.get("eye"), 12, 2)
        ear = ear_from_eye_points(eye) if eye is not None else None
        gesture = self.process_frame(hand, handedness, ear, now)
        return {"gesture": gesture}

    def get_recognition(self):
        """No recent frames (tab closed / camera stopped) means no gesture."""
        if not self.camera_ok:
            return "none", None
        return super().get_recognition()

    def get_eye_status(self) -> dict:
        status = super().get_eye_status()
        if not self.camera_ok:
            status.update(face=False, closed=False)
        return status

    def generate_mjpeg_stream(self):
        """Video stays in the browser; nothing to stream."""
        return iter(())
