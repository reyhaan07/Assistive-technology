"""Controller: turns input events into state transitions and, only after an
explicit confirmation, into speech.

Two branches share this one controller and one state machine:

- FALLBACK_MODE / READY_TO_SPEAK  -> conventional AAC (Stage 3). The user builds
  a message on a fixed board and speaks it after a two-step confirmation.
- IDLE / PREDICTION_SHOWN / CONFIRM_MODE -> the prediction path. Still a stub
  (Stage 1 placeholder) until Stage 4 adds real prediction and Stage 6 the policy
  that routes between the two.

Speech is reachable only through session.speak_confirmed() at READY_TO_SPEAK, so
no raw input, blink, gaze, key, phrase or unconfirmed message can speak.
"""

import threading

from aac.fallback import Board
from aac.state import CommunicationSession, State
from events import EventType
from prediction.predictor import get_prediction
from speech.tts import Speaker

_NAVIGATE = (EventType.LEFT, EventType.RIGHT)
_ACTIVATE = (EventType.BLINK, EventType.SELECT)


class Controller:
    def __init__(self, speaker=None):
        self.session = CommunicationSession()
        self.speaker = speaker or Speaker()
        self.board = Board()
        self.notice = ""
        self.confirm_index = 0          # READY_TO_SPEAK: 0=SPEAK, 1=CANCEL
        # prediction-stub path state
        self.prediction = None
        self.selected = None
        # Ocular runs on its own thread and Flask requests on others.
        self._lock = threading.Lock()

    # --- entry ---
    def enter_aac(self):
        with self._lock:
            if self.session.state == State.IDLE:
                self.session.to(State.FALLBACK_MODE)
                self.notice = ""

    def handle(self, event):
        with self._lock:
            state = self.session.state
            if state == State.FALLBACK_MODE:
                self._aac_edit(event.type)
            elif state == State.READY_TO_SPEAK:
                self._aac_confirm(event.type)
            else:
                self._prediction_stub(event.type, state)
            return self.snapshot()

    def scan_advance(self):
        with self._lock:
            if self.session.state == State.FALLBACK_MODE:
                self.board.scan_step()
            return self.snapshot()

    def set_index(self, index):
        with self._lock:
            if self.session.state == State.FALLBACK_MODE and 0 <= index < len(self.board.targets):
                self.board.index = index
            return self.snapshot()

    # --- AAC: message building ---
    def _aac_edit(self, et):
        if et == EventType.LEFT:
            self.board.move(-1)
        elif et == EventType.RIGHT:
            self.board.move(1)
        elif et in _ACTIVATE:
            self._activate_target()
        elif et == EventType.CONFIRM:
            self._try_ready()
        # CANCEL / REJECT while editing: no-op (message is preserved).

    def _activate_target(self):
        action = self.board.activate()
        self.notice = ""
        if action == "confirm":
            self._try_ready()
        elif action == "ready":          # phrase / recent loaded into buffer
            self._enter_ready()

    def _try_ready(self):
        if self.board.message.strip():
            self._enter_ready()
        else:
            self.notice = "No message to speak."

    def _enter_ready(self):
        self.session.to(State.READY_TO_SPEAK)
        self.confirm_index = 0
        self.notice = ""

    # --- AAC: two-step confirmation ---
    def _aac_confirm(self, et):
        if et in _NAVIGATE:
            self.confirm_index ^= 1
        elif et in _ACTIVATE:
            if self.confirm_index == 0:
                self._speak_message()
            else:
                self._cancel_to_edit()
        elif et == EventType.CONFIRM:
            self._speak_message()
        elif et in (EventType.CANCEL, EventType.REJECT):
            self._cancel_to_edit()

    def _speak_message(self):
        text = self.board.message.strip()
        if not text:
            self._cancel_to_edit()
            return
        message = self.session.speak_confirmed(text)   # READY_TO_SPEAK -> SPEAKING, mints
        self.speaker.speak(message)                    # only a confirmed message reaches speech
        self.board.add_recent(text)
        self.session.to(State.IDLE)
        self.session.to(State.FALLBACK_MODE)           # back to the board for the next message
        self.board.clear_message()
        self.notice = f"Spoken: {text}"

    def _cancel_to_edit(self):
        self.session.to(State.FALLBACK_MODE)           # keep the message, resume editing
        self.notice = "Cancelled."

    # --- prediction stub path (placeholder until Stage 4/6) ---
    def _prediction_stub(self, et, state):
        if state == State.IDLE and et == EventType.BLINK:
            self.session.to(State.PREDICTING)
            self.prediction = get_prediction("")
            self.session.to(State.PREDICTION_SHOWN)
        elif state == State.PREDICTION_SHOWN and et == EventType.SELECT:
            self.selected = self.prediction.candidates[0].text
            self.session.to(State.CONFIRM_MODE)
        elif state == State.CONFIRM_MODE and et == EventType.CONFIRM:
            text = self.selected or self.prediction.candidates[0].text
            self.session.to(State.READY_TO_SPEAK)
            message = self.session.speak_confirmed(text)
            self.speaker.speak(message)
            self.session.to(State.IDLE)
            self._clear_prediction()
        elif et == EventType.REJECT and self.session.can(State.REJECTED):
            self.session.to(State.REJECTED)
            self.session.to(State.IDLE)
            self._clear_prediction()
        elif et == EventType.CANCEL and self.session.can(State.CANCELLED):
            self.session.to(State.CANCELLED)
            self.session.to(State.IDLE)
            self._clear_prediction()

    def _clear_prediction(self):
        self.prediction = None
        self.selected = None

    # --- misc ---
    def reset(self):
        with self._lock:
            self.session.reset()
            self.board.clear_message()
            self.notice = ""
            self._clear_prediction()

    def current_label(self):
        if self.session.state == State.READY_TO_SPEAK:
            return ("SPEAK", "CANCEL")[self.confirm_index]
        if self.session.state == State.FALLBACK_MODE:
            return self.board.current().label
        return ""

    def snapshot(self):
        state = self.session.state
        data = {
            "state": state.name,
            "message": self.board.message,
            "notice": self.notice,
            "index": self.board.index,
            "current": self.current_label(),
            "targets": [{"kind": t.kind, "label": t.label} for t in self.board.targets],
            "recents": self.board.recents,
            "final_message": self.session.final_message,
        }
        if state == State.READY_TO_SPEAK:
            data["confirm_options"] = ["SPEAK", "CANCEL"]
            data["confirm_index"] = self.confirm_index
        return data
