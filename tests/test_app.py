import threading

import pytest

from app import Announcer, clean_gesture_name, create_app
from gestures import GestureStore, normalize_landmarks
from phrases import PhraseBook
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
                     PhraseBook(str(tmp_path / "p.json")))
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
