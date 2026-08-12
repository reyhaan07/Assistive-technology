"""Minimal local JSON storage.

A single place for future persistence (calibration, profile, phrases, research
logs). No database. Callers pass a filename; data lives under data/.
"""

import json
import os

DATA_DIR = "data"


def _path(name: str) -> str:
    return os.path.join(DATA_DIR, name)


def load(name: str, default=None):
    path = _path(name)
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def save(name: str, data) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_path(name), "w") as f:
        json.dump(data, f, indent=2)
