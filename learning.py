"""Usage learning: GestureTalk gets faster and more accurate the more it is used.

* Phrase frequency per context  -> the blink board shows the most-used phrases first.
* Word frequency                -> word suggestions while spelling with blinks.
"""
import json
import os
import re
import threading
from collections import Counter
from typing import Dict, List

from config import USAGE_FILE

WORD_RE = re.compile(r"[a-zA-Z']+")
STARTER_WORDS = ("yes no please thank you help water food toilet pain doctor nurse "
                 "medicine cold hot tired sleep wait stop more family call home bathroom "
                 "hungry thirsty good bad okay love sorry hello goodbye today tomorrow").split()


class UsageStats:
    def __init__(self, file_path: str = USAGE_FILE):
        self.file_path = file_path
        self._lock = threading.RLock()
        self.phrases: Dict[str, Counter] = {}
        self.words: Counter = Counter()
        self.load()

    def record(self, phrase: str, context: str) -> None:
        phrase = phrase.strip()
        if not phrase:
            return
        with self._lock:
            self.phrases.setdefault(context, Counter())[phrase] += 1
            for w in WORD_RE.findall(phrase.lower()):
                if len(w) > 1 or w in ("i", "a"):
                    self.words[w] += 1
            self.save()

    def top_phrases(self, context: str, n: int = 8) -> List[str]:
        with self._lock:
            return [p for p, _ in self.phrases.get(context, Counter()).most_common(n)]

    def suggest(self, prefix: str, n: int = 4) -> List[str]:
        prefix = prefix.lower().strip()
        if not prefix:
            return []
        with self._lock:
            learned = [w for w, _ in self.words.most_common() if w.startswith(prefix) and w != prefix]
        starters = [w for w in STARTER_WORDS if w.startswith(prefix) and w != prefix and w not in learned]
        return (learned + starters)[:n]

    def save(self) -> None:
        with self._lock:
            data = {"phrases": {c: dict(v) for c, v in self.phrases.items()}, "words": dict(self.words)}
        directory = os.path.dirname(self.file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = self.file_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self.file_path)

    def load(self) -> None:
        if not os.path.exists(self.file_path):
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.phrases = {c: Counter(v) for c, v in data.get("phrases", {}).items()}
            self.words = Counter(data.get("words", {}))
        except (OSError, ValueError, AttributeError) as exc:
            print(f"[learning] Could not read {self.file_path}: {exc}")
