"""Automatic eye anchors on a synthetic cat face (no detector, no network)."""
import os, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
from series_factory import anchors  # noqa: E402


def face(open_eyes=True):
    img = np.full((600, 400, 3), (120, 110, 105), np.uint8)
    cv2.circle(img, (200, 260), 150, (110, 105, 100), -1)
    for cx in (140, 260):
        if open_eyes:
            cv2.ellipse(img, (cx, 230), (34, 30), 0, 0, 360, (60, 200, 170), -1)   # green-yellow iris (BGR)
            cv2.ellipse(img, (cx, 230), (12, 24), 0, 0, 360, (15, 15, 15), -1)     # pupil
        else:
            cv2.line(img, (cx - 30, 232), (cx + 30, 232), (40, 40, 40), 3)
    return img


def test_two_eyes_found_left_to_right_with_head_points_below():
    eyes = anchors.find_eyes(face(), (40, 100, 360, 520))
    assert eyes and len(eyes) == 2
    (ax, ay, arx, ary), (bx, by, brx, bry) = eyes
    assert abs(ax - 140) < 6 and abs(bx - 260) < 6 and abs(ay - 230) < 6
    assert 25 < arx < 45 and 22 < ary < 40
    hp = anchors.head_points(eyes, 400, 600)
    assert hp["neck"][0] > ay and hp["head_pivot"][1] > ay and hp["chest"][1] > hp["head_pivot"][1]


def test_closed_eyes_give_nothing():
    assert anchors.find_eyes(face(open_eyes=False), (40, 100, 360, 520)) is None


def test_big_pupil_and_pale_iris_still_give_the_whole_eye():
    """A large off-centre pupil splits the iris into a crescent whose outer part is washed out; the anchor must cover
    the whole eye, otherwise a closing lid leaves a coloured rim."""
    img = np.full((600, 400, 3), (120, 110, 105), np.uint8)
    cv2.circle(img, (200, 260), 150, (110, 105, 100), -1)
    for cx in (140, 260):
        cv2.ellipse(img, (cx, 230), (38, 34), 0, 0, 360, (40, 40, 40), -1)          # dark rim
        cv2.ellipse(img, (cx, 230), (35, 31), 0, 0, 360, (115, 140, 140), -1)       # pale iris (low saturation)
        cv2.ellipse(img, (cx + 10, 230), (26, 28), 0, 0, 360, (60, 200, 170), -1)   # saturated crescent
        cv2.circle(img, (cx + 14, 230), 24, (15, 15, 15), -1)                        # big pupil, touching the rim
    eyes = anchors.find_eyes(img, (40, 100, 360, 520))
    assert eyes and len(eyes) == 2
    for (x, y, rx, ry), cx in zip(eyes, (140, 260)):
        assert abs(x - cx) < 6 and rx > 31 and ry > 28
