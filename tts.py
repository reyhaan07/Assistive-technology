"""Offline text-to-speech with a single worker thread.

pyttsx3 is not thread safe and `runAndWait` can hang when called from several
threads, so every utterance goes through one queue/worker. If pyttsx3 (or an
audio device) is unavailable the manager stays usable and simply reports
`available = False`; the browser can then speak instead.
"""
import queue
import threading
import time


class TTSManager:
    def __init__(self, cooldown_seconds: float = 2.0, enabled: bool = True):
        self.cooldown_seconds = cooldown_seconds
        self.muted = False
        self.available = False
        self.error = ""
        self.last_spoken_time = 0.0
        self.last_spoken_key = ""
        self.state_lock = threading.Lock()
        self._queue: "queue.Queue[str]" = queue.Queue(maxsize=3)
        self._ready = threading.Event()

        if enabled:
            threading.Thread(target=self._worker, daemon=True).start()
            self._ready.wait(timeout=5)

    def _worker(self):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            self.available = True
        except Exception as exc:  # no driver / no audio device / not installed
            self.error = str(exc)
            print(f"[tts] Server speech disabled: {exc}")
            self._ready.set()
            return

        self._ready.set()
        while True:
            text = self._queue.get()
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception as exc:
                print(f"[tts] Failed to speak: {exc}")

    def speak(self, text: str) -> bool:
        if self.muted or not self.available or not text:
            return False
        try:
            self._queue.put_nowait(text)
            return True
        except queue.Full:
            return False

    def should_speak(self, key: str) -> bool:
        """Cooldown check: a new key may speak immediately, a repeat must wait."""
        now = time.time()
        with self.state_lock:
            if key != self.last_spoken_key or (now - self.last_spoken_time) >= self.cooldown_seconds:
                self.last_spoken_time = now
                self.last_spoken_key = key
                return True
        return False

    def try_speak(self, text: str, key: str) -> bool:
        if not self.should_speak(key):
            return False
        self.speak(text)
        return True
