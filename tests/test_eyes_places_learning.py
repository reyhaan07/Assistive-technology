import numpy as np

from eyes import LEFT_EYE, RIGHT_EYE, BlinkDetector, BlinkPatternDecoder, face_ear
from gestures import GestureStore, normalize_landmarks
from learning import UsageStats
from places import PlaceBook, haversine_m, resolve_tokens
from tests.hands import make_hand


def face_with_eyes(openness):
    pts = np.zeros((468, 3), dtype=np.float32)
    for idx, x0 in ((LEFT_EYE, 0.0), (RIGHT_EYE, 2.0)):
        p1, p2, p3, p4, p5, p6 = idx
        pts[p1] = [x0, 0, 0]; pts[p4] = [x0 + 1, 0, 0]
        pts[p2] = [x0 + 0.33, -openness, 0]; pts[p6] = [x0 + 0.33, openness, 0]
        pts[p3] = [x0 + 0.66, -openness, 0]; pts[p5] = [x0 + 0.66, openness, 0]
    return pts


def run(detector, seq, dt=0.033, t0=0.0):
    events, t = [], t0
    for openness, frames in seq:
        for _ in range(frames):
            t += dt
            e = detector.update(face_ear(face_with_eyes(openness)), t)
            if e:
                events.append(e)
    return events, t


def test_ear_drops_when_eye_closes():
    assert face_ear(face_with_eyes(0.15)) > 3 * face_ear(face_with_eyes(0.02))


def test_blink_detector_short_long_very_long_and_noise():
    d = BlinkDetector()
    events, _ = run(d, [(0.15, 30), (0.02, 5), (0.15, 10),       # short ~0.17s
                        (0.02, 25), (0.15, 10),                   # long ~0.8s
                        (0.02, 70), (0.15, 10),                   # very long ~2.3s
                        (0.02, 1), (0.15, 10),                    # 1 frame noise
                        (0.02, 200), (0.15, 10)])                 # eyes shut > max
    assert [e["kind"] for e in events] == ["short", "long", "very_long"]


def test_blink_detector_adapts_to_user_baseline():
    d = BlinkDetector()
    events, _ = run(d, [(0.08, 30), (0.02, 6), (0.08, 10)])  # narrower eyes
    assert [e["kind"] for e in events] == ["short"]


def test_pattern_decoder():
    dec = BlinkPatternDecoder(gap_seconds=0.8)
    assert dec.feed({"kind": "short", "time": 0.0}) is None
    assert dec.tick(0.5) is None
    assert dec.tick(1.0) is None  # single blink ignored
    for t in (2.0, 2.3):
        dec.feed({"kind": "short", "time": t})
    assert dec.tick(3.2) == "blink_x2"
    for t in (4.0, 4.3, 4.6):
        dec.feed({"kind": "short", "time": t})
    assert dec.tick(5.5) == "blink_x3"
    assert dec.feed({"kind": "long", "time": 6}) == "long_blink"
    assert dec.feed({"kind": "very_long", "time": 7}) == "open_board"


def test_haversine_and_tokens():
    assert 1100 < haversine_m(0, 0, 0, 0.01) < 1120
    vals = {"usual": "", "medical": "Allergic to nuts", "place": "Cafe", "name": ""}
    assert resolve_tokens("{usual|One coffee}", vals) == "One coffee"
    assert resolve_tokens("At {place}: {medical}", vals) == "At Cafe: Allergic to nuts"


def test_placebook_persist_nearest_refine(tmp_path):
    a, b = str(tmp_path / "pl.json"), str(tmp_path / "pr.json")
    book = PlaceBook(a, b)
    p = book.add({"name": "Cafe", "context": "cafe", "lat": 10, "lon": 10, "radius": 200, "usual": "Tea"})
    book.add({"name": "Far", "context": "bank", "lat": 20, "lon": 20})
    assert book.nearest(10.001, 10)["name"] == "Cafe"
    assert book.nearest(11, 11) is None
    book.refine(p["id"], 10.001, 10, weight=0.5)
    reloaded = PlaceBook(a, b)
    assert reloaded.get(p["id"])["lat"] == 10.0005
    assert reloaded.usual_for("cafe") == "Tea"
    assert reloaded.usual_for("college") == ""


def test_auto_learning_adds_novel_samples_only(tmp_path):
    store = GestureStore(str(tmp_path / "g.json"))
    base = normalize_landmarks(make_hand(extended=("index",)))
    assert store.learn_sample("point", base, 0.04, 5)
    assert not store.learn_sample("point", base + 0.001, 0.04, 5)  # too similar
    for i in range(1, 8):
        store.learn_sample("point", base + 0.05 * i, 0.04, 5)
    assert store.sample_counts()["point"] == 5  # capped, oldest dropped


def test_usage_stats(tmp_path):
    path = str(tmp_path / "u.json")
    u = UsageStats(path)
    for _ in range(3):
        u.record("Bathroom please", "hospital")
    u.record("Bath time", "hospital")
    assert u.top_phrases("hospital")[0] == "Bathroom please"
    assert UsageStats(path).suggest("bat")[:2] == ["bathroom", "bath"]
    assert "water" in u.suggest("wa")  # starter vocabulary
