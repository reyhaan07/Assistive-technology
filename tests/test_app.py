import pytest

import app as app_module


@pytest.fixture(autouse=True)
def reset_controller():
    app_module.controller.reset()
    yield


@pytest.fixture
def client():
    return app_module.app.test_client()


def test_app_starts_without_camera(client):
    res = client.get("/state")
    assert res.status_code == 200
    body = res.get_json()
    assert body["state"] == "IDLE"
    assert body["camera"] == "NOT INITIALIZED"
    assert body["input"] == "SIMULATION"


def test_simulate_advances_state(client):
    res = client.post("/simulate", json={"event": "BLINK"})
    assert res.status_code == 200
    assert res.get_json()["state"] == "PREDICTION_SHOWN"


def test_simulate_unknown_event(client):
    res = client.post("/simulate", json={"event": "XYZ"})
    assert res.status_code == 400
