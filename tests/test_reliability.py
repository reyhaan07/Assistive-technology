from vision.reliability import Reliability


def test_all_valid_is_good():
    r = Reliability(window=10)
    for _ in range(10):
        r.update(True, True)
    assert r.status() == "GOOD"


def test_no_data_is_unreliable():
    assert Reliability().status() == "UNRELIABLE"


def test_all_invalid_is_unreliable():
    r = Reliability(window=10)
    for _ in range(10):
        r.update(False, False)
    assert r.status() == "UNRELIABLE"


def test_intermittent_is_uncertain():
    r = Reliability(window=10)
    for i in range(10):
        valid = i % 2 == 0  # 50% valid
        r.update(valid, valid)
    assert r.status() == "UNCERTAIN"
