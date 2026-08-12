from vision.calibration import Calibrator, compute


def blinks(n, closed_frames, start=0.0, dt=0.02, gap=0.3, open_ear=0.30, closed_ear=0.10):
    """Build an (ear, t) stream of n blinks, each closed for closed_frames frames."""
    samples = []
    t = start
    for _ in range(n):
        samples.append((open_ear, round(t, 3))); t = round(t + dt, 3)
        for _ in range(closed_frames):
            samples.append((closed_ear, round(t, 3))); t = round(t + dt, 3)
        samples.append((open_ear, round(t, 3))); t = round(t + gap, 3)
    return samples


def test_valid_calibration():
    result = compute([0.30] * 20, blinks(4, 3), blinks(4, 16, start=50.0))
    assert result.ok, result.reason
    assert result.params["open_thresh"] > result.params["close_thresh"]
    assert result.params["intentional_min"] > 0


def test_insufficient_baseline_fails():
    result = compute([0.30] * 5, blinks(4, 3), blinks(4, 16, start=50.0))
    assert not result.ok
    assert "baseline" in result.reason.lower()


def test_no_open_closed_difference_fails():
    # eyes never really close: blink "closed" EAR ~ open EAR
    result = compute([0.30] * 20, blinks(4, 3, closed_ear=0.28), blinks(4, 16, start=50.0, closed_ear=0.28))
    assert not result.ok


def test_natural_and_intentional_too_similar_fails():
    result = compute([0.30] * 20, blinks(4, 3), blinks(4, 3, start=50.0))
    assert not result.ok


def test_calibrator_collects_and_computes():
    c = Calibrator()
    c.start("baseline")
    for _ in range(20):
        c.feed(0.30, 0.0, True)
    c.start("natural")
    for ear, t in blinks(4, 3):
        c.feed(ear, t, True)
    c.start("intentional")
    for ear, t in blinks(4, 16, start=50.0):
        c.feed(ear, t, True)
    assert c.counts()["baseline"] == 20
    result = c.finish()
    assert result.ok, result.reason
