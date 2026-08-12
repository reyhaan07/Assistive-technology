"""Input reliability — how trustworthy the current ocular signal is.

This is NOT medical/fatigue monitoring. It only answers: is the camera giving us
a usable, stable view of the eyes right now? It uses a short rolling window of
"valid frame" flags (face found AND both eyes measurable) and reports:

    GOOD        mostly valid recently
    UNCERTAIN   intermittent
    UNRELIABLE  mostly invalid / no data yet
"""

from collections import deque


class Reliability:
    def __init__(self, window=15, good=0.8, uncertain=0.4):
        self.recent = deque(maxlen=window)
        self.good = good
        self.uncertain = uncertain

    def update(self, face_present, eyes_valid):
        self.recent.append(1.0 if (face_present and eyes_valid) else 0.0)

    def status(self):
        if not self.recent:
            return "UNRELIABLE"
        ratio = sum(self.recent) / len(self.recent)
        if ratio >= self.good:
            return "GOOD"
        if ratio >= self.uncertain:
            return "UNCERTAIN"
        return "UNRELIABLE"
