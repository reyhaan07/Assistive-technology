import pytest

from aac.state import CommunicationSession, ConfirmedMessage, InvalidTransition, State


def test_valid_happy_path():
    s = CommunicationSession()
    assert s.state == State.IDLE
    s.to(State.PREDICTING)
    s.to(State.PREDICTION_SHOWN)
    s.to(State.CONFIRM_MODE)
    msg = s.confirm("hi")
    assert s.state == State.READY_TO_SPEAK
    assert isinstance(msg, ConfirmedMessage)
    s.to(State.SPEAKING)
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


def test_confirm_requires_confirm_mode():
    s = CommunicationSession()
    with pytest.raises(InvalidTransition):
        s.confirm("nope")


def test_reset_returns_to_idle():
    s = CommunicationSession()
    s.to(State.PREDICTING)
    s.reset()
    assert s.state == State.IDLE
    assert s.final_message is None
