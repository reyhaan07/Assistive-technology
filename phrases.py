"""Per-context phrases spoken for each gesture, persisted to JSON."""
import json
import os
import threading
from typing import Dict, Optional

from config import CONTEXTS, PHRASES_FILE

DEFAULT_PHRASES: Dict[str, Dict[str, str]] = {
    "thumbs_up": {"cafe": "One coffee please", "hospital": "I am okay",
                  "college": "Present", "bank": "Confirm"},
    "thumbs_down": {"cafe": "I don't like this", "hospital": "I feel unwell",
                    "college": "I disagree", "bank": "That is not correct"},
    "stop": {"cafe": "Stop order", "hospital": "Emergency stop",
             "college": "Wait", "bank": "Cancel"},
    "peace": {"cafe": "Two items", "hospital": "Need assistance",
              "college": "Break", "bank": "Check balance"},
    "point": {"cafe": "I would like that one", "hospital": "It hurts here",
              "college": "I have a question", "bank": "I need help with this"},
    "fist": {"cafe": "Bill please", "hospital": "I am in pain",
             "college": "I am ready", "bank": "Withdraw money"},
}


def humanize(gesture_name: str) -> str:
    return gesture_name.replace("_", " ").strip().capitalize()


class PhraseBook:
    def __init__(self, file_path: str = PHRASES_FILE, contexts=CONTEXTS):
        self.file_path = file_path
        self.contexts = list(contexts)
        self._lock = threading.RLock()
        self._phrases: Dict[str, Dict[str, str]] = {
            g: dict(m) for g, m in DEFAULT_PHRASES.items()
        }
        self.load()

    def _clean(self, messages: Optional[dict]) -> Dict[str, str]:
        messages = messages or {}
        return {ctx: str(messages.get(ctx, "") or "").strip() for ctx in self.contexts}

    def get(self, gesture_name: str, context_name: str) -> str:
        """Phrase for a gesture in a context, falling back to the gesture name."""
        gesture_name = gesture_name.lower()
        with self._lock:
            msg = self._phrases.get(gesture_name, {}).get(context_name, "")
        return msg or humanize(gesture_name)

    def messages_for(self, gesture_name: str) -> Dict[str, str]:
        with self._lock:
            return self._clean(self._phrases.get(gesture_name.lower()))

    def has(self, gesture_name: str) -> bool:
        with self._lock:
            return gesture_name.lower() in self._phrases

    def set(self, gesture_name: str, messages: Optional[dict], keep_existing: bool = False) -> Dict[str, str]:
        """Store messages; with keep_existing, blank entries keep the previous text."""
        gesture_name = gesture_name.lower().strip()
        cleaned = self._clean(messages)
        with self._lock:
            if keep_existing:
                old = self._clean(self._phrases.get(gesture_name))
                cleaned = {ctx: cleaned[ctx] or old[ctx] for ctx in self.contexts}
            self._phrases[gesture_name] = cleaned
            self.save()
            return dict(cleaned)

    def delete(self, gesture_name: str) -> None:
        with self._lock:
            name = gesture_name.lower().strip()
            if name in DEFAULT_PHRASES:
                self._phrases[name] = dict(DEFAULT_PHRASES[name])
            else:
                self._phrases.pop(name, None)
            self.save()

    def all(self) -> Dict[str, Dict[str, str]]:
        with self._lock:
            return {g: self._clean(m) for g, m in sorted(self._phrases.items())}

    def save(self) -> None:
        with self._lock:
            data = dict(self._phrases)
        directory = os.path.dirname(self.file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = self.file_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.file_path)

    def load(self) -> None:
        if not os.path.exists(self.file_path):
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as exc:
            print(f"[phrases] Could not read {self.file_path}: {exc}")
            return
        with self._lock:
            for gesture, messages in data.items():
                if isinstance(messages, dict):
                    self._phrases[gesture.lower()] = {k: str(v) for k, v in messages.items()}
