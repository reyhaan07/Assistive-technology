import pytest

from aac.state import ConfirmedMessage
from controller import Controller
from events import sim_event
from prediction.predictor import get_prediction
from speech.tts import Speaker


class FakeSpeaker:
    available = False

    def __init__(self):
        self.said = []

    def speak(self, message):
        assert isinstance(message, ConfirmedMessage)
        self.said.append(message.text)
        return True


def test_speak_rejects_raw_text():
    sp = Speaker()
    with pytest.raises(TypeError):
        sp.speak("hello")


def test_confirmed_message_cannot_be_forged():
    with pytest.raises(PermissionError):
        ConfirmedMessage("hi")  # only session.confirm() may create one


def test_creating_a_prediction_does_not_speak():
    sp = FakeSpeaker()
    c = Controller(speaker=sp)
    get_prediction("")          # prediction produces data only
    c.handle(sim_event("BLINK"))  # controller runs the stub prediction
    assert sp.said == []


def test_raw_input_does_not_speak():
    sp = FakeSpeaker()
    c = Controller(speaker=sp)
    c.handle(sim_event("BLINK"))
    c.handle(sim_event("SELECT"))  # in CONFIRM_MODE, still unconfirmed
    assert sp.said == []


def test_only_confirmed_message_reaches_speech():
    sp = FakeSpeaker()
    c = Controller(speaker=sp)
    c.handle(sim_event("BLINK"))
    c.handle(sim_event("SELECT"))
    c.handle(sim_event("CONFIRM"))
    assert sp.said == ["Yes"]
