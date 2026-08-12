from aac.state import ConfirmedMessage
from controller import Controller
from events import SIMULATION, EventType, sim_event


class FakeSpeaker:
    available = False

    def __init__(self):
        self.said = []

    def speak(self, message):
        assert isinstance(message, ConfirmedMessage)
        self.said.append(message.text)
        return True


def test_all_events_build():
    for name in ["BLINK", "SELECT", "CONFIRM", "REJECT", "CANCEL"]:
        event = sim_event(name)
        assert event.type == EventType[name]
        assert event.source == SIMULATION


def test_unknown_event_is_none():
    assert sim_event("NOPE") is None


def test_full_flow_reaches_speech():
    c = Controller(speaker=FakeSpeaker())
    c.handle(sim_event("BLINK"))
    assert c.session.state.name == "PREDICTION_SHOWN"
    c.handle(sim_event("SELECT"))
    assert c.session.state.name == "CONFIRM_MODE"
    c.handle(sim_event("CONFIRM"))
    assert c.session.state.name == "IDLE"
    assert c.speaker.said == ["Yes"]


def test_reject_returns_to_idle_without_speaking():
    c = Controller(speaker=FakeSpeaker())
    c.handle(sim_event("BLINK"))
    c.handle(sim_event("REJECT"))
    assert c.session.state.name == "IDLE"
    assert c.speaker.said == []


def test_cancel_returns_to_idle_without_speaking():
    c = Controller(speaker=FakeSpeaker())
    c.handle(sim_event("BLINK"))
    c.handle(sim_event("SELECT"))
    c.handle(sim_event("CANCEL"))
    assert c.session.state.name == "IDLE"
    assert c.speaker.said == []
