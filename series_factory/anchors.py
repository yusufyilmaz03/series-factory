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


def _refine(hsv, e, np, cv2):
    """Grow a detected iris to the whole eye. A large pupil can split the iris into a crescent, and an ellipse fitted
    to the crescent alone is too small: the lid then leaves a coloured rim. Iris and pupil pixels near the candidate
    are joined, holes filled, and the ellipse is fitted to their convex hull."""
    H, W = hsv.shape[:2]
    r = 1.9 * max(e["rx"], e["ry"])
    xa, ya = max(0, int(e["cx"] - r)), max(0, int(e["cy"] - r))
    xb, yb = min(W, int(e["cx"] + r) + 1), min(H, int(e["cy"] + r) + 1)
    sub = hsv[ya:yb, xa:xb]
    if sub.size == 0:
        return e
    hh, ss, vv = (sub[..., i].astype(int) for i in range(3))
    pale = (hh >= 17) & (hh <= 45) & (ss > 22) & (ss < 70) & (vv > 110) & (vv < 238)   # washed-out iris, not white fur
    eye = (_iris_mask(sub, np) | pale).astype(np.uint8)
    # the pupil: a dark blob enclosed by the iris (dark fur around the eye touches the border of the crop instead)
    dark = ((vv < 70) & (eye == 0)).astype(np.uint8)
    ko = max(3, int(min(e["rx"], e["ry"]) / 4) | 1)                   # break thin links to the dark rim and fur
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ko, ko)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(dark)
    sh, sw = dark.shape
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if x == 0 or y == 0 or x + w >= sw or y + h >= sh or area < 0.15 * math.pi * e["rx"] * e["ry"]:
            continue
        # a pupil is compact and lies over the first fit; dark fur around the eye is neither
        bx, by = e["cx"] - xa, e["cy"] - ya
        if (x < bx - 1.3 * e["rx"] or x + w > bx + 1.3 * e["rx"] or y < by - 1.3 * e["ry"] or y + h > by + 1.3 * e["ry"]):
            continue
        cs, _ = cv2.findContours((lab == i).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if area < 0.75 * cv2.contourArea(cv2.convexHull(max(cs, key=cv2.contourArea))):
            continue
        eye[lab == i] = 1
    eye *= 255
    k = max(3, int(max(e["rx"], e["ry"]) / 8) | 1)
    eye = cv2.morphologyEx(eye, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    n, lab = cv2.connectedComponents(eye)
    seed = np.zeros(eye.shape, np.uint8)
    cv2.ellipse(seed, (int(e["cx"] - xa), int(e["cy"] - ya)), (max(1, int(e["rx"])), max(1, int(e["ry"]))),
                0, 0, 360, 1, -1)
    hits = np.bincount(lab[(seed > 0) & (lab > 0)].ravel(), minlength=n)
    if n < 2 or hits.max() == 0:
        return e
    comp = (lab == int(hits.argmax())).astype(np.uint8)
    pts = cv2.findNonZero(comp)
    if pts is None or len(pts) < 8:
        return e
    hull = cv2.convexHull(pts)
    if len(hull) < 5:
        return e
    (ex, ey), (ea, eb), ang = cv2.fitEllipse(hull)
    if abs(((ang + 45) % 180) - 45) > 45:
        ea, eb = eb, ea
    rx, ry = ea / 2, eb / 2
    # accept only a moderate growth that still contains the first fit and stays eye-shaped; dark fur or a dark
    # background leaking in would make it much larger
    if not (0.95 <= rx / e["rx"] <= 1.7 and 0.95 <= ry / e["ry"] <= 1.7 and 0.55 < rx / max(ry, 1) < 1.9):
        return e
    if math.hypot(xa + ex - e["cx"], ya + ey - e["cy"]) > 0.6 * max(rx, ry):
        return e

    def bright_rim(cx, cy, ax, ay):                   # share of bright pixels just outside an ellipse
        ring = np.zeros(vv.shape, np.uint8)
        cv2.ellipse(ring, (int(cx), int(cy)), (max(1, int(ax * 1.12)), max(1, int(ay * 1.12))), 0, 0, 360, 1,
                    max(2, int(max(ax, ay) * 0.08)))
        v = vv[ring > 0]
        return (v > 170).mean() if v.size else 0.0
    # the outline of an eye is a dark rim; a fit that ran into white fur has a bright one
    if bright_rim(ex, ey, rx, ry) > bright_rim(e["cx"] - xa, e["cy"] - ya, e["rx"], e["ry"]) + 0.12:
        return e
    return {"cx": xa + ex, "cy": ya + ey, "rx": rx, "ry": ry, "a": math.pi * rx * ry}


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
    eyes = sorted((_refine(hsv, e, np, cv2) for e in best), key=lambda e: e["cx"])
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
