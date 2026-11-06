"""Regression tests on real hand landmarks (MediaPipe run on real photos in a browser)."""
import json
import os

import numpy as np
import pytest

from gestures import GestureStore, classify_builtin, normalize_landmarks
from recognizer import Recognizer

DATA = os.path.join(os.path.dirname(__file__), "data")


def real(name):
    with open(os.path.join(DATA, f"{name}.json")) as f:
        d = json.load(f)
    return np.array(d["hand"], dtype=np.float32), d["handedness"]


def norm(name):
    pts, hand = real(name)
    return normalize_landmarks(pts, hand)


@pytest.mark.parametrize("photo, expected", [
    ("thumb_up", "thumbs_up"), ("victory", "peace"), ("pointing_up", "point")])
def test_builtin_rules_on_real_hands(photo, expected):
    assert classify_builtin(norm(photo)) == expected


def feed(rec, photo, frames=6):
    pts, hand = real(photo)
    out = None
    for i in range(frames):
        out = rec.process_frame(pts + np.float32(0.0005 * i), hand, now=100.0 + i * 4)
    return out


def test_self_learning_cannot_turn_point_into_peace(tmp_path):
    """The bug found with real photos: a learned 'peace' sample swallowed 'point'."""
    rec = Recognizer(GestureStore(str(tmp_path / "g.json")))
    assert feed(rec, "victory") == "peace"
    assert rec.gesture_store.sample_counts().get("peace", 0) >= 1  # learned from use
    assert feed(rec, "pointing_up") == "point"
    assert feed(rec, "victory") == "peace"
    assert feed(rec, "thumb_up") == "thumbs_up"
    counts = rec.gesture_store.sample_counts()
    store2 = GestureStore(str(tmp_path / "g.json"))
    assert store2.sample_counts() == counts  # nothing pruned: no bad samples were learned


def test_one_finger_difference_never_matches(tmp_path):
    store = GestureStore(str(tmp_path / "g.json"))
    store.add_samples("water", [norm("victory")])  # custom gesture with a peace shape
    assert store.match(norm("victory"), 0.3)[0] == "water"
    assert store.match(norm("pointing_up"), 0.3)[0] == "none"


def test_taught_custom_gesture_beats_builtin_rules(tmp_path):
    rec = Recognizer(GestureStore(str(tmp_path / "g.json")))
    rec.gesture_store.add_samples("water", [norm("victory")])
    assert rec.recognise(norm("victory"))[0] == "water"
    assert rec.recognise(norm("pointing_up"))[0] == "point"


def test_mislearned_samples_are_cleaned_on_load(tmp_path):
    path = tmp_path / "g.json"
    bad = norm("pointing_up").tolist()
    good = norm("victory").tolist()
    # legacy list format + new format with an auto sample that contradicts the rules
    path.write_text(json.dumps({"peace": [bad, good], "thumbs_up": [{"lm": bad, "auto": True}],
                                "my_sign": [bad]}))
    store = GestureStore(str(path))
    assert store.sample_counts() == {"my_sign": 1, "peace": 1}
    assert store.match(norm("pointing_up"), 0.3)[0] == "my_sign"


def test_manual_samples_survive_auto_rotation(tmp_path):
    store = GestureStore(str(tmp_path / "g.json"))
    store.add_samples("peace", [norm("victory")])
    base = norm("victory")
    for i in range(1, 10):
        store.learn_sample("peace", base + 0.05 * i, 0.01, 4)
    with store._lock:
        bucket = store._gestures["peace"]
        assert len(bucket) == 4 and not bucket[0]["auto"]
