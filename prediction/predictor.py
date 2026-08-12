"""Prediction interface — DEVELOPMENT STUB.

Establishes the data structures and the get_prediction() seam. It returns fixed
placeholder candidates so later stages can swap in real prediction without
changing callers. score is left None on purpose: confidence is NOT IMPLEMENTED
yet, so we do not invent one here.
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Candidate:
    text: str
    score: Optional[float] = None  # confidence NOT IMPLEMENTED yet
    source: str = "stub"


@dataclass
class PredictionResult:
    candidates: List[Candidate]
    context: str = ""
    timestamp: float = field(default_factory=time.time)


_STUB_TEXTS = ["Yes", "No", "Hello"]


def get_prediction(context: str = "") -> PredictionResult:
    candidates = [Candidate(text=t) for t in _STUB_TEXTS]
    return PredictionResult(candidates=candidates, context=context)
