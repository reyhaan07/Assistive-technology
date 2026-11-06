import threading

import pytest

from app import Announcer, clean_gesture_name, create_app
from gestures import GestureStore, normalize_landmarks
from learning import UsageStats
from phrases import PhraseBook
from places import PlaceBook
from tests.hands import make_hand


class FakeCamera:
    camera_ok = True

    def __init__(self):
        self.gesture = "none"
        self.landmarks = None
        self.frame_id = 0
        self.lock = threading.Lock()

    def get_recognition(self):
        return self.gesture, None

    def get_latest_landmarks_with_id(self):
        self.frame_id += 1
        return self.landmarks, self.frame_id

    def generate_mjpeg_stream(self):
        yield b""

    # eye tracking hooks
    eye_tracking = False
    blink_queue = None

    def set_eye_tracking(self, enabled):
        self.eye_tracking = enabled

    def pop_blink_events(self):
        events, self.blink_queue = list(self.blink_queue or []), []
        return events

    def get_eye_status(self):
        return {"face": True, "closed": False, "enabled": self.eye_tracking, "error": ""}


class FakeTTS:
    available = True
    muted = False

    def __init__(self):
        self.spoken = []

    def speak(self, text):
        if not self.muted:
            self.spoken.append(text)
        return True


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr("app.CAPTURE_TIMEOUT_SECONDS", 0.5)
    camera, tts = FakeCamera(), FakeTTS()
    app = create_app(camera, tts, GestureStore(str(tmp_path / "g.json")),
                     PhraseBook(str(tmp_path / "p.json")),
                     PlaceBook(str(tmp_path / "places.json"), str(tmp_path / "profile.json")),
                     UsageStats(str(tmp_path / "usage.json")))
    return app.test_client(), app.config["TALK"], camera, tts


def test_clean_gesture_name():
    assert clean_gesture_name("  Need Water ") == "need_water"
    assert clean_gesture_name("bad/name") == ""
    assert clean_gesture_name("") == ""


def test_announcer_onset_repeat_and_reset():
    a = Announcer(repeat_seconds=5)
    assert a.should_announce("peace", "cafe", now=0)
    assert not a.should_announce("peace", "cafe", now=1)
    assert a.should_announce("peace", "hospital", now=2)  # context change
    assert a.should_announce("peace", "hospital", now=8)  # held long enough
    assert not a.should_announce("none", "hospital", now=9)
    assert a.should_announce("peace", "hospital", now=9.5)


def test_index_and_state(env):
    client, talk, camera, tts = env
    assert client.get("/").status_code == 200
    state = client.get("/get_state").get_json()
    assert state["context"] == "cafe" and state["gesture"] == "none"
    assert state["camera_ok"] and state["tts_available"]


def test_recognition_step_speaks_contextual_phrase(env):
    client, talk, camera, tts = env
    camera.gesture = "thumbs_up"
    talk.step(now=0)
    talk.step(now=1)
    assert tts.spoken == ["One coffee please"]

    assert client.post("/set_context", json={"context": "hospital"}).status_code == 200
    talk.step(now=2)
    assert tts.spoken[-1] == "I am okay"
    state = client.get("/get_state").get_json()
    assert state["phrase"] == "I am okay"
    assert state["history"][0]["phrase"] == "I am okay"
    assert state["speech_id"] == 2


def test_invalid_context(env):
    client, *_ = env
    assert client.post("/set_context", json={"context": "mars"}).status_code == 400


def test_capture_and_train_flow(env):
    client, talk, camera, tts = env
    assert client.post("/train", json={"gesture_name": "water"}).status_code == 400  # nothing captured

    camera.landmarks = None
    assert client.post("/capture_landmarks").status_code == 400

    camera.landmarks = normalize_landmarks(make_hand(extended=("index", "middle")))
    res = client.post("/capture_landmarks?samples=3")
    assert res.status_code == 200 and res.get_json()["samples"] == 3

    res = client.post("/train", json={"gesture_name": "Need Water",
                                      "messages": {"cafe": "Water please", "hospital": "I need water"}})
    assert res.status_code == 200
    assert res.get_json()["gesture_name"] == "need_water"
    assert talk.store.sample_counts()["need_water"] == 3

    # capture buffer is consumed
    assert client.post("/train", json={"gesture_name": "need_water"}).status_code == 400

    gestures = {g["name"]: g for g in client.get("/gestures").get_json()["gestures"]}
    assert gestures["need_water"]["messages"]["cafe"] == "Water please"
    assert gestures["thumbs_up"]["builtin"]

    camera.gesture = "need_water"
    talk.step(now=0)
    assert tts.spoken[-1] == "Water please"


def test_update_phrases_and_delete(env):
    client, talk, camera, tts = env
    camera.landmarks = normalize_landmarks(make_hand())
    client.post("/capture_landmarks?samples=1")
    client.post("/train", json={"gesture_name": "hello", "messages": {"cafe": "Hi"}})

    res = client.put("/phrases/hello", json={"messages": {"cafe": "Hello there"}})
    assert res.get_json()["messages"]["cafe"] == "Hello there"

    assert client.delete("/gestures/hello").status_code == 200
    assert client.delete("/gestures/hello").status_code == 404
    names = [g["name"] for g in client.get("/gestures").get_json()["gestures"]]
    assert "hello" not in names


def test_speak_and_mute(env):
    client, talk, camera, tts = env
    assert client.post("/speak", json={"text": ""}).status_code == 400
    assert client.post("/speak", json={"text": "Good morning"}).status_code == 200
    assert tts.spoken == ["Good morning"]
    client.post("/set_mute", json={"muted": True})
    assert client.get("/get_state").get_json()["muted"] is True
    client.post("/speak", json={"text": "Silent"})
    assert tts.spoken == ["Good morning"]


# ---------------------------------------------------------------- GPS places
CAFE = {"lat": 51.5007, "lon": -0.1246}


def stay(talk, lat, lon, seconds, acc=8, t0=0.0):
    """Feed one accurate fix per second at a fixed spot; returns the end time."""
    for i in range(seconds):
        talk.update_location(lat, lon, acc, now=t0 + i)
    return t0 + seconds


def test_places_auto_context_and_usual_order(env):
    client, talk, camera, tts = env
    assert client.post("/places", json={"name": "x"}).status_code == 400
    res = client.post("/places", json={"name": "Corner Cafe", "context": "cafe", **CAFE,
                                       "radius": 60, "usual": "Large oat latte, no sugar"})
    place = res.get_json()
    assert res.status_code == 200 and place["id"]

    client.post("/set_context", json={"context": "bank"})
    t = stay(talk, CAFE["lat"] + 0.0001, CAFE["lon"], 10)
    assert client.get("/get_state").get_json()["context"] == "bank"  # still confirming
    assert client.get("/get_state").get_json()["gps"]["status"] == "confirming"
    t = stay(talk, CAFE["lat"] + 0.0001, CAFE["lon"], 20, t0=t)
    state = client.get("/get_state").get_json()
    assert state["context"] == "cafe" and state["place"]["name"] == "Corner Cafe"

    camera.gesture = "thumbs_up"
    talk.step(now=0)
    assert tts.spoken[-1] == "Large oat latte, no sugar"

    # leave: far away for long enough
    t = stay(talk, 40.0, -3.0, 50, t0=t)
    assert client.get("/get_state").get_json()["place"] is None

    assert client.put(f"/places/{place['id']}", json={"usual": ""}).status_code == 200
    camera.gesture = "none"; talk.step(now=1)
    camera.gesture = "thumbs_up"; talk.step(now=2)
    assert tts.spoken[-1] == "One coffee please"

    assert client.delete(f"/places/{place['id']}").status_code == 200
    assert client.delete(f"/places/{place['id']}").status_code == 404


def test_location_endpoint_smoke(env):
    client, *_ = env
    body = client.post("/location", json={**CAFE, "accuracy": 8}).get_json()
    assert body["status"] == "measuring" and body["arrived"] is False


def test_save_place_from_measured_position(env):
    client, talk, *_ = env
    res = client.post("/places", json={"name": "Home cafe", "context": "cafe", "use_current": True})
    assert res.status_code == 409 and res.get_json()["measuring"]
    stay(talk, CAFE["lat"], CAFE["lon"], 12, acc=6)
    res = client.post("/places", json={"name": "Home cafe", "context": "cafe", "use_current": True})
    assert res.status_code == 200
    place = res.get_json()
    assert abs(place["lat"] - CAFE["lat"]) < 1e-5 and 30 <= place["radius"] <= 150


def test_auto_context_can_be_disabled(env):
    client, talk, *_ = env
    client.post("/places", json={"name": "Clinic", "context": "hospital", **CAFE})
    client.post("/set_auto_context", json={"enabled": False})
    stay(talk, CAFE["lat"], CAFE["lon"], 40)
    state = client.get("/get_state").get_json()
    assert state["place"]["name"] == "Clinic" and state["context"] == "cafe"


def test_bad_location(env):
    client, *_ = env
    assert client.post("/location", json={"lat": "x"}).status_code == 400
    assert client.post("/location", json={"lat": 100, "lon": 0}).status_code == 400


def test_medical_card_and_sos_with_location(env):
    client, talk, camera, tts = env
    res = client.put("/profile", json={"name": "Sam", "allergies": "penicillin",
                                       "emergency_contact": "Alex", "emergency_phone": "555 0100"})
    text = res.get_json()["medical_text"]
    assert "Sam" in text and "penicillin" in text and "555 0100" in text

    client.post("/speak", json={"text": "{medical}"})
    assert "allergic to penicillin" in tts.spoken[-1]

    client.post("/location", json={**CAFE, "accuracy": 10})
    res = client.post("/speak", json={"text": "Emergency!", "source": "sos"}).get_json()
    assert "latitude" in res["phrase"] and res["location"]["lat"] == CAFE["lat"]
    assert res["contact"] == "555 0100"


# ---------------------------------------------------------------- eyes
def test_blink_patterns_speak_and_open_board(env):
    client, talk, camera, tts = env
    assert client.post("/set_eye_mode", json={"mode": "bogus"}).status_code == 400
    assert client.post("/set_eye_mode", json={"mode": "patterns"}).get_json()["mode"] == "patterns"
    assert camera.eye_tracking is True

    camera.blink_queue = [{"id": 1, "kind": "short", "time": 0.0}, {"id": 2, "kind": "short", "time": 0.4}]
    talk.step(now=0.5)
    talk.step(now=2.0)
    assert tts.spoken[-1] == "Yes"

    client.post("/set_context", json={"context": "hospital"})
    camera.blink_queue = [{"id": 3, "kind": "long", "time": 3.0}]
    talk.step(now=3.1)
    assert tts.spoken[-1] == "Please call the nurse"

    camera.blink_queue = [{"id": 4, "kind": "very_long", "time": 5.0}]
    talk.step(now=5.1)
    state = client.get("/get_state").get_json()
    assert state["eye"]["mode"] == "board" and state["eye"]["last_blink"]["id"] == 4

    client.post("/set_eye_mode", json={"mode": "off"})
    assert camera.eye_tracking is False


# ---------------------------------------------------------------- learning
def test_correction_and_suggestions(env):
    client, talk, camera, tts = env
    assert client.post("/correct", json={"gesture_name": "water"}).status_code == 400
    camera.landmarks = normalize_landmarks(make_hand(extended=("index",)))
    camera.get_latest_landmarks = lambda: camera.landmarks
    res = client.post("/correct", json={"gesture_name": "water"})
    assert res.status_code == 200
    assert talk.store.sample_counts()["water"] == 3

    client.post("/speak", json={"text": "I need water please"})
    client.post("/speak", json={"text": "water again"})
    data = client.get("/suggest?prefix=wa").get_json()
    assert data["words"][0] == "water"
    assert "I need water please" in data["phrases"]


def test_inaccurate_fix_never_switches_or_leaves_place(env):
    client, talk, camera, tts = env
    client.post("/places", json={"name": "Clinic", "context": "hospital", **CAFE})
    # rough Wi-Fi guesses right on top of the clinic for a full minute: ignored
    stay(talk, CAFE["lat"], CAFE["lon"], 60, acc=2000)
    state = client.get("/get_state").get_json()
    assert state["context"] == "cafe" and state["place"] is None and state["gps"]["status"] == "weak"

    t = stay(talk, CAFE["lat"], CAFE["lon"], 30, acc=10, t0=100)
    assert client.get("/get_state").get_json()["place"]["name"] == "Clinic"
    # rough fixes far away do not make us "leave"
    stay(talk, 52.0, 0.5, 90, acc=3000, t0=t)
    state = client.get("/get_state").get_json()
    assert state["place"]["name"] == "Clinic" and state["location"]["weak"]

    res = client.post("/speak", json={"text": "Help", "source": "sos"}).get_json()
    assert "Clinic" in res["phrase"]


def test_cannot_save_place_from_rough_fix(env):
    client, *_ = env
    res = client.post("/places", json={"name": "X", "context": "cafe", **CAFE, "accuracy": 900})
    assert res.status_code == 400 and "inaccurate" in res.get_json()["error"]
    assert client.post("/places", json={"name": "X", "context": "cafe", **CAFE, "accuracy": 30}).status_code == 200


def test_weak_location_text_in_sos(env):
    client, talk, *_ = env
    client.post("/location", json={**CAFE, "accuracy": 1500})
    assert "approximate" in talk.location_text() and "1500 metres" in talk.location_text()


def test_parse_args():
    from app import parse_args
    args = parse_args(["--https", "--port", "8443", "--camera", "1"])
    assert args.https and args.port == 8443 and args.camera == 1
    assert parse_args([]).https is False
