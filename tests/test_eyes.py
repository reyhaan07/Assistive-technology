from vision.eyes import LEFT_EYE, RIGHT_EYE, _MIN_LANDMARKS, both_ears, ear

# 6 points p1..p6 for an open and a nearly-closed eye.
OPEN = [(0, 0), (3, 3), (7, 3), (10, 0), (7, -3), (3, -3)]
CLOSED = [(0, 0), (3, 0.2), (7, 0.2), (10, 0), (7, -0.2), (3, -0.2)]


def test_open_eye_has_higher_ear_than_closed():
    assert ear(OPEN) > ear(CLOSED)
    assert ear(OPEN) > 0.2
    assert ear(CLOSED) < 0.1


def test_degenerate_horizontal_returns_zero():
    points = [(5, 0), (5, 1), (5, 1), (5, 0), (5, -1), (5, -1)]  # corners coincide
    assert ear(points) == 0.0


def _landmarks(open_eye=True):
    points = [(0.0, 0.0)] * _MIN_LANDMARKS
    src = OPEN if open_eye else CLOSED
    for idx, p in zip(LEFT_EYE, src):
        points[idx] = p
    for idx, p in zip(RIGHT_EYE, src):
        points[idx] = p
    return points


def test_both_ears_from_valid_landmarks():
    left, right = both_ears(_landmarks(open_eye=True))
    assert left > 0.2 and right > 0.2


def test_both_ears_invalid_input():
    assert both_ears(None) is None
    assert both_ears([(0, 0)] * 10) is None  # too few landmarks
