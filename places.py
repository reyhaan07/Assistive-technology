"""Saved places (GPS), the user's profile / medical card and phrase tokens.

Places let GestureTalk switch context automatically when the user arrives
somewhere (e.g. their regular cafe) and remember what they usually ask for
there ("my usual" order). The profile holds the medical card that can be
spoken at a hospital. Everything is stored locally in JSON files.
"""
import json
import math
import os
import re
import threading
import uuid
from typing import Dict, List, Optional

from config import CONTEXTS, PLACES_FILE, PROFILE_FILE

PROFILE_FIELDS = ["name", "conditions", "allergies", "medications", "blood_type",
                  "emergency_contact", "emergency_phone", "notes"]
DEFAULT_PLACE_RADIUS = 150  # metres


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        print(f"[places] Could not read {path}: {exc}")
        return default


def _write_json(path, data) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _float(value, lo, hi) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi and not math.isnan(v) else None


class PlaceBook:
    def __init__(self, places_file: str = PLACES_FILE, profile_file: str = PROFILE_FILE,
                 contexts=CONTEXTS):
        self.places_file = places_file
        self.profile_file = profile_file
        self.contexts = list(contexts)
        self._lock = threading.RLock()
        raw_places = _read_json(places_file, [])
        self._places: List[dict] = [p for p in raw_places if isinstance(p, dict) and "id" in p]
        raw_profile = _read_json(profile_file, {})
        self._profile = {f: str(raw_profile.get(f, "") or "") for f in PROFILE_FIELDS}

    # -- places ---------------------------------------------------------------
    def _clean_place(self, data: dict, existing: Optional[dict] = None) -> dict:
        place = dict(existing or {})
        if "name" in data or not existing:
            place["name"] = str(data.get("name", "")).strip()[:60]
        if "context" in data or not existing:
            ctx = str(data.get("context", "")).strip().lower()
            if ctx not in self.contexts:
                raise ValueError(f"context must be one of: {', '.join(self.contexts)}")
            place["context"] = ctx
        if "lat" in data or "lon" in data or not existing:
            lat, lon = _float(data.get("lat"), -90, 90), _float(data.get("lon"), -180, 180)
            if lat is None or lon is None:
                raise ValueError("valid lat and lon are required")
            place["lat"], place["lon"] = round(lat, 6), round(lon, 6)
        if "radius" in data or not existing:
            place["radius"] = _float(data.get("radius", DEFAULT_PLACE_RADIUS), 10, 5000) or DEFAULT_PLACE_RADIUS
        if "usual" in data or not existing:
            place["usual"] = str(data.get("usual", "") or "").strip()[:300]
        if not place["name"]:
            raise ValueError("name is required")
        return place

    def list(self) -> List[dict]:
        with self._lock:
            return [dict(p) for p in self._places]

    def get(self, place_id: str) -> Optional[dict]:
        with self._lock:
            for p in self._places:
                if p["id"] == place_id:
                    return dict(p)
        return None

    def add(self, data: dict) -> dict:
        place = self._clean_place(data)
        place["id"] = uuid.uuid4().hex[:10]
        with self._lock:
            self._places.append(place)
            _write_json(self.places_file, self._places)
        return dict(place)

    def update(self, place_id: str, data: dict) -> Optional[dict]:
        with self._lock:
            for i, p in enumerate(self._places):
                if p["id"] == place_id:
                    self._places[i] = self._clean_place(data, p)
                    _write_json(self.places_file, self._places)
                    return dict(self._places[i])
        return None

    def delete(self, place_id: str) -> bool:
        with self._lock:
            before = len(self._places)
            self._places = [p for p in self._places if p["id"] != place_id]
            if len(self._places) != before:
                _write_json(self.places_file, self._places)
                return True
        return False

    def nearest(self, lat: float, lon: float) -> Optional[dict]:
        """Closest saved place whose radius contains the point."""
        best, best_d = None, float("inf")
        with self._lock:
            for p in self._places:
                d = haversine_m(lat, lon, p["lat"], p["lon"])
                if d <= p["radius"] and d < best_d:
                    best, best_d = dict(p, distance=round(d)), d
        return best

    def refine(self, place_id: str, lat: float, lon: float, weight: float = 0.1) -> None:
        """Nudge a place's centre towards where the user actually is (learns with visits)."""
        with self._lock:
            for p in self._places:
                if p["id"] == place_id:
                    p["lat"] = round(p["lat"] + (lat - p["lat"]) * weight, 6)
                    p["lon"] = round(p["lon"] + (lon - p["lon"]) * weight, 6)
                    p["visits"] = int(p.get("visits", 0)) + 1
                    _write_json(self.places_file, self._places)
                    return

    def usual_for(self, context: str, place: Optional[dict] = None) -> str:
        if place and place.get("usual"):
            return place["usual"]
        with self._lock:
            for p in self._places:
                if p["context"] == context and p.get("usual"):
                    return p["usual"]
        return ""

    # -- profile / medical card ----------------------------------------------------
    def profile(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._profile)

    def set_profile(self, data: dict) -> Dict[str, str]:
        with self._lock:
            for f in PROFILE_FIELDS:
                if f in data:
                    self._profile[f] = str(data.get(f) or "").strip()[:300]
            _write_json(self.profile_file, self._profile)
            return dict(self._profile)

    def medical_text(self) -> str:
        p = self.profile()
        parts = []
        if p["name"]:
            parts.append(f"My name is {p['name']}.")
        if p["conditions"]:
            parts.append(f"I have {p['conditions']}.")
        parts.append(f"I am allergic to {p['allergies']}." if p["allergies"] else "")
        if p["medications"]:
            parts.append(f"I take {p['medications']}.")
        if p["blood_type"]:
            parts.append(f"My blood type is {p['blood_type']}.")
        if p["emergency_contact"] or p["emergency_phone"]:
            who = p["emergency_contact"] or "my emergency contact"
            phone = f" on {p['emergency_phone']}" if p["emergency_phone"] else ""
            parts.append(f"Please contact {who}{phone}.")
        if p["notes"]:
            parts.append(p["notes"])
        return " ".join(x for x in parts if x)


TOKEN_RE = re.compile(r"\{(usual|medical|place|name)(?:\|([^}]*))?\}")


def resolve_tokens(text: str, values: Dict[str, str]) -> str:
    """Replace {usual}, {medical}, {place}, {name}; `{usual|fallback}` uses fallback when empty."""
    def sub(m):
        return values.get(m.group(1)) or (m.group(2) or "")
    out = TOKEN_RE.sub(sub, text)
    return re.sub(r"\s{2,}", " ", out).strip(" :,") or text
