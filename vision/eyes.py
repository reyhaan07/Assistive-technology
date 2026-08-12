"""Eye-opening metric (Eye Aspect Ratio).

Pure geometry on pixel-space (x, y) points — no camera or mediapipe here, so it
unit-tests headless. Landmark indices are the standard MediaPipe Face Mesh eye
points used for EAR. They are the commonly published indices; they have NOT been
visually verified against a live face in this headless environment.

EAR (Soukupova & Cech), per eye, for 6 points p1..p6:
    EAR = (dist(p2, p6) + dist(p3, p5)) / (2 * dist(p1, p4))
p1/p4 are the eye corners (horizontal); p2/p3 upper lid, p5/p6 lower lid.
"""

import math

# Order per eye: [p1 corner, p2 upper, p3 upper, p4 corner, p5 lower, p6 lower]
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

# Highest index we touch; a landmark list must be at least this long + 1.
_MIN_LANDMARKS = max(LEFT_EYE + RIGHT_EYE) + 1


def ear(points):
    """EAR from 6 (x, y) points ordered p1..p6. Returns 0.0 if degenerate."""
    p1, p2, p3, p4, p5, p6 = points
    horizontal = math.dist(p1, p4)
    if horizontal < 1e-6:
        return 0.0
    vertical = math.dist(p2, p6) + math.dist(p3, p5)
    return vertical / (2.0 * horizontal)


def both_ears(landmarks):
    """Return (left_ear, right_ear) from a landmark list, or None if unusable."""
    if landmarks is None or len(landmarks) < _MIN_LANDMARKS:
        return None
    left = ear([landmarks[i] for i in LEFT_EYE])
    right = ear([landmarks[i] for i in RIGHT_EYE])
    return left, right
