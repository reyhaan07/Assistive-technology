from prediction.predictor import Candidate, PredictionResult, get_prediction


def test_candidate_defaults():
    c = Candidate(text="hi")
    assert c.text == "hi"
    assert c.score is None  # confidence not implemented yet
    assert c.source == "stub"


def test_prediction_result():
    r = PredictionResult(candidates=[Candidate("a")], context="ctx")
    assert r.context == "ctx"
    assert r.timestamp > 0


def test_stub_output():
    r = get_prediction("")
    assert len(r.candidates) >= 1
    assert all(c.score is None for c in r.candidates)
