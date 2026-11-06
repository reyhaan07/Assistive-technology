"""GestureTalk – Flask server tying camera, recognition, phrases and speech together."""
import re
import threading
import time
from collections import deque
from typing import Optional

from flask import Flask, Response, jsonify, render_template, request

from config import (
    CAPTURE_SAMPLES,
    CAPTURE_TIMEOUT_SECONDS,
    CONTEXTS,
    DEFAULT_CONTEXT,
    ENABLE_BUILTIN_GESTURES,
    HISTORY_SIZE,
    HOST,
    PORT,
    REPEAT_SPEECH_SECONDS,
    SPEECH_COOLDOWN_SECONDS,
)
from gestures import BUILTIN_GESTURES, GestureStore
from phrases import PhraseBook

WAITING = "Waiting for gesture..."
NAME_RE = re.compile(r"^[a-z0-9_]{1,40}$")


def clean_gesture_name(raw) -> str:
    name = re.sub(r"\s+", "_", str(raw or "").strip().lower())
    return name if NAME_RE.match(name) else ""


class Announcer:
    """Decides when a recognised gesture should be spoken.

    A gesture is spoken when it first appears (or the context changes) and again
    every `repeat_seconds` while it is held. Dropping the hand resets it.
    """

    def __init__(self, repeat_seconds: float = REPEAT_SPEECH_SECONDS):
        self.repeat_seconds = repeat_seconds
        self.last_key: Optional[str] = None
        self.last_time = 0.0

    def should_announce(self, gesture: str, context: str, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        if gesture == "none":
            self.last_key = None
            return False
        key = f"{context}:{gesture}"
        if key != self.last_key or now - self.last_time >= self.repeat_seconds:
            self.last_key, self.last_time = key, now
            return True
        return False


class GestureTalk:
    def __init__(self, camera, tts, store: GestureStore, phrases: PhraseBook):
        self.camera = camera
        self.tts = tts
        self.store = store
        self.phrases = phrases
        self.announcer = Announcer()

        self.state_lock = threading.Lock()
        self.state = {"context": DEFAULT_CONTEXT, "gesture": "none", "phrase": WAITING}
        self.history: deque = deque(maxlen=HISTORY_SIZE)
        self.speech_id = 0

        self.capture_lock = threading.Lock()
        self.captured_samples = []

    # -- speech -------------------------------------------------------------
    def announce(self, phrase: str, gesture: str, context: str, source: str = "gesture") -> dict:
        with self.state_lock:
            self.speech_id += 1
            entry = {"id": self.speech_id, "time": time.strftime("%H:%M:%S"),
                     "gesture": gesture, "context": context, "phrase": phrase, "source": source}
            self.history.appendleft(entry)
        self.tts.speak(phrase)
        return entry

    # -- recognition --------------------------------------------------------
    def step(self, now: Optional[float] = None) -> None:
        gesture, _ = self.camera.get_recognition()
        with self.state_lock:
            context = self.state["context"]
        phrase = WAITING if gesture == "none" else self.phrases.get(gesture, context)

        with self.state_lock:
            self.state["gesture"] = gesture
            self.state["phrase"] = phrase

        if self.announcer.should_announce(gesture, context, now):
            self.announce(phrase, gesture, context)

    def recognition_loop(self) -> None:
        while True:
            try:
                self.step()
            except Exception as exc:  # keep the loop alive
                print(f"[recognition] {exc}")
            time.sleep(0.05)

    # -- capture ------------------------------------------------------------
    def capture(self, samples: int, timeout: float) -> list:
        collected, last_id = [], -1
        deadline = time.time() + timeout
        while time.time() < deadline and len(collected) < samples:
            landmarks, frame_id = self.camera.get_latest_landmarks_with_id()
            if landmarks is not None and frame_id != last_id:
                collected.append(landmarks)
                last_id = frame_id
            time.sleep(0.08)
        with self.capture_lock:
            self.captured_samples = collected
        return collected

    def snapshot(self) -> dict:
        with self.state_lock:
            snap = dict(self.state)
            snap["history"] = list(self.history)
            snap["speech_id"] = self.speech_id
        snap["trained_gesture_count"] = self.store.count()
        snap["camera_ok"] = bool(getattr(self.camera, "camera_ok", True))
        snap["tts_available"] = bool(self.tts.available)
        snap["muted"] = bool(self.tts.muted)
        return snap

    def gesture_list(self) -> list:
        counts = self.store.sample_counts()
        builtin = BUILTIN_GESTURES if ENABLE_BUILTIN_GESTURES else []
        names = sorted(set(counts) | set(builtin))
        return [{
            "name": name,
            "samples": counts.get(name, 0),
            "builtin": name in builtin,
            "messages": self.phrases.messages_for(name),
        } for name in names]


def create_app(camera, tts, store: Optional[GestureStore] = None,
               phrases: Optional[PhraseBook] = None) -> Flask:
    app = Flask(__name__)
    talk = GestureTalk(camera, tts, store or GestureStore(), phrases or PhraseBook())
    app.config["TALK"] = talk

    def error(message, status=400):
        return jsonify({"error": message}), status

    @app.route("/")
    def index():
        return render_template("index.html", contexts=CONTEXTS)

    @app.route("/video_feed")
    def video_feed():
        return Response(camera.generate_mjpeg_stream(),
                        mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/get_state")
    def get_state():
        return jsonify(talk.snapshot())

    @app.route("/set_context", methods=["POST"])
    def set_context():
        data = request.get_json(silent=True) or {}
        context = str(data.get("context", "")).strip().lower()
        if context not in CONTEXTS:
            return error(f"Invalid context. Choose one of: {', '.join(CONTEXTS)}")
        with talk.state_lock:
            talk.state["context"] = context
        return jsonify({"context": context})

    @app.route("/capture_landmarks", methods=["GET", "POST"])
    def capture_landmarks():
        try:
            samples = int(request.args.get("samples", CAPTURE_SAMPLES))
        except ValueError:
            samples = CAPTURE_SAMPLES
        samples = max(1, min(samples, 20))
        collected = talk.capture(samples, CAPTURE_TIMEOUT_SECONDS)
        if not collected:
            return error("No hand detected. Hold your hand in front of the camera.")
        return jsonify({"message": "Gesture captured", "samples": len(collected)})

    @app.route("/train", methods=["POST"])
    def train():
        data = request.get_json(silent=True) or {}
        name = clean_gesture_name(data.get("gesture_name"))
        if not name:
            return error("Gesture name is required (letters, numbers, spaces or _; max 40).")

        with talk.capture_lock:
            samples = list(talk.captured_samples)
            talk.captured_samples = []
        if not samples:
            return error("No captured gesture. Capture the gesture first.")

        talk.store.add_samples(name, samples)
        messages = talk.phrases.set(name, data.get("messages"), keep_existing=True)
        return jsonify({"message": "Gesture trained", "gesture_name": name,
                        "samples_added": len(samples), "messages": messages})

    @app.route("/gestures")
    def list_gestures():
        return jsonify({"contexts": CONTEXTS, "gestures": talk.gesture_list()})

    @app.route("/gestures/<name>", methods=["DELETE"])
    def delete_gesture(name):
        name = clean_gesture_name(name)
        removed = talk.store.delete_gesture(name) if name else False
        if not removed:
            return error("Gesture not found", 404)
        talk.phrases.delete(name)
        return jsonify({"message": "Gesture deleted", "gesture_name": name})

    @app.route("/phrases/<name>", methods=["PUT", "POST"])
    def update_phrases(name):
        name = clean_gesture_name(name)
        if not name:
            return error("Invalid gesture name")
        data = request.get_json(silent=True) or {}
        messages = talk.phrases.set(name, data.get("messages"))
        return jsonify({"gesture_name": name, "messages": messages})

    @app.route("/speak", methods=["POST"])
    def speak():
        data = request.get_json(silent=True) or {}
        text = str(data.get("text", "")).strip()[:300]
        if not text:
            return error("Text is required")
        source = data.get("source") if data.get("source") in ("typed", "sos") else "typed"
        with talk.state_lock:
            context = talk.state["context"]
        return jsonify(talk.announce(text, source, context, source=source))

    @app.route("/set_mute", methods=["POST"])
    def set_mute():
        data = request.get_json(silent=True) or {}
        talk.tts.muted = bool(data.get("muted"))
        return jsonify({"muted": talk.tts.muted})

    return app


def main():
    from camera import CameraProcessor
    from tts import TTSManager

    store = GestureStore()
    camera = CameraProcessor(store)
    tts = TTSManager(cooldown_seconds=SPEECH_COOLDOWN_SECONDS)
    app = create_app(camera, tts, store=store)
    talk = app.config["TALK"]

    threading.Thread(target=camera.process_camera_loop, daemon=True).start()
    threading.Thread(target=talk.recognition_loop, daemon=True).start()

    print(f"GestureTalk running on http://localhost:{PORT}")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
