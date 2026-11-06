"""Accurate place detection from noisy GPS fixes.

Accuracy is preferred over speed (decisions may take up to ~1 minute):

1. Smoothing  – fixes from the last GPS_WINDOW_SECONDS are combined with
   inverse-variance weights (a ±5 m fix counts 100x more than a ±50 m fix).
2. Outliers   – fixes that disagree with the others by more than their own
   error bars are dropped (GPS "jumps", reflections between buildings).
3. Certainty  – you only *arrive* when the uncertainty circle is (mostly)
   inside a place, and only *leave* when you are clearly outside it.
4. Ambiguity  – when two saved places are too close to tell apart with the
   current accuracy, nothing switches.
5. Dwell      – a decision must hold for ARRIVE/LEAVE_DWELL_SECONDS with
   several good fixes before it is applied, so one bad fix never switches.
"""
import math
import statistics
import threading
from collections import deque
from typing import List, Optional, Tuple

from config import (
    ARRIVE_DWELL_SECONDS,
    GPS_MAX_FIX_ACCURACY_M,
    GPS_MIN_FIXES,
    GPS_WINDOW_SECONDS,
    LEAVE_DWELL_SECONDS,
    PLACE_REFINE_AFTER_SECONDS,
    PLACE_REFINE_MAX_ACCURACY_M,
    SAVE_PLACE_MAX_ACCURACY_M,
    SAVE_PLACE_MIN_FIXES,
    SAVE_PLACE_MIN_SECONDS,
)
from places import haversine_m

M_PER_DEG_LAT = 111_320.0


def _offset_m(lat0, lon0, lat, lon) -> Tuple[float, float]:
    """Local east/north metres of (lat, lon) relative to (lat0, lon0)."""
    return ((lon - lon0) * M_PER_DEG_LAT * math.cos(math.radians(lat0)),
            (lat - lat0) * M_PER_DEG_LAT)


def _weighted_mean(fixes: List[dict]) -> Tuple[float, float]:
    w = [1.0 / max(f["accuracy"], 1.0) ** 2 for f in fixes]
    sw = sum(w)
    return (sum(f["lat"] * wi for f, wi in zip(fixes, w)) / sw,
            sum(f["lon"] * wi for f, wi in zip(fixes, w)) / sw)


def smooth_fixes(fixes: List[dict], recent_seconds: float = 10.0) -> Optional[dict]:
    """Inverse-variance weighted mean with outlier rejection.

    Movement-aware: the newest `recent_seconds` of fixes anchor the estimate, and
    older fixes are only used if they agree with where the user is *now*. So
    walking somewhere new is picked up within seconds, while standing still
    still averages the whole window. (Brief GPS jumps are then filtered by the
    dwell time in LocationTracker.)

    Returns {"lat", "lon", "accuracy", "fixes", "span"} or None.
    The reported accuracy is never better than the best single fix, because
    GPS errors between consecutive fixes are correlated.
    """
    if not fixes:
        return None
    used = list(fixes)
    t_max = max(f["time"] for f in used)
    recent = [f for f in used if f["time"] >= t_max - recent_seconds]
    if len(recent) >= 3:
        # Median, not mean: one wild fix among the newest cannot move the anchor.
        lat = statistics.median(f["lat"] for f in recent)
        lon = statistics.median(f["lon"] for f in recent)
        consistent = [f for f in used if f in recent
                      or haversine_m(lat, lon, f["lat"], f["lon"]) <= 2 * f["accuracy"] + 5]
        used = consistent or recent
    for _ in range(3):
        lat, lon = _weighted_mean(used)
        kept = [f for f in used if haversine_m(lat, lon, f["lat"], f["lon"]) <= 2 * f["accuracy"] + 5]
        if len(kept) == len(used) or not kept:
            break
        used = kept
    w = [1.0 / max(f["accuracy"], 1.0) ** 2 for f in used]
    combined = 1.0 / math.sqrt(sum(w))
    best = min(f["accuracy"] for f in used)
    accuracy = max(combined, best * 0.8, 3.0)
    times = [f["time"] for f in used]
    return {"lat": lat, "lon": lon, "accuracy": round(accuracy, 1),
            "fixes": len(used), "span": max(times) - min(times)}


class LocationTracker:
    def __init__(self, places):
        self.places = places
        self.fixes: deque = deque()
        self.lock = threading.Lock()
        self.current = None           # confirmed place dict
        self.arrived_at = 0.0
        self.refined_this_visit = False
        self.pending = None           # ("place_id" | None, since, fixes_seen)
        self.estimate = None
        self.status = "no_fix"

    # -- input ----------------------------------------------------------------
    def add_fix(self, lat: float, lon: float, accuracy: float, now: float) -> None:
        with self.lock:
            self.fixes.append({"lat": lat, "lon": lon, "accuracy": float(accuracy), "time": now})
            while self.fixes and now - self.fixes[0]["time"] > GPS_WINDOW_SECONDS:
                self.fixes.popleft()

    def good_estimate(self) -> Optional[dict]:
        with self.lock:
            good = [f for f in self.fixes if f["accuracy"] <= GPS_MAX_FIX_ACCURACY_M]
        return smooth_fixes(good)

    # -- classification ----------------------------------------------------------
    def classify(self, est: dict):
        """Return (target, reason). target: place dict, None (outside all), or "unknown"."""
        acc = est["accuracy"]
        scored = []
        for p in self.places.list():
            d = haversine_m(est["lat"], est["lon"], p["lat"], p["lon"])
            scored.append((d, p))
        scored.sort(key=lambda x: x[0])

        possible = [(d, p) for d, p in scored if d - acc <= p["radius"]]
        if self.current:
            cur = next(((d, p) for d, p in scored if p["id"] == self.current["id"]), None)
            if cur:
                d, p = cur
                # Hysteresis: stay while not clearly outside.
                if d <= p["radius"] + max(acc, 20) and not any(
                        q["id"] != p["id"] and dq + 0.5 * acc <= q["radius"] and dq + acc < d
                        for dq, q in possible):
                    return p, "inside"
        if not possible:
            return None, "outside"

        d1, p1 = possible[0]
        confident = d1 + 0.5 * acc <= p1["radius"]
        if len(possible) > 1:
            d2 = possible[1][0]
            if d2 - d1 < acc:
                return "unknown", "ambiguous"
        if confident:
            return p1, "inside"
        return "unknown", "uncertain"

    # -- main update ---------------------------------------------------------------
    def update(self, lat: float, lon: float, accuracy: float, now: float) -> dict:
        self.add_fix(lat, lon, accuracy, now)
        est = self.good_estimate()
        self.estimate = est
        result = {"arrived": False, "left": False, "place": self.current, "estimate": est}

        if est is None or est["fixes"] < GPS_MIN_FIXES:
            self.status = "weak" if accuracy > GPS_MAX_FIX_ACCURACY_M else "measuring"
            self.pending = None
            return dict(result, status=self.status)

        target, reason = self.classify(est)
        current_id = self.current["id"] if self.current else None

        if target == "unknown":
            self.pending = None
            self.status = reason
        else:
            target_id = target["id"] if target else None
            if target_id == current_id:
                self.pending = None
                self.status = "inside" if target else "outside"
                if target:
                    self.current = target
                    self._maybe_refine(est, now)
            else:
                if not self.pending or self.pending[0] != target_id:
                    self.pending = (target_id, now, 0)
                pid, since, seen = self.pending
                self.pending = (pid, since, seen + 1)
                dwell = ARRIVE_DWELL_SECONDS if target else LEAVE_DWELL_SECONDS
                waited = now - since
                if waited >= dwell and self.pending[2] >= GPS_MIN_FIXES:
                    result["left"] = self.current is not None
                    result["arrived"] = target is not None
                    self.current = target
                    self.arrived_at = now
                    self.refined_this_visit = False
                    self.pending = None
                    self.status = "inside" if target else "outside"
                else:
                    self.status = "confirming"
                    result["confirming"] = {
                        "place": target["name"] if target else None,
                        "seconds_left": max(0, round(dwell - waited)),
                    }
        result["place"] = self.current
        result["status"] = self.status
        return result

    def _maybe_refine(self, est: dict, now: float) -> None:
        """Learn the true centre of a place, but only after really staying there."""
        if (self.current and not self.refined_this_visit
                and now - self.arrived_at >= PLACE_REFINE_AFTER_SECONDS
                and est["accuracy"] <= PLACE_REFINE_MAX_ACCURACY_M
                and est["span"] >= 20):
            self.places.refine(self.current["id"], est["lat"], est["lon"], weight=0.2)
            self.refined_this_visit = True

    def forget_place(self, place_id: str) -> None:
        if self.current and self.current["id"] == place_id:
            self.current = None
        if self.pending and self.pending[0] == place_id:
            self.pending = None

    def save_estimate(self) -> Tuple[Optional[dict], str]:
        """Precise position for saving a new place, or a reason to keep measuring."""
        est = self.good_estimate()
        if est is None:
            return None, "Waiting for GPS…"
        if est["fixes"] < SAVE_PLACE_MIN_FIXES or est["span"] < SAVE_PLACE_MIN_SECONDS:
            return None, f"Measuring position… ({est['fixes']} readings, ±{round(est['accuracy'])} m)"
        if est["accuracy"] > SAVE_PLACE_MAX_ACCURACY_M:
            return None, (f"Position not precise enough yet (±{round(est['accuracy'])} m, need "
                          f"±{SAVE_PLACE_MAX_ACCURACY_M} m). Stay still, or move near a window / outside.")
        return est, "ok"
