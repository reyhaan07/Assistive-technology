import pytest

import storage
from aac.fallback import Board


@pytest.fixture(autouse=True)
def temp_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))


def find(board, kind, value=None):
    for i, t in enumerate(board.targets):
        if t.kind == kind and (value is None or t.value == value):
            return i
    raise AssertionError(f"target {kind} {value} not found")


def type_char(board, ch):
    board.index = find(board, "char", ch)
    board.activate()


def test_add_characters_and_space():
    b = Board()
    for ch in "HI":
        type_char(b, ch)
    b.index = find(b, "space")
    b.activate()
    type_char(b, "U")
    assert b.message == "HI U"


def test_backspace():
    b = Board()
    for ch in "WAT":
        type_char(b, ch)
    b.index = find(b, "backspace")
    b.activate()
    assert b.message == "WA"


def test_backspace_on_empty_does_not_crash():
    b = Board()
    b.index = find(b, "backspace")
    b.activate()
    assert b.message == ""


def test_clear():
    b = Board()
    for ch in "ABC":
        type_char(b, ch)
    b.index = find(b, "clear")
    b.activate()
    assert b.message == ""


def test_word_shortcut_appends_with_space():
    b = Board()
    b.index = find(b, "word", "NEED")
    assert b.activate() == "edit"
    assert b.message == "NEED "


def test_confirm_returns_confirm_code():
    b = Board()
    b.index = find(b, "confirm")
    assert b.activate() == "confirm"


def test_phrase_loads_message_and_returns_ready():
    b = Board()
    idx = find(b, "phrase")
    phrase = b.targets[idx].value
    b.index = idx
    assert b.activate() == "ready"
    assert b.message == phrase


def test_navigation_wraps():
    b = Board()
    b.index = 0
    b.move(-1)
    assert b.index == len(b.targets) - 1
    b.move(1)
    assert b.index == 0


def test_scan_step_advances_by_one():
    b = Board()
    b.index = 0
    b.scan_step()
    assert b.index == 1


def test_recent_persists_and_dedups():
    b = Board()
    b.add_recent("HELLO")
    b.add_recent("WORLD")
    b.add_recent("HELLO")               # moves to front, no duplicate
    assert b.recents[0] == "HELLO"
    assert b.recents.count("HELLO") == 1
    assert "HELLO" in Board().recents   # persisted for a fresh board


def test_long_message_builds():
    b = Board()
    text = "ABCDEFGHIJ" * 10
    for ch in text:
        type_char(b, ch)
    assert len(b.message) == 100
