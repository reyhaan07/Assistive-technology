import numpy as np
import pytest

from gestures import GestureSmoother, GestureStore, classify_builtin, normalize_landmarks
from tests.hands import make_hand


@pytest.mark.parametrize("pose, expected", [
    (dict(extended=("index", "middle", "ring", "pinky"), thumb="out"), "stop"),
    (dict(extended=("index", "middle")), "peace"),
    (dict(extended=("index",)), "point"),
    (dict(), "fist"),
    (dict(thumb="up"), "thumbs_up"),
    (dict(thumb="down"), "thumbs_down"),
])
def test_builtin_classifier(pose, expected):
    hand = make_hand(**pose)
    assert classify_builtin(hand) == expected
    assert classify_builtin(normalize_landmarks(hand)) == expected


def test_classifier_rejects_bad_shape():
    assert classify_builtin(np.zeros((5, 3))) is None


def test_normalize_is_translation_and_scale_invariant():
    hand = make_hand(extended=("index",))
    moved = hand * 2.0 + np.array([0.3, -0.1, 0.0], dtype=np.float32)
    assert np.allclose(normalize_landmarks(hand), normalize_landmarks(moved), atol=1e-5)


def test_left_hand_mirroring_matches_right_hand():
    right = make_hand(extended=("index", "middle"))
    left = right.copy()
    left[:, 0] = 1.0 - left[:, 0]
    assert np.allclose(normalize_landmarks(right, "Right"), normalize_landmarks(left, "Left"), atol=1e-5)


def test_store_match_persist_and_delete(tmp_path):
    path = tmp_path / "g.json"
    store = GestureStore(str(path))
    peace = normalize_landmarks(make_hand(extended=("index", "middle")))
    fist = normalize_landmarks(make_hand())
    store.add_samples("Peace Sign", [peace, peace])
    store.add_gesture("fist2", fist)
    assert store.count() == 3
    assert store.sample_counts() == {"fist2": 1, "peace sign": 2}

    name, dist = store.match(peace, 0.3)
    assert name == "peace sign" and dist == pytest.approx(0.0, abs=1e-6)

    reloaded = GestureStore(str(path))
    assert reloaded.count() == 3
    assert reloaded.delete_gesture("fist2") is True
    assert reloaded.delete_gesture("missing") is False
    assert GestureStore(str(path)).names() == ["peace sign"]


def test_store_no_match_beyond_threshold(tmp_path):
    store = GestureStore(str(tmp_path / "g.json"))
    assert store.match(np.zeros((21, 3)), 0.3) == ("none", None)
    store.add_gesture("a", normalize_landmarks(make_hand()))
    name, dist = store.match(normalize_landmarks(make_hand(extended=("index", "middle", "ring", "pinky"))), 0.01)
    assert name == "none" and dist > 0.01


def test_store_survives_corrupt_file(tmp_path):
    path = tmp_path / "g.json"
    path.write_text("{not json")
    assert GestureStore(str(path)).count() == 0


def test_smoother_requires_stable_frames():
    s = GestureSmoother(3)
    assert s.update("peace") == "none"
    assert s.update("peace") == "none"
    assert s.update("peace") == "peace"
    assert s.update("fist") == "peace"   # single glitch ignored
    assert s.update("peace") == "peace"
    for _ in range(3):
        out = s.update("none")
    assert out == "none"
