"""Frame animation tests: no network, no rembg (the mask is given), synthetic frame.

Skipped when numpy / opencv are missing (they are the optional [animate] extra).
"""
import json, os, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from series_factory import animate  # noqa: E402

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")


def test_curves_are_bounded_and_end_at_zero():
    for f in (lambda t: animate.pulse(t, 1, 0.5), lambda t: animate.hold(t, 1, 2)):
        vals = [f(i / 100) for i in range(0, 400)]
        assert min(vals) >= 0 and max(vals) <= 1.0001
        assert f(0.5) == 0 and f(3.5) == 0
    assert animate.spring(2.0, 1.0, 1.0) == 0.0


def test_presets_use_known_events_and_stretch():
    for name, p in animate.PRESETS.items():
        assert {e["type"] for e in p["events"]} <= set(animate.EVENT_TYPES), name
        ev = animate.preset_events(name, 8.0)
        assert all(e["start"] + e["dur"] <= 8.0 + 1e-6 for e in ev), name
    # blinks keep their speed when the clip is longer
    ev = animate.preset_events("idle", 8.0)
    assert ev[0]["dur"] == animate.PRESETS["idle"]["events"][0]["dur"]


def test_state_mixes_blink_and_squint():
    ev = [{"type": "squint", "start": 0, "dur": 4, "amount": 0.4}, {"type": "blink", "start": 2, "dur": 0.2}]
    assert abs(animate.state(ev, 1.0)["lid"] - 0.4) < 1e-6
    assert animate.state(ev, 2.1)["lid"] > 0.9


@pytest.fixture
def frame(tmp_path):
    """A grey 'head' disc with two dark eyes on a striped background, plus its mask."""
    h, w = 400, 240
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = (40, 120, 200)
    img[::8] = (30, 90, 160)
    m = np.zeros((h, w), np.uint8)
    cv2.circle(m, (120, 160), 90, 255, -1)
    cv2.rectangle(m, (70, 200), (170, 400), 255, -1)
    img[m > 0] = (150, 140, 130)
    for cx in (85, 155):
        cv2.circle(img, (cx, 150), 22, (90, 200, 170), -1)
        cv2.circle(img, (cx, 150), 13, (10, 10, 10), -1)
    p, mp = str(tmp_path / "f.png"), str(tmp_path / "f_mask.png")
    cv2.imwrite(p, img)
    cv2.imwrite(mp, m)
    anchors = {"eyes": [[85, 150, 22, 22], [155, 150, 22, 22]], "head_pivot": [120, 245], "neck": [215, 250],
               "chest": [120, 320]}
    return p, mp, anchors, img


def test_render_rest_is_close_to_the_frame(frame):
    p, mp, an, img = frame
    a = animate.Animator(p, an, mask_path=mp)
    out = a.render(0.0, [], breathe=0.0)
    assert out.shape == img.shape
    assert np.abs(out - img.astype(np.float32)).mean() < 2.0


def test_background_stays_put_when_the_head_turns(frame):
    p, mp, an, img = frame
    a = animate.Animator(p, an, mask_path=mp)
    out = a.render(1.0, [{"type": "tilt", "start": 0, "dur": 2, "deg": 6}], breathe=0.0)
    far = np.zeros(img.shape[:2], bool)
    far[:, :15] = far[:, -15:] = True                  # columns far from the character
    assert np.abs(out[far] - img[far].astype(np.float32)).mean() < 1.0
    head = (slice(70, 230), slice(40, 200))
    assert np.abs(out[head] - img[head].astype(np.float32)).mean() > 3.0


def test_blink_covers_the_eyes(frame):
    p, mp, an, img = frame
    a = animate.Animator(p, an, mask_path=mp)
    out = a.render(0.1, [{"type": "blink", "start": 0, "dur": 0.2}], breathe=0.0)
    eye = out[140:160, 75:95]
    assert eye.mean() > img[140:160, 75:95].mean() + 40     # dark pupil replaced by lid fur


def test_presets_command_lists_everything():
    import subprocess
    env = dict(os.environ, SERIES_LANG="en", SERIES_OFFLINE="1")
    r = subprocess.run([sys.executable, "-m", "series_factory", "--series", os.path.join(ROOT, "example_series"),
                        "animate", "presets", "--json"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert set(json.loads(r.stdout)) == set(animate.PRESETS)
