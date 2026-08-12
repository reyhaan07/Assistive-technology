"""Speech output.

Speaks ONLY a ConfirmedMessage. There is no speak(text) that any module can
call with raw text, and this module imports nothing from prediction/camera/input
so those layers cannot reach speech. pyttsx3 is optional: without it (e.g. a
headless test box) the speaker stays quiet instead of crashing.
"""

import threading
import time

from aac.state import ConfirmedMessage

try:
    import pyttsx3
except Exception:
    pyttsx3 = None


class Speaker:
    def __init__(self, cooldown: float = 1.0):
        self.cooldown = cooldown
        self.available = pyttsx3 is not None
        self._engine = None
        self._last = 0.0
        self._lock = threading.Lock()

    def speak(self, message: ConfirmedMessage) -> bool:
        if not isinstance(message, ConfirmedMessage):
            raise TypeError("Speaker.speak requires a ConfirmedMessage, not raw text")

        now = time.time()
        if now - self._last < self.cooldown:
            return False
        self._last = now

        self._say(message.text)
        return True

    def _say(self, text: str) -> None:
        if pyttsx3 is None:
            return

        def run():
            with self._lock:
                if self._engine is None:
                    self._engine = pyttsx3.init()
                self._engine.say(text)
                self._engine.runAndWait()

        threading.Thread(target=run, daemon=True).start()
