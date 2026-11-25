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
