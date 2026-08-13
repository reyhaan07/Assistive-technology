"""Conventional AAC board.

The fixed, no-AI communication surface: an A-Z keyboard plus SPACE / BACKSPACE /
CLEAR / CONFIRM, a few fixed word shortcuts, fixed common phrases, and recent
messages. It holds the message buffer and a single highlighted target; the user
navigates (move/scan) and activates the highlight. Nothing here predicts,
ranks, reorders, or speaks — this is the low-confidence FALLBACK branch of
ADAPT-AAC and the manual baseline. Layout is fixed and never reordered.
"""

from dataclasses import dataclass

import config
import storage

RECENTS_FILE = "recents.json"
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
PUNCTUATION = ".,?"


@dataclass
class Target:
    kind: str          # char, word, space, backspace, clear, confirm, phrase, recent
    label: str
    value: str = ""


class Board:
    def __init__(self):
        self.message = ""
        self.index = 0
        self.recents = storage.load(RECENTS_FILE, []) or []
        self._build_targets()

    def _build_targets(self):
        targets = [Target("char", c, c) for c in LETTERS]
        targets += [Target("char", p, p) for p in PUNCTUATION]
        targets.append(Target("space", "SPACE", " "))
        targets.append(Target("backspace", "BACKSPACE"))
        targets.append(Target("clear", "CLEAR"))
        targets.append(Target("confirm", "CONFIRM"))
        targets += [Target("word", w, w) for w in config.WORD_SHORTCUTS]
        targets += [Target("phrase", p, p) for p in config.COMMON_PHRASES]
        targets += [Target("recent", r, r) for r in self.recents]
        self.targets = targets
        if self.index >= len(targets):
            self.index = 0

    def current(self):
        return self.targets[self.index]

    def move(self, delta):
        self.index = (self.index + delta) % len(self.targets)

    def scan_step(self):
        self.move(1)

    def activate(self):
        """Apply the highlighted target. Returns an action code for the controller:
        'edit' (buffer changed), 'confirm' (CONFIRM key), or 'ready' (phrase/recent
        loaded into the buffer, go to confirmation)."""
        target = self.current()
        kind = target.kind
        if kind == "char":
            self.message += target.value
        elif kind == "word":
            self.message += target.value + " "
        elif kind == "space":
            self.message += " "
        elif kind == "backspace":
            self.message = self.message[:-1]
        elif kind == "clear":
            self.message = ""
        elif kind == "confirm":
            return "confirm"
        elif kind in ("phrase", "recent"):
            self.message = target.value
            return "ready"
        return "edit"

    def clear_message(self):
        self.message = ""
        self.index = 0

    def add_recent(self, text):
        text = text.strip()
        if not text:
            return
        self.recents = [text] + [r for r in self.recents if r != text]
        self.recents = self.recents[: config.RECENT_MESSAGES_MAX]
        storage.save(RECENTS_FILE, self.recents)
        self._build_targets()
