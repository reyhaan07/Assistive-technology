import numpy as np

from app import create_app, parse_args
from browser_camera import BrowserCamera
from gestures import GestureStore
from learning import UsageStats
from phrases import PhraseBook
from places import PlaceBook
from tests.hands import make_hand
from tests.test_app import FakeTTS


def eye_points(openness):
    """12 points: left eye p1..p6 then right eye p1..p6 (pixels)."""
    pts = []
    for x0 in (100, 200):
        pts += [[x0, 100], [x0 + 10, 100 - openness], [x0 + 20, 100 - openness],
                [x0 + 30, 100], [x0 + 20, 100 + openness], [x0 + 10, 100 + openness]]
    return pts


def make(tmp_path):
    store = GestureStore(str(tmp_path / "g.json"))
    cam = BrowserCamera(store)
    app = create_app(cam, FakeTTS(), store, PhraseBook(str(tmp_path / "p.json")),
                     PlaceBook(str(tmp_path / "pl.json"), str(tmp_path / "pr.json")),
                     UsageStats(str(tmp_path / "u.json")))
    return cam, app.test_client(), app.config["TALK"]


def test_browser_frames_recognise_gestures(tmp_path):
    cam, client, talk = make(tmp_path)
    assert client.get("/get_state").get_json()["camera_ok"] is False
    hand = make_hand(thumb="up").tolist()
    for _ in range(5):
        res = client.post("/landmarks", json={"hand": hand, "handedness": "Right", "eye": None})
    assert res.get_json()["gesture"] == "thumbs_up"
    state = client.get("/get_state").get_json()
    assert state["camera_ok"] and state["camera_mode"] == "browser"
    talk.step(now=0)
    assert talk.tts.spoken[-1] == "One coffee please"


def test_browser_frames_capture_and_train(tmp_path):
    cam, client, talk = make(tmp_path)
    hand = make_hand(extended=("index", "middle", "ring")).tolist()
    for _ in range(3):
        client.post("/landmarks", json={"hand": hand, "handedness": "Left"})
    talk.camera.get_latest_landmarks_with_id()
    # capture reads latest frames; keep frames flowing in between
    import threading, time
    stop = False

    def pump():
        while not stop:
            cam.ingest({"hand": hand, "handedness": "Left"})
            time.sleep(0.02)
    threading.Thread(target=pump, daemon=True).start()
    res = client.post("/capture_landmarks?samples=3")
    stop = True
    assert res.status_code == 200
    assert client.post("/train", json={"gesture_name": "three", "messages": {"cafe": "Three please"}}).status_code == 200
    for _ in range(5):
        cam.ingest({"hand": hand, "handedness": "Left"})
    assert cam.get_recognition()[0] == "three"


def test_browser_blinks(tmp_path):
    cam, client, talk = make(tmp_path)
    client.post("/set_eye_mode", json={"mode": "patterns"})
    import time as _time
    t = _time.time()
    def frames(openness, n):
        nonlocal t
        for _ in range(n):
            cam.ingest({"hand": None, "eye": eye_points(openness)}, now=t)
            t += 0.066
    frames(6, 15); frames(1, 3); frames(6, 5); frames(1, 3); frames(6, 5)
    talk.step(now=t + 2)
    assert talk.tts.spoken[-1] == "Yes"
    cam.ingest({"hand": None, "eye": eye_points(6)})
    assert client.get("/get_state").get_json()["eye"]["face"] is True


def test_bad_payloads_are_ignored(tmp_path):
    cam, client, talk = make(tmp_path)
    for payload in ({"hand": [[1, 2]]}, {"hand": "x"}, {"hand": [[float("nan")] * 3] * 21}, {"eye": [[1]] * 12}, {}):
        assert client.post("/landmarks", json=payload).get_json()["gesture"] == "none"


def test_server_camera_rejects_landmarks(tmp_path):
    from tests.test_app import FakeCamera
    app = create_app(FakeCamera(), FakeTTS(), GestureStore(str(tmp_path / "g.json")),
                     PhraseBook(str(tmp_path / "p.json")),
                     PlaceBook(str(tmp_path / "pl.json"), str(tmp_path / "pr.json")),
                     UsageStats(str(tmp_path / "u.json")))
    assert app.test_client().post("/landmarks", json={}).status_code == 409


def test_index_renders_browser_camera(tmp_path):
    cam, client, talk = make(tmp_path)
    html = client.get("/").get_data(as_text=True)
    assert 'id="camVideo"' in html and "browser_camera.js" in html and 'id="videoFeed"' not in html


def test_parse_browser_flag():
    assert parse_args(["--browser-camera"]).browser_camera is True


def test_stale_browser_reports_no_gesture(tmp_path):
    cam, client, talk = make(tmp_path)
    hand = make_hand(thumb="up").tolist()
    for _ in range(5):
        cam.ingest({"hand": hand, "handedness": "Right"})
    assert cam.get_recognition()[0] == "thumbs_up"
    cam.last_frame_time -= 10  # tab closed 10 s ago
    assert cam.get_recognition()[0] == "none"
    assert client.get("/get_state").get_json()["camera_ok"] is False
    cam.ingest({"hand": make_hand(extended=("index", "middle")).tolist(), "handedness": "Right"})
    assert cam.get_recognition()[0] == "none"  # old gesture forgotten after the gap
