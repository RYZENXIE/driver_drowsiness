"""Tests for the detection logic. Run:  python test_logic.py"""
from logic import Config, Metrics, Monitor

FPS = 10
GOOD = Metrics(ear=0.30, mar=0.05, roll=0.0, pitch=1.30)


def make_calibrated():
    m = Monitor(Config(), start_time=0.0)
    t = 0.0
    for _ in range(Config().calib_frames):
        t += 1 / FPS
        m.update(GOOD, t)
    assert m.calibrated, "calibration should finish"
    return m, t


def run(m, t, metrics, seconds):
    """Feed the same metrics for `seconds`; return (time, last result)."""
    r = None
    for _ in range(int(seconds * FPS)):
        t += 1 / FPS
        r = m.update(metrics, t)
    return t, r


def test_normal_blink_no_alarm():
    m, t = make_calibrated()
    t, r = run(m, t, Metrics(0.10, 0.05, 0, 1.30), 0.3)
    t, r = run(m, t, GOOD, 1)
    assert r.level == 0


def test_eyes_closed_levels():
    m, t = make_calibrated()
    closed = Metrics(0.10, 0.05, 0, 1.30)
    t, r = run(m, t, closed, 1.2)
    assert r.level == 1, r
    t, r = run(m, t, closed, 1.0)
    assert r.level == 2, r
    t, r = run(m, t, closed, 2.0)
    assert r.level == 3, r
    t, r = run(m, t, GOOD, 0.5)
    assert r.level == 0, "alarm must stop when eyes open"


def test_no_face_emergency():
    m, t = make_calibrated()
    t, r = run(m, t, None, 1.0)
    assert r.level == 0
    t, r = run(m, t, None, 2.5)
    assert r.level == 3
    t, r = run(m, t, GOOD, 0.3)
    assert r.level == 0


def test_head_tilt_warning():
    m, t = make_calibrated()
    tilted = Metrics(0.30, 0.05, 40.0, 1.30)
    t, r = run(m, t, tilted, 3.2)
    assert r.level == 2, r
    t, r = run(m, t, tilted, 3.5)
    assert r.level == 3, r


def test_head_down_with_closed_eyes_is_emergency():
    m, t = make_calibrated()
    bad = Metrics(0.10, 0.05, 0.0, 0.90)  # pitch changed, eyes closed
    t, r = run(m, t, bad, 2.5)
    assert r.level == 3, r


def test_repeated_yawns_caution():
    m, t = make_calibrated()
    yawn = Metrics(0.30, 0.70, 0, 1.30)
    t, r = run(m, t, yawn, 1.7)
    assert r.level == 0 and r.yawns == 1
    t, r = run(m, t, GOOD, 1.0)
    t, r = run(m, t, yawn, 1.7)
    assert r.level == 1 and r.yawns == 2, r


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print("PASS", fn.__name__)
    print(f"All {len(tests)} tests passed.")
