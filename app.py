"""GestureTalk – Flask server tying camera, recognition, phrases and speech together."""
import re
import threading
import time
from collections import deque
from typing import Optional

from flask import Flask, Response, jsonify, render_template, request

from config import (
    CERT_DIR,
    DEFAULT_EYE_MODE,
    MAX_LOCATION_ACCURACY_M,
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
from eyes import EYE_GESTURES, EYE_MODES, BlinkPatternDecoder
from geo import LocationTracker
from gestures import BUILTIN_GESTURES, GestureStore
from learning import UsageStats
from phrases import PhraseBook, humanize
from places import PROFILE_FIELDS, PlaceBook, resolve_tokens

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
    def __init__(self, camera, tts, store: GestureStore, phrases: PhraseBook,
                 places: PlaceBook, usage: UsageStats):
        self.camera = camera
        self.tts = tts
        self.store = store
        self.phrases = phrases
        self.places = places
        self.usage = usage
        self.announcer = Announcer()
        self.blink_decoder = BlinkPatternDecoder()

        self.state_lock = threading.Lock()
        self.state = {"context": DEFAULT_CONTEXT, "gesture": "none", "phrase": WAITING}
        self.history: deque = deque(maxlen=HISTORY_SIZE)
        self.speech_id = 0

        self.eye_mode = "off"
        self.last_blink = {"id": 0, "kind": None}
        self.last_pattern = None

        self.location = None        # last raw fix {"lat", "lon", "accuracy", "time"}
        self.current_place = None   # confirmed place dict when inside a saved place
        self.auto_context = True
        self.tracker = LocationTracker(places)
        self.gps_status = {"status": "no_fix"}

        self.capture_lock = threading.Lock()
        self.captured_samples = []
        self.set_eye_mode(DEFAULT_EYE_MODE)

    # -- phrases --------------------------------------------------------------
    def token_values(self, context: str) -> dict:
        with self.state_lock:
            place = self.current_place
        return {
            "usual": self.places.usual_for(context, place if place and place["context"] == context else None),
            "medical": self.places.medical_text(),
            "place": place["name"] if place else "",
            "name": self.places.profile().get("name", ""),
        }

    def render(self, text: str, context: str) -> str:
        if "{" not in text:
            return text
        return resolve_tokens(text, self.token_values(context))

    def phrase_for(self, gesture: str, context: str) -> str:
        return self.render(self.phrases.get(gesture, context), context)

    # -- speech -------------------------------------------------------------
    def announce(self, phrase: str, gesture: str, context: str, source: str = "gesture") -> dict:
        phrase = self.render(phrase, context)
        if source != "sos":
            self.usage.record(phrase, context)
        with self.state_lock:
            self.speech_id += 1
            entry = {"id": self.speech_id, "time": time.strftime("%H:%M:%S"),
                     "gesture": gesture, "context": context, "phrase": phrase, "source": source}
            self.history.appendleft(entry)
        self.tts.speak(phrase)
        return entry

    # -- recognition --------------------------------------------------------
    def set_eye_mode(self, mode: str) -> None:
        if mode not in EYE_MODES:
            raise ValueError(mode)
        self.eye_mode = mode
        if hasattr(self.camera, "set_eye_tracking"):
            self.camera.set_eye_tracking(mode != "off")

    def process_blinks(self, now: float, context: str) -> None:
        events = self.camera.pop_blink_events() if hasattr(self.camera, "pop_blink_events") else []
        patterns = []
        for event in events:
            with self.state_lock:
                self.last_blink = {"id": event.get("id", 0), "kind": event["kind"]}
            if self.eye_mode == "patterns":
                patterns.append(self.blink_decoder.feed(event))
        if self.eye_mode == "patterns":
            patterns.append(self.blink_decoder.tick(now))

        for pattern in filter(None, patterns):
            self.last_pattern = pattern
            if pattern == "open_board":
                self.eye_mode = "board"
                continue
            self.announce(self.phrases.get(pattern, context), pattern, context, source="blink")

    def step(self, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        gesture, _ = self.camera.get_recognition()
        with self.state_lock:
            context = self.state["context"]
        if self.eye_mode != "off":
            self.process_blinks(now, context)
        phrase = WAITING if gesture == "none" else self.phrase_for(gesture, context)

        with self.state_lock:
            self.state["gesture"] = gesture
            self.state["phrase"] = phrase

        if self.announcer.should_announce(gesture, context, now):
            self.announce(phrase, gesture, context)

    # -- GPS --------------------------------------------------------------------
    def update_location(self, lat: float, lon: float, accuracy: Optional[float],
                        now: Optional[float] = None) -> dict:
        """Feed one GPS fix. Place changes happen only once the tracker is certain."""
        now = time.time() if now is None else now
        accuracy = 9999.0 if accuracy is None else accuracy  # unknown accuracy = never decisive
        res = self.tracker.update(lat, lon, accuracy, now)
        with self.state_lock:
            self.location = {"lat": lat, "lon": lon, "accuracy": accuracy,
                             "time": time.strftime("%H:%M:%S"),
                             "weak": accuracy > MAX_LOCATION_ACCURACY_M}
            self.current_place = res["place"]
            if res["arrived"] and self.auto_context:
                self.state["context"] = res["place"]["context"]
            self.gps_status = {"status": res["status"], "confirming": res.get("confirming"),
                               "estimate": res.get("estimate")}
        return {"place": res["place"], "arrived": res["arrived"], "left": res["left"],
                "status": res["status"], "confirming": res.get("confirming"),
                "estimate": res.get("estimate")}

    def location_text(self) -> str:
        with self.state_lock:
            loc, place = self.location, self.current_place
        est = self.tracker.good_estimate()
        if est and est["fixes"] >= 2:  # smoothed position is more accurate than one raw fix
            loc = {"lat": est["lat"], "lon": est["lon"], "accuracy": est["accuracy"], "weak": False}
        if place:
            return f"I am at {place['name']}."
        if loc and loc.get("weak"):
            return (f"My approximate location is latitude {loc['lat']:.4f}, "
                    f"longitude {loc['lon']:.4f}, within {round(loc['accuracy'])} metres.")
        if loc:
            return f"My location is latitude {loc['lat']:.5f}, longitude {loc['lon']:.5f}."
        return ""

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
        snap["camera_mode"] = getattr(self.camera, "camera_mode", "server")
        snap["tts_available"] = bool(self.tts.available)
        snap["muted"] = bool(self.tts.muted)
        eye = self.camera.get_eye_status() if hasattr(self.camera, "get_eye_status") else {}
        with self.state_lock:
            snap["eye"] = dict(eye, mode=self.eye_mode, last_blink=dict(self.last_blink))
            snap["location"] = dict(self.location) if self.location else None
            snap["place"] = dict(self.current_place) if self.current_place else None
            snap["auto_context"] = self.auto_context
            snap["gps"] = dict(self.gps_status)
        snap["learned_samples"] = int(getattr(self.camera, "learned_samples", 0))
        snap["auto_learn"] = bool(getattr(self.camera, "auto_learn", False))
        return snap

    def gesture_list(self) -> list:
        counts = self.store.sample_counts()
        builtin = BUILTIN_GESTURES if ENABLE_BUILTIN_GESTURES else []
        names = sorted(set(counts) | set(builtin)) + EYE_GESTURES
        return [{
            "name": name,
            "samples": counts.get(name, 0),
            "builtin": name in builtin or name in EYE_GESTURES,
            "eye": name in EYE_GESTURES,
            "messages": self.phrases.messages_for(name),
        } for name in names]


def create_app(camera, tts, store: Optional[GestureStore] = None,
               phrases: Optional[PhraseBook] = None, places: Optional[PlaceBook] = None,
               usage: Optional[UsageStats] = None) -> Flask:
    app = Flask(__name__)
    talk = GestureTalk(camera, tts, store or GestureStore(), phrases or PhraseBook(),
                       places or PlaceBook(), usage or UsageStats())
    app.config["TALK"] = talk

    def error(message, status=400):
        return jsonify({"error": message}), status

    camera_mode = getattr(camera, "camera_mode", "server")

    @app.route("/")
    def index():
        from assets import TASKS_VISION_VERSION, assets_present
        return render_template("index.html", contexts=CONTEXTS, camera_mode=camera_mode,
                               local_vision=assets_present(), vision_version=TASKS_VISION_VERSION)

    @app.route("/landmarks", methods=["POST"])
    def landmarks():
        """Browser camera mode: one frame of hand / eye landmarks from the page."""
        if not hasattr(camera, "ingest"):
            return error("This server uses its own camera", 409)
        return jsonify(camera.ingest(request.get_json(silent=True) or {}))

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
        source = data.get("source") if data.get("source") in ("typed", "sos", "board") else "typed"
        with talk.state_lock:
            context = talk.state["context"]
        if source == "sos":
            extra = talk.location_text()
            text = f"{text} {extra}".strip()
        entry = talk.announce(text, source, context, source=source)
        if source == "sos":
            entry = dict(entry, location=talk.snapshot()["location"],
                         contact=talk.places.profile().get("emergency_phone", ""))
        return jsonify(entry)

    @app.route("/set_mute", methods=["POST"])
    def set_mute():
        data = request.get_json(silent=True) or {}
        talk.tts.muted = bool(data.get("muted"))
        return jsonify({"muted": talk.tts.muted})

    # -- eyes ---------------------------------------------------------------
    @app.route("/set_eye_mode", methods=["POST"])
    def set_eye_mode():
        mode = str((request.get_json(silent=True) or {}).get("mode", "")).lower()
        if mode not in EYE_MODES:
            return error(f"mode must be one of: {', '.join(EYE_MODES)}")
        talk.set_eye_mode(mode)
        eye = talk.snapshot()["eye"]
        return jsonify({"mode": talk.eye_mode, "error": eye.get("error", "")})

    # -- learning / correction -------------------------------------------------
    @app.route("/correct", methods=["POST"])
    def correct():
        """'That was wrong, it was X': store the last hand pose as gesture X."""
        name = clean_gesture_name((request.get_json(silent=True) or {}).get("gesture_name"))
        if not name:
            return error("gesture_name is required")
        landmarks = getattr(camera, "last_recognised_landmarks", None)
        if landmarks is None and hasattr(camera, "get_latest_landmarks"):
            landmarks = camera.get_latest_landmarks()
        if landmarks is None:
            return error("No recent hand pose to learn from")
        talk.store.add_samples(name, [landmarks] * 3)  # weight corrections strongly
        if not talk.phrases.has(name):
            talk.phrases.set(name, {})
        return jsonify({"message": f"Learned: that pose means {humanize(name)}", "gesture_name": name})

    @app.route("/set_auto_learn", methods=["POST"])
    def set_auto_learn():
        camera.auto_learn = bool((request.get_json(silent=True) or {}).get("enabled"))
        return jsonify({"auto_learn": camera.auto_learn})

    @app.route("/suggest")
    def suggest():
        with talk.state_lock:
            context = talk.state["context"]
        return jsonify({
            "words": talk.usage.suggest(request.args.get("prefix", "")),
            "phrases": talk.usage.top_phrases(request.args.get("context", context)),
        })

    # -- GPS places ---------------------------------------------------------
    @app.route("/location", methods=["POST"])
    def location():
        data = request.get_json(silent=True) or {}
        try:
            lat, lon = float(data["lat"]), float(data["lon"])
            accuracy = float(data["accuracy"]) if data.get("accuracy") is not None else None
        except (KeyError, TypeError, ValueError):
            return error("lat and lon are required")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return error("lat/lon out of range")
        result = talk.update_location(lat, lon, accuracy)
        with talk.state_lock:
            result["context"] = talk.state["context"]
        return jsonify(result)

    @app.route("/set_auto_context", methods=["POST"])
    def set_auto_context():
        talk.auto_context = bool((request.get_json(silent=True) or {}).get("enabled"))
        return jsonify({"auto_context": talk.auto_context})

    @app.route("/places", methods=["GET", "POST"])
    def places_route():
        if request.method == "GET":
            return jsonify({"places": talk.places.list(), "contexts": CONTEXTS,
                            "max_accuracy": MAX_LOCATION_ACCURACY_M})
        data = request.get_json(silent=True) or {}
        if data.get("use_current"):
            # Save from the smoothed, multi-reading GPS position (precise).
            est, message = talk.tracker.save_estimate()
            if est is None:
                return jsonify({"error": message, "measuring": True}), 409
            data = dict(data, lat=est["lat"], lon=est["lon"])
            if not data.get("radius"):
                data["radius"] = min(150, max(30, round(est["accuracy"] * 2.5)))
        else:
            try:
                accuracy = float(data["accuracy"]) if data.get("accuracy") is not None else None
            except (TypeError, ValueError):
                accuracy = None
            if accuracy is not None and accuracy > MAX_LOCATION_ACCURACY_M:
                return error(f"Location is too inaccurate (±{round(accuracy)} m) to save a place. "
                             "Go outside or use a phone with GPS and try again.")
        try:
            return jsonify(talk.places.add(data))
        except ValueError as exc:
            return error(str(exc))

    @app.route("/places/<place_id>", methods=["PUT", "DELETE"])
    def place_route(place_id):
        if request.method == "DELETE":
            if not talk.places.delete(place_id):
                return error("Place not found", 404)
            talk.tracker.forget_place(place_id)
            with talk.state_lock:
                if talk.current_place and talk.current_place["id"] == place_id:
                    talk.current_place = None
            return jsonify({"deleted": place_id})
        try:
            place = talk.places.update(place_id, request.get_json(silent=True) or {})
        except ValueError as exc:
            return error(str(exc))
        return jsonify(place) if place else error("Place not found", 404)

    # -- profile / medical card ---------------------------------------------------
    @app.route("/profile", methods=["GET", "PUT", "POST"])
    def profile():
        if request.method == "GET":
            return jsonify({"profile": talk.places.profile(), "fields": PROFILE_FIELDS,
                            "medical_text": talk.places.medical_text()})
        prof = talk.places.set_profile(request.get_json(silent=True) or {})
        return jsonify({"profile": prof, "medical_text": talk.places.medical_text()})

    return app


def parse_args(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="GestureTalk – gesture, blink and GPS assisted speech")
    parser.add_argument("--https", action="store_true",
                        help="serve over HTTPS (self-signed) so phones on the same Wi-Fi can share GPS")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--camera", type=int, default=None, help="camera index (default from config)")
    parser.add_argument("--browser-camera", action="store_true",
                        help="use the webcam of the browser that opens the page (tracking runs in the browser)")
    return parser.parse_args(argv)


def main(argv=None):
    from tts import TTSManager

    args = parse_args(argv)
    ssl_context = None
    if args.https:
        from certs import ensure_certificate, lan_ips
        ssl_context = ensure_certificate(CERT_DIR)

    store = GestureStore()
    camera = None
    if not args.browser_camera:
        try:
            from camera import CameraProcessor
            camera = (CameraProcessor(store) if args.camera is None
                      else CameraProcessor(store, camera_index=args.camera))
        except Exception as exc:  # no OpenCV / MediaPipe 'solutions' (e.g. Python 3.13)
            print(f"[camera] Server camera unavailable: {exc}")
            print("[camera] Switching to browser camera mode: the page will use your browser's webcam.")
    if camera is None:
        from assets import ensure_vision_assets
        from browser_camera import BrowserCamera
        camera = BrowserCamera(store)
        ensure_vision_assets()

    tts = TTSManager(cooldown_seconds=SPEECH_COOLDOWN_SECONDS)
    app = create_app(camera, tts, store=store)
    talk = app.config["TALK"]

    if hasattr(camera, "process_camera_loop"):
        threading.Thread(target=camera.process_camera_loop, daemon=True).start()
    threading.Thread(target=talk.recognition_loop, daemon=True).start()

    scheme = "https" if ssl_context else "http"
    print(f"GestureTalk running on {scheme}://localhost:{args.port}")
    if ssl_context:
        for ip in lan_ips():
            print(f"  On your phone (same Wi-Fi): https://{ip}:{args.port}")
        print("  The phone will warn that the certificate is not trusted – it is your own "
              "computer, so choose 'Advanced' -> 'Proceed'. You only need to do this once.")
    else:
        print("  Tip: run with --https to use your phone's GPS (browsers block GPS over plain http).")
    app.run(host=args.host, port=args.port, debug=False, threaded=True, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
