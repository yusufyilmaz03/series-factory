"""Automatic anchors for `animate`: eye ellipses, head pivot, neck and chest of the main animal in a frame.

No language model and no generated pixels: the object detector of the `subtitles` extra finds the animal, the irises
are found by colour and shape in the upper part of its box, and the head points follow from the distance between the
eyes (ratios measured on hand-placed anchors). When two open eyes are not found (closed eyes, a far shot, a back
view) nothing is returned and the frame is simply not animated.
"""
import math


def _iris_mask(hsv, np):
    """Coloured, bright iris pixels (yellow-green to blue; most stylised cats), plus dark pupils."""
    h, s, v = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    iris = (s > 55) & (v > 85) & (((h >= 18) & (h <= 52)) | ((h >= 85) & (h <= 110)))
    return iris


def find_eyes(img_bgr, box):
    """Two eye ellipses [[cx, cy, rx, ry], [cx, cy, rx, ry]] (left to right) inside box (pixels x0, y0, x1, y1),
    or None."""
    import numpy as np, cv2
    H, W = img_bgr.shape[:2]
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    bh = y1 - y0
    roi = img_bgr[y0:y0 + int(bh * 0.7), x0:x1]
    if roi.size == 0:
        return None
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    m = _iris_mask(hsv, np).astype(np.uint8) * 255
    k = max(3, int(min(roi.shape[:2]) / 60) | 1)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    bw = x1 - x0
    val = hsv[..., 2]
    cands = []
    for c in cnts:
        if len(c) < 8:
            continue
        x, y, w, h = cv2.boundingRect(c)
        if max(w, h) < bw * 0.045 or max(w, h) > bw * 0.5:      # eye size relative to the animal
            continue
        # an iris ring is often open (the pupil touches its edge): fit an ellipse to its points
        (ex, ey), (ea, eb), ang = cv2.fitEllipse(c)
        if abs(((ang + 45) % 180) - 45) > 45:                     # axes swapped when the ellipse is upright
            ea, eb = eb, ea
        rx, ry = ea / 2, eb / 2
        if not (0.4 < rx / max(ry, 1) < 2.6) or rx > 1.6 * max(w, h) or ry > 1.6 * max(w, h):
            ex, ey, rx, ry = x + w / 2, y + h / 2, w / 2, h / 2
        if not (0.45 < rx / max(ry, 1) < 2.6):                    # thin slivers (bars, leaves) are not eyes
            continue
        # a real eye has a dark pupil inside
        em = np.zeros(val.shape, np.uint8)
        cv2.ellipse(em, (int(ex), int(ey)), (max(1, int(rx * 0.8)), max(1, int(ry * 0.8))), 0, 0, 360, 255, -1)
        inside = val[em > 0]
        if inside.size == 0 or (inside < 70).mean() < 0.06:
            continue
        cands.append({"cx": ex, "cy": ey, "rx": rx, "ry": ry, "a": math.pi * rx * ry})
    best, score = None, 0.0
    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            a, b = cands[i], cands[j]
            size = min(a["a"], b["a"]) / max(a["a"], b["a"])
            if size < 0.35:
                continue
            avg_h = (a["ry"] + b["ry"])
            if abs(a["cy"] - b["cy"]) > 0.8 * avg_h:
                continue
            dist = abs(a["cx"] - b["cx"])
            if dist < 1.3 * (a["rx"] + b["rx"]) or dist > 6 * (a["rx"] + b["rx"]):
                continue
            sc = (a["a"] + b["a"]) * size
            if sc > score:
                best, score = (a, b), sc
    if not best:
        return None
    eyes = sorted(best, key=lambda e: e["cx"])
    pad = 1.04                                        # include the dark rim around the iris
    return [[round(x0 + e["cx"], 1), round(y0 + e["cy"], 1), round(e["rx"] * pad, 1), round(e["ry"] * pad, 1)]
            for e in eyes]


def head_points(eyes, w, h):
    """Head pivot, neck rows and chest from the eye line (ratios of the distance between the eyes)."""
    (ax, ay, _, _), (bx, by, _, _) = eyes
    mx, my = (ax + bx) / 2, (ay + by) / 2
    d = math.hypot(bx - ax, by - ay)
    clamp = lambda v: max(0, min(h - 1, v))  # noqa: E731
    return {"head_pivot": [round(mx, 1), round(clamp(my + 1.3 * d), 1)],
            "neck": [round(clamp(my + 0.7 * d), 1), round(clamp(my + 1.35 * d), 1)],
            "chest": [round(mx, 1), round(clamp(my + 2.2 * d), 1)]}


def find(image_path, boxes=None):
    """Anchors for the frame's main animal, or None."""
    import cv2
    img = cv2.imread(image_path)
    if img is None:
        return None
    h, w = img.shape[:2]
    if boxes is None:
        try:
            from . import subplace
            boxes, _ = subplace.detect(image_path)
        except Exception:
            boxes = []
    # the main animal: the largest one (several cats in a frame: the one the shot is about is usually the biggest)
    animals = sorted((b for b in boxes if b[0] in ("cat", "dog")), key=lambda b: -(b[4] - b[2]) * (b[5] - b[3]))
    regions = [(b[2] * w, b[3] * h, b[4] * w, b[5] * h) for b in animals]   # no animal found: no anchors
    for r in regions:
        eyes = find_eyes(img, r)
        if eyes:
            return {"eyes": eyes, **head_points(eyes, w, h)}
    return None
