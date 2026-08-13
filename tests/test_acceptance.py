"""Stage 3 acceptance scenario (section 56): construct a brand-new message with
the conventional AAC board, speak it only after an explicit two-step
confirmation, and re-speak it from recents — again only after confirmation.
"""

import pytest

import storage
from aac.state import ConfirmedMessage, State
from controller import Controller
from events import sim_event

MESSAGE = "PLEASE BRING MY COLLEGE DOCUMENTS TOMORROW MORNING."


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


def find(c, kind, value=None):
    for i, t in enumerate(c.board.targets):
        if t.kind == kind and (value is None or t.value == value):
            return i
    raise AssertionError(f"{kind} {value} not found")


def type_text(c, text):
    for ch in text:
        i = find(c, "space", " ") if ch == " " else find(c, "char", ch)
        c.set_index(i)
        c.handle(sim_event("SELECT"))


def test_full_acceptance_scenario():
    c = Controller(speaker=FakeSpeaker())
    c.enter_aac()

    # A completely new message, not in phrases or recents.
    assert MESSAGE not in c.board.recents
    type_text(c, MESSAGE)
    assert c.board.message == MESSAGE

    # CONFIRM arms READY_TO_SPEAK but must NOT speak yet.
    c.handle(sim_event("CONFIRM"))
    assert c.session.state == State.READY_TO_SPEAK
    assert c.speaker.said == []

    # Explicit confirmation -> exactly one TTS event.
    c.handle(sim_event("CONFIRM"))
    assert c.speaker.said == [MESSAGE]

    # Stored as a recent message.
    assert c.board.recents[0] == MESSAGE

    # Selecting the recent message must NOT auto-speak.
    c.set_index(find(c, "recent", MESSAGE))
    c.handle(sim_event("SELECT"))
    assert c.session.state == State.READY_TO_SPEAK
    assert c.speaker.said == [MESSAGE]

    # Confirm again -> exactly one more TTS event.
    c.handle(sim_event("CONFIRM"))
    assert c.speaker.said == [MESSAGE, MESSAGE]
