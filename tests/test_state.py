import pytest

from aac.state import CommunicationSession, ConfirmedMessage, InvalidTransition, State


def test_valid_happy_path():
    s = CommunicationSession()
    assert s.state == State.IDLE
    s.to(State.PREDICTING)
    s.to(State.PREDICTION_SHOWN)
    s.to(State.CONFIRM_MODE)
    s.to(State.READY_TO_SPEAK)          # armed by an explicit confirm selection
    msg = s.speak_confirmed("hi")       # final confirmation mints the message
    assert s.state == State.SPEAKING
    assert isinstance(msg, ConfirmedMessage)
    s.to(State.IDLE)
    assert s.state == State.IDLE


def test_invalid_idle_to_speaking():
    s = CommunicationSession()
    with pytest.raises(InvalidTransition):
        s.to(State.SPEAKING)


def test_invalid_prediction_shown_to_speaking():
    s = CommunicationSession()
    s.to(State.PREDICTING)
    s.to(State.PREDICTION_SHOWN)
    with pytest.raises(InvalidTransition):
        s.to(State.SPEAKING)


def test_invalid_rejected_to_speaking():
    s = CommunicationSession()
    s.to(State.PREDICTING)
    s.to(State.PREDICTION_SHOWN)
    s.to(State.REJECTED)
    with pytest.raises(InvalidTransition):
        s.to(State.SPEAKING)


def test_speak_confirmed_requires_ready():
    s = CommunicationSession()
    with pytest.raises(InvalidTransition):
        s.speak_confirmed("nope")       # cannot speak straight from IDLE


def test_reset_returns_to_idle():
    s = CommunicationSession()
    s.to(State.PREDICTING)
    s.reset()
    assert s.state == State.IDLE
    assert s.final_message is None
