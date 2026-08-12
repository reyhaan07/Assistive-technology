"""Controller: turns input events into state transitions and, only after an
explicit confirm, into speech.

This is the one place that wires prediction, the state machine and speech
together. The prediction, camera and event modules never import speech, so the
only route to the speaker is through this confirmed path. The mode routing here
is a fixed development path (always CONFIRM); the adaptive policy that chooses
CONFIRM / CHOICES / FALLBACK arrives in Stage 6.
"""

from aac.state import CommunicationSession, State, CONFIRM_STATES
from events import EventType
from prediction.predictor import get_prediction
from speech.tts import Speaker


class Controller:
    def __init__(self, speaker=None):
        self.session = CommunicationSession()
        self.speaker = speaker or Speaker()
        self.prediction = None
        self.selected = None

    def handle(self, event):
        et = event.type
        state = self.session.state

        if et == EventType.BLINK and state == State.IDLE:
            self._predict()
        elif et == EventType.SELECT and state == State.PREDICTION_SHOWN:
            self._choose()
        elif et == EventType.CONFIRM and state in CONFIRM_STATES:
            self._confirm_and_speak()
        elif et == EventType.REJECT and self.session.can(State.REJECTED):
            self._reject()
        elif et == EventType.CANCEL and self.session.can(State.CANCELLED):
            self._cancel()
        # Any other event in the current state is ignored (no-op).

        return self.snapshot()

    def _predict(self):
        self.session.to(State.PREDICTING)
        self.prediction = get_prediction("")  # stub
        self.session.to(State.PREDICTION_SHOWN)

    def _choose(self):
        self.selected = self.prediction.candidates[0].text
        self.session.to(State.CONFIRM_MODE)

    def _confirm_and_speak(self):
        text = self.selected or self.prediction.candidates[0].text
        message = self.session.confirm(text)   # -> READY_TO_SPEAK, mints ConfirmedMessage
        self.session.to(State.SPEAKING)
        self.speaker.speak(message)            # only a confirmed message reaches speech
        self.session.to(State.IDLE)
        self._clear()

    def _reject(self):
        self.session.to(State.REJECTED)
        self.session.to(State.IDLE)
        self._clear()

    def _cancel(self):
        self.session.to(State.CANCELLED)
        self.session.to(State.IDLE)
        self._clear()

    def _clear(self):
        self.prediction = None
        self.selected = None

    def reset(self):
        self.session.reset()
        self._clear()

    def snapshot(self):
        candidates = [c.text for c in self.prediction.candidates] if self.prediction else []
        return {
            "state": self.session.state.name,
            "session_id": self.session.session_id,
            "final_message": self.session.final_message,
            "candidates": candidates,
        }
