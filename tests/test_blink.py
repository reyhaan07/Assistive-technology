from vision.blink import BlinkDetector, BlinkParams, Phase


def params(**kw):
    base = dict(open_thresh=0.25, close_thresh=0.18, min_close=0.05,
                max_close=1.0, intentional_min=0.3, cooldown=0.5)
    base.update(kw)
    return BlinkParams(**base)


def feed(detector, sequence):
    return [b for b in (detector.update(ear, t, True) for ear, t in sequence) if b]


def test_valid_blink_open_close_reopen():
    d = BlinkDetector(params())
    blinks = feed(d, [(0.3, 0.0), (0.1, 0.1), (0.1, 0.2), (0.3, 0.25)])
    assert len(blinks) == 1
    assert blinks[0].kind == "natural"  # 0.15s closure


def test_intentional_blink_is_longer():
    d = BlinkDetector(params())
    blinks = feed(d, [(0.3, 0.0), (0.1, 0.1), (0.1, 0.5), (0.3, 0.55)])
    assert len(blinks) == 1
    assert blinks[0].kind == "intentional"  # 0.45s closure


def test_too_short_closure_is_ignored():
    d = BlinkDetector(params())
    assert feed(d, [(0.3, 0.0), (0.1, 0.10), (0.3, 0.12)]) == []  # 0.02s


def test_too_long_closure_is_not_a_blink():
    d = BlinkDetector(params())
    assert feed(d, [(0.3, 0.0), (0.1, 0.1), (0.1, 2.0), (0.3, 2.1)]) == []  # 2.0s


def test_incomplete_sequence_no_reopen():
    d = BlinkDetector(params())
    assert feed(d, [(0.3, 0.0), (0.1, 0.1), (0.1, 0.2)]) == []  # never reopened


def test_face_loss_mid_closure_does_not_blink():
    d = BlinkDetector(params())
    d.update(0.3, 0.0, True)
    d.update(0.1, 0.1, True)                     # closed
    assert d.update(0.0, 0.2, face_present=False) is None
    assert d.phase == Phase.OPEN
    assert d.update(0.3, 0.3, True) is None      # reopen after loss: no blink


def test_cooldown_blocks_immediate_second_blink():
    d = BlinkDetector(params(cooldown=0.5))
    d.update(0.3, 0.0, True); d.update(0.1, 0.1, True)
    assert d.update(0.3, 0.25, True) is not None          # first blink at t=0.25
    d.update(0.1, 0.3, True)
    assert d.update(0.3, 0.4, True) is None               # within cooldown
    d.update(0.1, 0.8, True)
    assert d.update(0.3, 0.95, True) is not None           # after cooldown
