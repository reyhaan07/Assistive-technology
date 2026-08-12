"""Ocular input source.

Owns the processing pipeline and turns a physical intentional blink into the
SAME InputEvent the simulation uses:

    camera frame -> face landmarks -> eye EAR -> blink detector -> InputEvent(BLINK, source="ocular")

The camera owns frame acquisition; this owns processing (one processing thread).
Only INTENTIONAL blinks are forwarded as commands — natural blinks are counted
for debug but never sent downstream, so ordinary blinking does not drive the
system. The blink never touches TTS: it goes to on_event (the controller), which
keeps the Stage 1 safety boundary intact.
"""

import threading
import time

import config
import storage
from events import OCULAR, EventType, InputEvent
from vision.blink import BlinkDetector, BlinkParams
from vision.calibration import Calibrator
from vision.eyes import LEFT_EYE, RIGHT_EYE, both_ears
from vision.gaze import direction as gaze_direction
from vision.reliability import Reliability

try:
    import cv2
except Exception:
    cv2 = None

CALIBRATION_FILE = "calibration.json"


def default_params():
    return BlinkParams(
        open_thresh=config.EAR_OPEN_THRESHOLD,
        close_thresh=config.EAR_CLOSE_THRESHOLD,
        min_close=config.BLINK_MIN_CLOSE_SECONDS,
        max_close=config.BLINK_MAX_CLOSE_SECONDS,
        intentional_min=config.INTENTIONAL_BLINK_SECONDS,
        cooldown=config.BLINK_COOLDOWN_SECONDS,
    )


def params_from_dict(data):
    return BlinkParams(
        open_thresh=data["open_thresh"],
        close_thresh=data["close_thresh"],
        min_close=data["min_close"],
        max_close=data["max_close"],
        intentional_min=data["intentional_min"],
        cooldown=data["cooldown"],
    )


def load_params():
    saved = storage.load(CALIBRATION_FILE)
    return params_from_dict(saved) if saved else default_params()


class OcularInput:
    def __init__(self, camera, face, on_event, params=None, fps=None):
        self.camera = camera
        self.face = face
        self.on_event = on_event
        self.blink = BlinkDetector(params or load_params())
        self.reliability = Reliability(window=config.RELIABILITY_WINDOW)
        self.fps = fps or config.OCULAR_FPS

        self.debug = False
        self.calibrator = None
        self.calibrated = storage.load(CALIBRATION_FILE) is not None

        self.face_state = "FACE_NOT_FOUND"
        self.ear = None
        self.gaze = None
        self.natural_blinks = 0
        self.intentional_blinks = 0

        self._running = False
        self._thread = None
        self._annotated = None
        self._lock = threading.Lock()

    # --- lifecycle ---
    def start(self):
        if not self.camera.start():
            return False
        self.face.start()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        self.face.stop()
        self.camera.stop()

    def running(self):
        return self._running

    # --- processing ---
    def _loop(self):
        delay = 1.0 / self.fps
        while self._running:
            frame = self.camera.frame()
            if frame is None:
                time.sleep(delay)
                continue
            self._process(frame, time.time())
            time.sleep(delay)

    def _process(self, frame, t):
        landmarks = self.face.landmarks(frame)
        face_present = landmarks is not None
        ears = both_ears(landmarks) if face_present else None
        eyes_valid = ears is not None
        ear = (ears[0] + ears[1]) / 2.0 if eyes_valid else None
        self.gaze = gaze_direction(landmarks) if face_present else None
        self.update(ear, face_present, eyes_valid, t)
        if self.debug:
            self._annotate(frame, landmarks, ear)

    def update(self, ear, face_present, eyes_valid, t):
        """Run one metrics step. Public so tests can drive it without a camera."""
        self.face_state = "FACE_FOUND" if face_present else "FACE_NOT_FOUND"
        self.ear = round(ear, 3) if ear is not None else None
        self.reliability.update(face_present, eyes_valid)

        gate = face_present and eyes_valid
        if self.calibrator is not None:
            if gate:
                self.calibrator.feed(ear, t, True)
            return

        blink = self.blink.update(ear if gate else 0.0, t, gate)
        if not blink:
            return
        if blink.kind == "intentional":
            self.intentional_blinks += 1
            self.on_event(InputEvent(EventType.BLINK, source=OCULAR))
        else:
            self.natural_blinks += 1

    # --- calibration ---
    def begin_calibration(self, phase):
        if self.calibrator is None:
            self.calibrator = Calibrator()
        self.calibrator.start(phase)

    def calibration_counts(self):
        return self.calibrator.counts() if self.calibrator else {}

    def finish_calibration(self):
        result = self.calibrator.finish()
        if result.ok:
            storage.save(CALIBRATION_FILE, result.params)
            self.blink = BlinkDetector(params_from_dict(result.params))
            self.calibrated = True
        self.calibrator = None
        return result

    # --- debug / status ---
    def set_debug(self, on):
        self.debug = bool(on)

    def status(self):
        return {
            "face": self.face_state,
            "ear": self.ear,
            "blink_phase": self.blink.phase.value,
            "reliability": self.reliability.status(),
            "gaze": self.gaze,
            "natural_blinks": self.natural_blinks,
            "intentional_blinks": self.intentional_blinks,
            "calibrated": self.calibrated,
            "calibrating": self.calibrator is not None,
        }

    def _annotate(self, frame, landmarks, ear):
        if cv2 is None:
            return
        annotated = frame.copy()
        if landmarks is not None:
            for i in LEFT_EYE + RIGHT_EYE:
                x, y = landmarks[i]
                cv2.circle(annotated, (int(x), int(y)), 2, (0, 255, 0), -1)
        lines = [
            f"EAR: {ear:.3f}" if ear is not None else "EAR: -",
            f"Blink: {self.blink.phase.value}",
            f"Input: {self.reliability.status()}",
            f"Face: {self.face_state}",
        ]
        for row, text in enumerate(lines):
            cv2.putText(annotated, text, (8, 20 + row * 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        with self._lock:
            self._annotated = annotated

    def mjpeg(self):
        """Yield annotated (debug) or raw frames as an MJPEG stream."""
        if cv2 is None:
            return
        while self._running:
            with self._lock:
                frame = self._annotated if self.debug and self._annotated is not None else self.camera.frame()
            if frame is None:
                time.sleep(0.05)
                continue
            ok, buffer = cv2.imencode(".jpg", frame)
            if ok:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
            time.sleep(1.0 / self.fps)
