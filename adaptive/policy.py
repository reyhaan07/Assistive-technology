"""Adaptive policy — STUB INTERFACE ONLY (Stage 6).

The research core lives here later: map (confidence, interaction cost, input
reliability) to an interaction mode. Only the interface is defined now; the
decision is not implemented, so we do not fake one.
"""

from enum import Enum


class Mode(Enum):
    CONFIRM = "CONFIRM"
    CHOICES = "CHOICES"
    FALLBACK = "FALLBACK"


def choose_mode(confidence=None, cost=None, reliability=None, prediction=None) -> Mode:
    raise NotImplementedError("Adaptive policy is implemented in Stage 6")
