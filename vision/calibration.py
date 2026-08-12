"""Per-user calibration.

One EAR threshold does not fit everyone (eye shape, camera, lighting), so we
learn per-user parameters from a short guided session:

    baseline      look normally        -> normal open EAR
    natural       blink normally x N    -> natural closure durations
    intentional   deliberate blinks x N -> intentional closure durations

From these we derive open/close EAR thresholds (with hysteresis) and the
duration boundary between natural and intentional blinks. Bad calibration is
rejected (see compute) rather than silently stored. Only parameters are kept —
never raw frames.
"""

from dataclasses import dataclass, field
from statistics import median
from typing import List, Tuple

from vision.blink import BlinkDetector, BlinkParams


@dataclass
class Calibration:
    ok: bool
    reason: str
    params: dict = field(default_factory=dict)


def _closure_durations(samples: List[Tuple[float, float]], close_thresh, open_thresh):
    """Segment (ear, t) samples into closures and return their durations."""
    detector = BlinkDetector(BlinkParams(open_thresh, close_thresh, 0.0, 1e9, 1e9, 0.0))
    durations = []
    for ear, t in samples:
        blink = detector.update(ear, t, True)
        if blink:
            durations.append(blink.duration)
    return durations


def compute(baseline_ears, natural_samples, intentional_samples,
            min_baseline=10, min_blinks=3, min_range=0.05, min_separation=0.15,
            max_close=2.0, cooldown=0.6, min_close_floor=0.05):
    """Turn collected samples into detector parameters, or explain why it failed."""
    if len(baseline_ears) < min_baseline:
        return Calibration(False, "Not enough baseline samples (face/eyes not detected?)")

    open_ear = median(baseline_ears)
    blink_ears = [e for e, _ in natural_samples] + [e for e, _ in intentional_samples]
    if not blink_ears:
        return Calibration(False, "No blink samples collected")

    closed_ear = min(blink_ears)
    span = open_ear - closed_ear
    if span < min_range:
        return Calibration(False, "No clear difference between open and closed eyes")

    close_thresh = closed_ear + 0.35 * span
    open_thresh = closed_ear + 0.55 * span

    natural = _closure_durations(natural_samples, close_thresh, open_thresh)
    intentional = _closure_durations(intentional_samples, close_thresh, open_thresh)
    if len(natural) < min_blinks or len(intentional) < min_blinks:
        return Calibration(False, "Too few natural/intentional blinks detected")

    natural_med = median(natural)
    intentional_med = median(intentional)
    if intentional_med - natural_med < min_separation:
        return Calibration(False, "Natural and intentional blinks are too similar")

    params = {
        "open_thresh": open_thresh,
        "close_thresh": close_thresh,
        "min_close": max(min_close_floor, natural_med * 0.5),
        "max_close": max_close,
        "intentional_min": (natural_med + intentional_med) / 2.0,
        "cooldown": cooldown,
        "open_ear": open_ear,
        "closed_ear": closed_ear,
    }
    return Calibration(True, "OK", params)


class Calibrator:
    """Collects samples per phase while the user is guided through calibration."""

    PHASES = ("baseline", "natural", "intentional")

    def __init__(self):
        self.baseline = []
        self.natural = []
        self.intentional = []
        self.phase = None

    def start(self, phase):
        if phase not in self.PHASES:
            raise ValueError(f"unknown phase: {phase}")
        self.phase = phase

    def feed(self, ear, t, face_present):
        if not face_present or self.phase is None:
            return
        if self.phase == "baseline":
            self.baseline.append(ear)
        elif self.phase == "natural":
            self.natural.append((ear, t))
        else:
            self.intentional.append((ear, t))

    def counts(self):
        return {
            "baseline": len(self.baseline),
            "natural": len(self.natural),
            "intentional": len(self.intentional),
        }

    def finish(self):
        self.phase = None
        return compute(self.baseline, self.natural, self.intentional)
