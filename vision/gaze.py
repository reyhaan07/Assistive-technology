"""Experimental gaze direction — DEVELOPMENT / EXPERIMENTAL.

A crude LEFT / CENTER / RIGHT estimate from the iris position between the eye
corners (needs refine_landmarks, i.e. >= 478 landmarks). It is NOT connected to
communication and never triggers speech. If it is unreliable, ignore it — blink
is the real Stage 2 input.
"""

_LEFT_IRIS = 468   # iris landmark blocks start here with refine_landmarks
_RIGHT_IRIS = 473
_LEFT_CORNERS = (33, 133)
_RIGHT_CORNERS = (362, 263)
_MIN_LANDMARKS = 478


def _ratio(iris_x, corner_a, corner_b):
    lo, hi = sorted((corner_a[0], corner_b[0]))
    span = hi - lo
    if span < 1e-6:
        return 0.5
    return (iris_x - lo) / span


def direction(landmarks, left_bias=0.4, right_bias=0.6):
    """Return "LEFT" / "CENTER" / "RIGHT", or None if iris landmarks are missing."""
    if landmarks is None or len(landmarks) < _MIN_LANDMARKS:
        return None

    left = _ratio(landmarks[_LEFT_IRIS][0], landmarks[_LEFT_CORNERS[0]], landmarks[_LEFT_CORNERS[1]])
    right = _ratio(landmarks[_RIGHT_IRIS][0], landmarks[_RIGHT_CORNERS[0]], landmarks[_RIGHT_CORNERS[1]])
    ratio = (left + right) / 2.0

    if ratio < left_bias:
        return "LEFT"
    if ratio > right_bias:
        return "RIGHT"
    return "CENTER"
