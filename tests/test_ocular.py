from aac.state import ConfirmedMessage
from controller import Controller
from events import OCULAR, EventType, InputEvent, sim_event
from vision.blink import BlinkParams
from vision.ocular import OcularInput


def _params():
    return BlinkParams(open_thresh=0.25, close_thresh=0.18, min_close=0.05,
                       max_close=1.0, intentional_min=0.3, cooldown=0.5)


def _ocular(on_event=None):
    events = []
    oc = OcularInput(camera=None, face=None,
                     on_event=on_event or events.append, params=_params())
    return oc, events


class FakeSpeaker:
    available = False

    def __init__(self):
        self.said = []

    def speak(self, message):
        assert isinstance(message, ConfirmedMessage)
        self.said.append(message.text)
        return True


def test_intentional_blink_emits_ocular_input_event():
    oc, events = _ocular()
    oc.update(0.30, True, True, 0.0)
    oc.update(0.10, True, True, 0.1)   # closed
    oc.update(0.30, True, True, 0.5)   # reopen after 0.4s -> intentional
    assert len(events) == 1
    assert events[0].type == EventType.BLINK
    assert events[0].source == OCULAR
    assert oc.intentional_blinks == 1


def test_natural_blink_is_not_forwarded():
    oc, events = _ocular()
    oc.update(0.30, True, True, 0.0)
    oc.update(0.10, True, True, 0.1)
    oc.update(0.30, True, True, 0.2)   # 0.1s closure -> natural
    assert events == []
    assert oc.natural_blinks == 1


def test_face_loss_produces_no_event():
    oc, events = _ocular()
    oc.update(0.30, True, True, 0.0)
    oc.update(0.10, True, True, 0.1)          # closed
    oc.update(None, False, False, 0.2)        # face lost
    oc.update(0.30, True, True, 0.5)          # reopen after loss
    assert events == []


def test_ocular_blink_does_not_reach_tts():
    speaker = FakeSpeaker()
    controller = Controller(speaker=speaker)
    oc, _ = _ocular(on_event=controller.handle)
    oc.update(0.30, True, True, 0.0)
    oc.update(0.10, True, True, 0.1)
    oc.update(0.30, True, True, 0.5)          # intentional blink -> controller
    assert controller.session.state.name == "PREDICTION_SHOWN"
    assert speaker.said == []                 # blink never speaks


def test_simulation_and_ocular_take_the_same_path():
    c1 = Controller(speaker=FakeSpeaker())
    c2 = Controller(speaker=FakeSpeaker())
    c1.handle(sim_event("BLINK"))
    c2.handle(InputEvent(EventType.BLINK, source=OCULAR))
    assert c1.session.state.name == c2.session.state.name == "PREDICTION_SHOWN"
