import pytest

import storage
from aac.state import ConfirmedMessage, State
from controller import Controller
from events import OCULAR, EventType, InputEvent, sim_event


@pytest.fixture(autouse=True)
def temp_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))


class FakeSpeaker:
    available = False

    def __init__(self):
        self.said = []

    def speak(self, message):
        assert isinstance(message, ConfirmedMessage)
        self.said.append(message.text)
        return True


def controller():
    c = Controller(speaker=FakeSpeaker())
    c.enter_aac()
    return c


def find(c, kind, value=None):
    for i, t in enumerate(c.board.targets):
        if t.kind == kind and (value is None or t.value == value):
            return i
    raise AssertionError(f"{kind} {value} not found")


def ev(name):
    return sim_event(name)


def type_text(c, text):
    for ch in text:
        i = find(c, "space", " ") if ch == " " else find(c, "char", ch)
        c.set_index(i)
        c.handle(ev("SELECT"))


def test_enter_aac_starts_in_fallback():
    assert controller().session.state == State.FALLBACK_MODE


def test_build_then_two_step_confirm_speaks_once():
    c = controller()
    type_text(c, "HI")
    assert c.board.message == "HI"
    assert c.speaker.said == []            # building never speaks
    c.handle(ev("CONFIRM"))                # FALLBACK_MODE -> READY_TO_SPEAK
    assert c.session.state == State.READY_TO_SPEAK
    assert c.speaker.said == []            # armed, still silent
    c.handle(ev("CONFIRM"))                # explicit speak
    assert c.speaker.said == ["HI"]
    assert c.session.state == State.FALLBACK_MODE


def test_empty_message_cannot_be_spoken():
    c = controller()
    c.handle(ev("CONFIRM"))
    assert c.session.state == State.FALLBACK_MODE
    assert c.speaker.said == []
    assert "No message" in c.notice


def test_cancel_at_ready_keeps_message():
    c = controller()
    type_text(c, "HI")
    c.handle(ev("CONFIRM"))                # READY_TO_SPEAK
    c.handle(ev("CANCEL"))                 # back to editing
    assert c.session.state == State.FALLBACK_MODE
    assert c.board.message == "HI"
    assert c.speaker.said == []


def test_arbitrary_message_can_be_spoken():
    c = controller()
    message = "PLEASE BRING MY COLLEGE DOCUMENTS"
    type_text(c, message)
    assert c.board.message == message
    c.handle(ev("CONFIRM"))
    c.handle(ev("CONFIRM"))
    assert c.speaker.said == [message]


def test_one_blink_one_selection():
    c = controller()
    c.set_index(find(c, "char", "A"))
    c.handle(InputEvent(EventType.BLINK, source=OCULAR))
    assert c.board.message == "A"
    c.handle(InputEvent(EventType.BLINK, source=OCULAR))
    assert c.board.message == "AA"


def test_navigation_never_selects():
    c = controller()
    c.handle(ev("LEFT"))
    c.handle(ev("RIGHT"))
    assert c.board.message == ""
    assert c.session.state == State.FALLBACK_MODE


def test_scan_never_selects():
    c = controller()
    start = c.board.index
    c.scan_advance()
    assert c.board.index != start
    assert c.board.message == ""


def test_phrase_requires_confirmation():
    c = controller()
    idx = find(c, "phrase")
    phrase = c.board.targets[idx].value
    c.set_index(idx)
    c.handle(ev("SELECT"))                 # load phrase
    assert c.session.state == State.READY_TO_SPEAK
    assert c.speaker.said == []            # not spoken yet
    c.handle(ev("CONFIRM"))
    assert c.speaker.said == [phrase]


def test_recent_message_requires_confirmation():
    c = controller()
    type_text(c, "HELLO")
    c.handle(ev("CONFIRM"))
    c.handle(ev("CONFIRM"))               # spoken once, stored as recent
    assert c.speaker.said == ["HELLO"]
    assert "HELLO" in c.board.recents
    c.set_index(find(c, "recent", "HELLO"))
    c.handle(ev("SELECT"))                # select recent
    assert c.session.state == State.READY_TO_SPEAK
    assert c.speaker.said == ["HELLO"]    # not auto-spoken
    c.handle(ev("CONFIRM"))
    assert c.speaker.said == ["HELLO", "HELLO"]


def test_characters_do_not_speak():
    c = controller()
    type_text(c, "ABC")
    assert c.speaker.said == []


def test_no_duplicate_speech_from_extra_confirm():
    c = controller()
    type_text(c, "HI")
    c.handle(ev("CONFIRM"))               # READY
    c.handle(ev("CONFIRM"))               # speak once
    assert c.speaker.said == ["HI"]
    c.handle(ev("CONFIRM"))               # now editing empty -> nothing
    assert c.speaker.said == ["HI"]
