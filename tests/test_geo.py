"""Simulated real-world GPS: noise, jumps, drive-bys, neighbouring shops."""
import math
import random

from geo import LocationTracker, smooth_fixes
from places import PlaceBook, haversine_m

BASE = (51.5000, -0.1200)
M = 1 / 111_320  # degrees latitude per metre


def at(north_m=0.0, east_m=0.0):
    return (BASE[0] + north_m * M, BASE[1] + east_m * M / math.cos(math.radians(BASE[0])))


def noisy(rng, pos, sigma):
    return (pos[0] + rng.gauss(0, sigma) * M, pos[1] + rng.gauss(0, sigma) * M / math.cos(math.radians(BASE[0])))


def setup(tmp_path, places):
    book = PlaceBook(str(tmp_path / "pl.json"), str(tmp_path / "pr.json"))
    ids = {}
    for name, pos, radius in places:
        ids[name] = book.add({"name": name, "context": "cafe", "lat": pos[0], "lon": pos[1], "radius": radius})["id"]
    return LocationTracker(book), ids


def feed(tr, rng, pos, seconds, acc=8, sigma=5, t0=0.0, log=None):
    t = t0
    for _ in range(seconds):
        lat, lon = noisy(rng, pos, sigma)
        res = tr.update(lat, lon, acc, t)
        if log is not None and (res["arrived"] or res["left"]):
            log.append((t, res["place"]["name"] if res["place"] else None))
        t += 1
    return t


def test_smoothing_beats_single_fixes():
    rng = random.Random(1)
    fixes = []
    for i in range(30):
        lat, lon = noisy(rng, BASE, 8)
        fixes.append({"lat": lat, "lon": lon, "accuracy": 10, "time": i})
    fixes.append({"lat": BASE[0] + 300 * M, "lon": BASE[1], "accuracy": 10, "time": 30})  # jump
    est = smooth_fixes(fixes)
    assert haversine_m(est["lat"], est["lon"], *BASE) < 5
    assert est["fixes"] == 30  # outlier rejected


def test_walk_in_arrives_within_a_minute_and_not_before(tmp_path):
    rng = random.Random(2)
    tr, _ = setup(tmp_path, [("Cafe", BASE, 50)])
    log = []
    t = 0
    for d in range(200, 0, -2):  # walk in from 200 m north at ~2 m/s
        t = feed(tr, rng, at(d), 1, t0=t, log=log)
    assert log == []  # never "arrived" while still outside
    t_in = t
    feed(tr, rng, at(5), 70, t0=t, log=log)
    assert log and log[0][1] == "Cafe"
    assert log[0][0] - t_in <= 60


def test_driving_past_does_not_arrive(tmp_path):
    rng = random.Random(3)
    tr, _ = setup(tmp_path, [("Cafe", BASE, 50)])
    log = []
    t = 0
    for d in range(-300, 301, 12):  # 12 m/s drive straight through
        t = feed(tr, rng, at(d), 1, t0=t, log=log)
    assert log == []


def test_neighbouring_shops_are_told_apart_outdoors(tmp_path):
    rng = random.Random(4)
    tr, _ = setup(tmp_path, [("Bakery", at(0, 0), 15), ("Bank", at(0, 40), 15)])
    log = []
    feed(tr, rng, at(0, 40), 60, acc=4, sigma=3, log=log)
    assert log == [(log[0][0], "Bank")]


def test_neighbouring_shops_indoors_never_guess(tmp_path):
    rng = random.Random(5)
    tr, _ = setup(tmp_path, [("Bakery", at(0, 0), 25), ("Bank", at(0, 40), 25)])
    log = []
    feed(tr, rng, at(0, 20), 120, acc=35, sigma=25, log=log)  # between them, poor accuracy
    assert log == []
    assert tr.status in ("ambiguous", "uncertain")


def test_gps_jump_does_not_cause_leaving(tmp_path):
    rng = random.Random(6)
    tr, _ = setup(tmp_path, [("Cafe", BASE, 50)])
    log = []
    t = feed(tr, rng, BASE, 40, log=log)
    assert log[-1][1] == "Cafe"
    for _ in range(5):  # 5 s of a confidently wrong jump 400 m away
        tr.update(*at(400), 10, t)
        t += 1
    feed(tr, rng, BASE, 60, t0=t, log=log)
    assert log[-1][1] == "Cafe" and len(log) == 1


def test_leaving_is_detected(tmp_path):
    rng = random.Random(7)
    tr, _ = setup(tmp_path, [("Cafe", BASE, 50)])
    log = []
    t = feed(tr, rng, BASE, 40, log=log)
    t = feed(tr, rng, at(500), 90, t0=t, log=log)
    assert [name for _, name in log] == ["Cafe", None]


def test_weak_fixes_never_decide(tmp_path):
    rng = random.Random(8)
    tr, _ = setup(tmp_path, [("Cafe", BASE, 50)])
    log = []
    feed(tr, rng, BASE, 120, acc=300, sigma=10, log=log)
    assert log == [] and tr.status == "weak"


def test_place_centre_is_learned_only_after_staying(tmp_path):
    rng = random.Random(9)
    true_spot = at(12, 0)  # saved 12 m off
    tr, ids = setup(tmp_path, [("Cafe", BASE, 50)])
    feed(tr, rng, true_spot, 100, acc=6, sigma=3)
    assert tr.places.get(ids["Cafe"]).get("visits", 0) == 0
    feed(tr, rng, true_spot, 100, acc=6, sigma=3, t0=100)
    place = tr.places.get(ids["Cafe"])
    assert place["visits"] == 1
    assert haversine_m(place["lat"], place["lon"], *true_spot) < 11  # moved towards the truth


def test_save_estimate_requires_precise_measurement(tmp_path):
    rng = random.Random(10)
    tr, _ = setup(tmp_path, [])
    feed(tr, rng, BASE, 3, acc=6)
    assert tr.save_estimate()[0] is None
    feed(tr, rng, BASE, 15, acc=60, sigma=40, t0=3)
    est, msg = tr.save_estimate()
    feed(tr, rng, BASE, 15, acc=5, sigma=3, t0=50)
    est, msg = tr.save_estimate()
    assert est and haversine_m(est["lat"], est["lon"], *BASE) < 5
