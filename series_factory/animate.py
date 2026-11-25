"""Frame animation without generative AI: small 2.5D motions on a single still frame.

The character is cut out of the frame (mask), the background behind it is filled with classical
inpainting, and only the character layer is warped: breathing, blinks, squints, pupils, gaze,
head tilt / nod / shake, a jolt, a bounce and ear flicks. Nothing is generated; every pixel comes
from the frame itself.

What is specific to a frame lives in the plan, on the frame (`"animate"`):

    "animate": {
      "anchors": {
        "eyes": [[cx, cy, rx, ry], ...],        # eye ellipses in frame pixels
        "head_pivot": [x, y],                    # where the head turns (neck)
        "neck": [y0, y1],                        # head weight goes 1 -> 0 between these rows
        "chest": [x, y],                         # breathing centre
        "ears": [{"tip": [x, y], "base": [[x, y], [x, y]]}]   # optional
      },
      "preset": "suspicious",                    # or "events": [...] for a hand-made timeline
      "seed": 0
    }

Everything else (motion curves, presets) is generic. Rendering needs numpy + opencv;
the character mask needs rembg (`pip install "series-factory[animate]"`).
Masks and lid textures are cached next to the frames in `_animate/`.
"""
import json, math, os, subprocess, sys

from .i18n import T

# ---------------------------------------------------------------- presets
# An event: {"type": ..., "start": s, "dur": s, ...}. Times are seconds from the clip start.
# Presets are written for ~4 s and stretched to the clip length.
PRESET_LEN = 4.0
PRESETS = {
    "idle": {
        "label": ("Idle", "Sakin"),
        "events": [{"type": "blink", "start": 1.1, "dur": 0.22}, {"type": "blink", "start": 3.3, "dur": 0.2}],
    },
    "innocent": {
        "label": ("Innocent", "Masum"),
        "events": [{"type": "pupils", "start": 0.2, "dur": 3.6, "scale": 1.28},
                   {"type": "tilt", "start": 0.6, "dur": 2.8, "deg": 4.5, "hold": True},
                   {"type": "slow_blink", "start": 2.2, "dur": 0.9}],
    },
    "suspicious": {
        "label": ("Suspicious", "Şüpheli"),
        "events": [{"type": "squint", "start": 0.2, "dur": 3.6, "amount": 0.42},
                   {"type": "look", "start": 0.7, "dur": 1.3, "dx": 0.32, "dy": 0.0},
                   {"type": "look", "start": 2.1, "dur": 1.4, "dx": -0.32, "dy": 0.0},
                   {"type": "tilt", "start": 0.6, "dur": 3.0, "deg": -2.0, "hold": True}],
    },
    "eye_roll": {
        "label": ("Eye roll", "Göz devirme"),
        "events": [{"type": "squint", "start": 0.3, "dur": 3.4, "amount": 0.22, "flat": 0.5},
                   {"type": "look_path", "start": 0.5, "dur": 1.6,
                    "path": [[-0.3, -0.05], [-0.15, -0.38], [0.15, -0.38], [0.3, -0.05]]},
                   {"type": "tilt", "start": 0.4, "dur": 2.0, "deg": 3.0},
                   {"type": "blink", "start": 2.6, "dur": 0.24}],
    },
    "surprised": {
        "label": ("Surprised", "Şaşırmış"),
        "events": [{"type": "jolt", "start": 0.5, "dur": 1.0, "amount": 0.055},
                   {"type": "pupils", "start": 0.45, "dur": 3.2, "scale": 0.62, "in": 0.12},
                   {"type": "bounce", "start": 0.5, "dur": 0.9, "amount": 0.05},
                   {"type": "blink", "start": 2.4, "dur": 0.16}, {"type": "blink", "start": 2.65, "dur": 0.16}],
    },
    "sleepy": {
        "label": ("Sleepy", "Uykulu"),
        "events": [{"type": "squint", "start": 0.0, "dur": 4.0, "amount": 0.55, "flat": 0.2, "in": 0.9, "out": 0.3},
                   {"type": "slow_blink", "start": 1.0, "dur": 1.4},
                   {"type": "nod", "start": 1.3, "dur": 1.3, "amount": 0.035, "count": 1, "hold": True},
                   {"type": "jolt", "start": 2.65, "dur": 0.5, "amount": 0.02}],
    },
    "no": {
        "label": ("No", "Hayır"),
        "events": [{"type": "shake", "start": 0.5, "dur": 1.6, "deg": 4.0, "count": 3},
                   {"type": "squint", "start": 0.4, "dur": 2.6, "amount": 0.25}],
    },
    "yes": {
        "label": ("Yes", "Onay"),
        "events": [{"type": "nod", "start": 0.5, "dur": 1.4, "amount": 0.03, "count": 2},
                   {"type": "slow_blink", "start": 2.2, "dur": 0.8}],
    },
    "smug": {
        "label": ("Smug", "Kibirli"),
        "events": [{"type": "tilt", "start": 0.3, "dur": 3.4, "deg": -3.0, "hold": True},
                   {"type": "squint", "start": 0.5, "dur": 3.2, "amount": 0.34, "flat": 0.85},
                   {"type": "look", "start": 1.0, "dur": 2.4, "dx": 0.28, "dy": 0.05}],
    },
    "love": {
        "label": ("Cat kiss", "Kedi öpücüğü"),
        "events": [{"type": "slow_blink", "start": 0.5, "dur": 1.2},
                   {"type": "slow_blink", "start": 2.2, "dur": 1.2},
                   {"type": "tilt", "start": 0.3, "dur": 3.4, "deg": 3.5, "hold": True}],
    },
    "ears": {
        "label": ("Ear flick", "Kulak seğirmesi"),
        "needs": "ears",
        "events": [{"type": "ear_flick", "start": 0.6, "dur": 0.3, "ear": 0, "deg": -9},
                   {"type": "ear_flick", "start": 1.0, "dur": 0.28, "ear": 0, "deg": -7},
                   {"type": "ear_flick", "start": 2.2, "dur": 0.32, "ear": 1, "deg": 9},
                   {"type": "blink", "start": 3.0, "dur": 0.2}],
    },
}
EVENT_TYPES = ["blink", "slow_blink", "squint", "pupils", "look", "look_path", "tilt", "nod", "shake", "jolt",
               "bounce", "ear_flick"]


def preset_events(name, seconds):
    """Events of a preset stretched to `seconds`."""
    p = PRESETS[name]
    k = seconds / PRESET_LEN
    out = []
    for e in p["events"]:
        e = dict(e)
        e["start"] *= k
        if e["type"] in ("blink", "ear_flick"):     # fast motions keep their speed
            pass
        else:
            e["dur"] *= k
        out.append(e)
    return out


# ---------------------------------------------------------------- curves
def _ss(e0, e1, x):
    import numpy as np
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def _s(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def pulse(t, t0, dur):
    """0 -> 1 -> 0, smooth."""
    if t < t0 or t > t0 + dur:
        return 0.0
    return math.sin(math.pi * (t - t0) / dur) ** 2


def hold(t, t0, dur, tin=0.35, tout=0.35):
    """Ease in, hold at 1, ease out."""
    if t < t0 or t > t0 + dur:
        return 0.0
    tin, tout = min(tin, dur / 2), min(tout, dur / 2)
    return min(_s(0, tin, t - t0), 1 - _s(dur - tout, dur, t - t0))


def spring(t, t0, dur, freq=2.5):
    """Quick rise with a damped overshoot (for jolts and bounces); ends at 0."""
    if t < t0 or t > t0 + dur:
        return 0.0
    x = (t - t0) / dur
    return math.sin(math.pi * freq * x) * math.exp(-4.0 * x) * (1 - x)


def osc(t, t0, dur, count):
    """count back-and-forth cycles inside a smooth envelope."""
    if t < t0 or t > t0 + dur:
        return 0.0
    x = (t - t0) / dur
    return math.sin(2 * math.pi * count * x) * math.sin(math.pi * x)


def state(events, t, breathe=1.0, breath_period=2.8):
    """All motion amounts at time t."""
    st = {"lid": 0.0, "flat": 0.0, "lower": 0.0, "pupil": 1.0, "look": [0.0, 0.0], "rot": 0.0, "scale": 1.0,
          "shift": [0.0, 0.0], "bounce": 0.0, "breath": breathe * math.sin(2 * math.pi * t / breath_period), "ears": {}}
    blink = 0.0
    squint = 0.0
    for e in events:
        ty, a, d = e["type"], e["start"], e["dur"]
        if ty == "blink":
            blink = max(blink, pulse(t, a, d))
        elif ty == "slow_blink":
            blink = max(blink, hold(t, a, d, d * 0.4, d * 0.45))
        elif ty == "squint":
            v = hold(t, a, d, e.get("in", 0.45), e.get("out", 0.35)) * e.get("amount", 0.42)
            if v > squint:
                squint = v
                st["flat"] = e.get("flat", 0.75) * (v / max(e.get("amount", 0.42), 1e-6))
        elif ty == "pupils":
            h = hold(t, a, d, e.get("in", 0.4), e.get("out", 0.5))
            st["pupil"] *= 1 + (e.get("scale", 1.25) - 1) * h
        elif ty == "look":
            h = hold(t, a, d, e.get("in", 0.25), e.get("out", 0.3))
            st["look"][0] += e.get("dx", 0) * h
            st["look"][1] += e.get("dy", 0) * h
        elif ty == "look_path":
            if a <= t <= a + d:
                pts = e["path"]
                x = (t - a) / d
                env = min(_s(0, 0.12, x), 1 - _s(0.88, 1.0, x))
                f = _s(0, 1, x) * (len(pts) - 1)
                i = min(int(f), len(pts) - 2)
                r = f - i
                st["look"][0] += (pts[i][0] * (1 - r) + pts[i + 1][0] * r) * env
                st["look"][1] += (pts[i][1] * (1 - r) + pts[i + 1][1] * r) * env
        elif ty == "tilt":
            h = hold(t, a, d, d * 0.3, d * 0.3) if e.get("hold") else pulse(t, a, d)
            st["rot"] += math.radians(e.get("deg", 3)) * h
        elif ty == "nod":
            if e.get("hold"):
                h = hold(t, a, d, d * 0.45, d * 0.2)
            else:
                h = max(0.0, osc(t, a, d, e.get("count", 2)))
            st["shift"][1] += e.get("amount", 0.03) * h          # fraction of head height, down
            st["rot"] += math.radians(-1.0) * h
        elif ty == "shake":
            st["rot"] += math.radians(e.get("deg", 4)) * osc(t, a, d, e.get("count", 3))
            st["shift"][0] += 0.01 * osc(t, a, d, e.get("count", 3))
        elif ty == "jolt":
            v = spring(t, a, d)
            st["scale"] *= 1 + e.get("amount", 0.05) * v
            st["shift"][1] -= e.get("amount", 0.05) * 0.5 * v
        elif ty == "bounce":
            st["bounce"] += e.get("amount", 0.05) * spring(t, a, d, freq=3.0)
        elif ty == "ear_flick":
            i = e.get("ear", 0)
            st["ears"][i] = st["ears"].get(i, 0.0) + math.radians(e.get("deg", 9)) * pulse(t, a, d)
    st["lid"] = max(blink, squint)
    st["blink_wins"] = blink >= squint
    if st["blink_wins"]:
        st["flat"] *= (1 - blink)
    st["lower"] = (0.4 * squint) * (1 - blink if st["blink_wins"] else 1)
    return st


# ---------------------------------------------------------------- the frame
class Animator:
    """One frame + its anchors. `render(t, events)` returns a BGR float image of the same size."""

    def __init__(self, image_path, anchors, cache_dir=None, mask_path=None):
        import numpy as np, cv2
        self.np, self.cv2 = np, cv2
        self.path = image_path
        self.img = cv2.imread(image_path).astype(np.float32)
        if self.img is None:
            raise FileNotFoundError(image_path)
        self.h, self.w = self.img.shape[:2]
        self.a = anchors
        self.cache = cache_dir
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
        self.Y, self.X = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        self.alpha = self._solid(self._mask(mask_path))
        self.plate = self._plate()
        self.pupils = [self._pupil(e) for e in anchors["eyes"]]
        self._lids = None
        self._head_h = max(1.0, (anchors.get("neck") or [self.h * 0.5, self.h * 0.6])[1] -
                           min([e[1] - e[3] for e in anchors["eyes"]] or [0]))

    # -- preparation (cached) ------------------------------------------------
    def _cached(self, name):
        return os.path.join(self.cache, name) if self.cache else None

    def _mask(self, mask_path):
        np, cv2 = self.np, self.cv2
        stem = os.path.splitext(os.path.basename(self.path))[0]
        p = mask_path or self._cached(stem + "_mask.png")
        if p and os.path.exists(p):
            return cv2.imread(p, 0).astype(np.float32) / 255
        try:
            from rembg import remove, new_session
        except ImportError:
            sys.exit(T('The character mask needs rembg: pip install "series-factory[animate]"',
                       'Karakter maskesi için rembg gerekli: pip install "series-factory[animate]"'))
        from PIL import Image
        m = np.array(remove(Image.open(self.path).convert("RGB"), session=new_session("isnet-general-use"),
                            only_mask=True))
        if p:
            cv2.imwrite(p, m)
        return m.astype(np.float32) / 255

    def _solid(self, alpha):
        """The mask must be solid inside the character: segmentation often leaves glossy eyes or bright fur
        half transparent, and the original frame would then show through a closed lid. Holes are filled and
        the eyes (with their lid margin) are made fully opaque."""
        np, cv2 = self.np, self.cv2
        b = (alpha > 0.5).astype(np.uint8) * 255
        cnts, _ = cv2.findContours(b, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        filled = np.zeros_like(b)
        cv2.drawContours(filled, cnts, -1, 255, -1)
        inner = cv2.erode(filled, np.ones((5, 5), np.uint8)).astype(np.float32) / 255
        for cx, cy, rx, ry in self.a["eyes"]:
            pad = max(3, int(round(0.25 * ry))) + 3
            cv2.ellipse(inner, (int(cx), int(cy)), (int(rx + pad), int(ry + pad)), 0, 0, 360, 1.0, -1)
        return np.maximum(alpha, inner)

    def _plate(self):
        """Background without the character: dilated mask, Telea inpaint at 1/4 size, blurred."""
        np, cv2 = self.np, self.cv2
        m = (self.alpha > 0.05).astype(np.uint8) * 255
        m = cv2.dilate(m, np.ones((11, 11), np.uint8))
        k = 2                                       # half size: sharp enough to read as the same wall/floor
        small = cv2.resize(self.img.astype(np.uint8), (self.w // k, self.h // k), interpolation=cv2.INTER_AREA)
        ms = cv2.resize(m, (self.w // k, self.h // k), interpolation=cv2.INTER_NEAREST)
        fill = cv2.inpaint(small, ms, 9, cv2.INPAINT_TELEA)
        fill = cv2.GaussianBlur(cv2.resize(fill, (self.w, self.h), interpolation=cv2.INTER_CUBIC), (0, 0), 1.5)
        mf = cv2.GaussianBlur(m.astype(np.float32) / 255, (0, 0), 4)[..., None]
        return self.img * (1 - mf) + fill.astype(np.float32) * mf

    def _pupil(self, eye):
        """Pupil radius as a fraction of the eye radius (darkest blob inside the eye)."""
        np, cv2 = self.np, self.cv2
        cx, cy, rx, ry = eye
        m = np.zeros((self.h, self.w), np.uint8)
        cv2.ellipse(m, (int(cx), int(cy)), (int(rx * 0.9), int(ry * 0.9)), 0, 0, 360, 255, -1)
        v = cv2.cvtColor(self.img.astype(np.uint8), cv2.COLOR_BGR2HSV)[..., 2]
        thr = np.percentile(v[m > 0], 35)
        d = ((v <= thr) & (m > 0)).astype(np.uint8)
        n, lab, stt, _ = cv2.connectedComponentsWithStats(d)
        if n < 2:
            return (0.5, cx, cy)
        i = 1 + int(np.argmax(stt[1:, 4]))
        pts = np.column_stack(np.where(lab == i))[:, ::-1].astype(np.float32)
        (px, py), r = cv2.minEnclosingCircle(pts)
        return (float(min(0.85, max(0.2, r / ((rx + ry) / 2)))), float(px), float(py))

    def _prepare_lids(self):
        """Per eye, once: a fur 'lid' covering the whole eye. Base colour = Telea inpaint of the eye and its
        dark rim from the surrounding fur; texture = high-pass detail of the fur strip above the eye."""
        np, cv2 = self.np, self.cv2
        img8 = np.clip(self.img, 0, 255).astype(np.uint8)
        self._lids = []
        for cx, cy, rx, ry in self.a["eyes"]:
            cx, cy, rx, ry = int(cx), int(cy), int(rx), int(ry)
            # everything scales with the eye: small eyes in medium shots need a tight margin
            P = max(5, int(round(0.4 * ry)))
            # source without whiskers: thin bright lines removed (morphological opening), so the mirrored fur
            # does not carry whisker streaks onto the lid
            ks = 3 if ry < 40 else 5                          # just enough to drop whisker lines
            clean = cv2.morphologyEx(img8, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ks, ks)))
            clean = clean.astype(np.float32)
            # column by column: the upper lid mirrors the fur just above the eye, the lower lid the fur just below
            # (continuous at the eye's edge, colour follows the fur of that column: no pale disc from nearby white fur)
            uu = np.clip((self.X - cx) / (rx + P), -1, 1)
            half = (ry + P) * np.sqrt(1 - uu * uu)
            yt, yb = cy - half, cy + half
            up_y = np.clip(yt - (self.Y - yt) * 0.5, 0, self.h - 1).astype(np.float32)
            # the lower lid uses the fur above the eye too, mirrored further up: a shut eye reads as one patch of
            # head fur, and the white muzzle below does not bleach it
            lo_y = np.clip(yt - (yb - self.Y) * 0.5 - 0.15 * (yb - yt), 0, self.h - 1).astype(np.float32)
            up = cv2.remap(clean, self.X, up_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            lo = cv2.remap(clean, self.X, lo_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            # ...but towards the bottom edge it turns into the fur just below the eye, so the lid meets the face
            # without a ring
            below_y = np.clip(yb + (yb - self.Y) * 0.5, 0, self.h - 1).astype(np.float32)
            below = cv2.remap(clean, self.X, below_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            wb = _ss(0.45, 0.95, (self.Y - cy) / (ry + P))[..., None]
            lo = lo * (1 - wb) + below * wb
            sm = max(1.0, ry / 25)
            base = cv2.GaussianBlur(up, (0, 0), 1.5 * sm)
            base_lo = cv2.GaussianBlur(lo, (0, 0), 1.5 * sm)
            detail = up - cv2.GaussianBlur(up, (0, 0), 2 * sm)
            detail_lo = lo - cv2.GaussianBlur(lo, (0, 0), 2 * sm)
            self._lids.append((base + 0.7 * detail, (base_lo + 0.6 * detail_lo) * 0.96))

    # -- eye-level -------------------------------------------------------------
    def _eyes_warp(self, img, pupil, look):
        """Pupil scaling and gaze shift inside each eye ellipse (iris content moves, the eye shape stays)."""
        np, cv2 = self.np, self.cv2
        if abs(pupil - 1) < 1e-3 and abs(look[0]) < 1e-3 and abs(look[1]) < 1e-3:
            return img
        sx, sy = self.X.copy(), self.Y.copy()
        for (cx, cy, rx, ry), (p, pcx, pcy) in zip(self.a["eyes"], self.pupils):
            x0, x1 = int(max(0, cx - rx - 2)), int(min(self.w, cx + rx + 3))
            y0, y1 = int(max(0, cy - ry - 2)), int(min(self.h, cy + ry + 3))
            X, Y = self.X[y0:y1, x0:x1], self.Y[y0:y1, x0:x1]
            # gaze: output point shows the source point moved back by d*(1-rho^2)
            gx, gy = look[0] * rx, look[1] * ry
            u, v = (X - cx) / rx, (Y - cy) / ry
            rho2 = u * u + v * v
            w = np.clip(1 - rho2, 0, 1)
            qx, qy = X - gx * w, Y - gy * w
            # pupil: radial remap around the (shifted) centre, normalised to the eye ellipse
            if abs(pupil - 1) > 1e-3:
                ccx, ccy = pcx + gx, pcy + gy                 # around the pupil's own centre
                dx_, dy_ = qx - ccx, qy - ccy
                dist = np.sqrt(dx_ * dx_ + dy_ * dy_) + 1e-6
                ux, uy = dx_ / dist, dy_ / dist
                # distance R from the pupil centre to the eye ellipse along (ux, uy)
                ox, oy = (ccx - cx) / rx, (ccy - cy) / ry
                A_ = (ux / rx) ** 2 + (uy / ry) ** 2
                B_ = 2 * (ox * ux / rx + oy * uy / ry)
                C_ = ox * ox + oy * oy - 1
                R = (-B_ + np.sqrt(np.maximum(B_ * B_ - 4 * A_ * C_, 0))) / (2 * A_)
                r = dist / np.maximum(R, 1e-3)
                pf = min(0.95, p * pupil)
                rs = np.where(r < pf, r * p / pf, p + (r - pf) * (1 - p) / max(1e-3, 1 - pf))
                rs = np.where(r < 1, rs, r)
                qx = ccx + ux * rs * R
                qy = ccy + uy * rs * R
            inside = (rho2 <= 1.0)
            sx[y0:y1, x0:x1] = np.where(inside, qx, X)
            sy[y0:y1, x0:x1] = np.where(inside, qy, Y)
        return cv2.remap(img, sx, sy, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    def _lids_draw(self, img, upper, lower=0.0, flat=0.0):
        """upper: 0..1 lid closure, edge follows the eye's own arc; flat>0 straightens it (squint);
        lower: lower lid rising."""
        np = self.np
        if upper < 0.01 and lower < 0.01:
            return img
        if self._lids is None:
            self._prepare_lids()
        out = img.copy()
        for (cx, cy, rx, ry), (up_img, lo_img) in zip(self.a["eyes"], self._lids):
            pad = max(3, int(round(0.25 * ry)))
            x0, x1 = int(max(0, cx - rx - pad - 2)), int(min(self.w, cx + rx + pad + 3))
            y0, y1 = int(max(0, cy - ry - pad - 2)), int(min(self.h, cy + ry + pad + 3))
            X, Y = self.X[y0:y1, x0:x1], self.Y[y0:y1, x0:x1]
            o = out[y0:y1, x0:x1]
            u = np.clip((X - cx) / (rx + pad), -1, 1)
            half = (ry + pad) * np.sqrt(1 - u * u)
            top, bot = cy - half, cy + half
            inside = ((X - cx) / (rx + pad)) ** 2 + ((Y - cy) / (ry + pad)) ** 2
            ell = 1 - _ss(0.93, 1.05, inside)
            lw = max(1.5, ry / 40)                      # line width scales with the eye
            # where the lids meet when the eye is shut: a soft curve in the lower middle of the eye
            meet = cy + 0.18 * ry + 0.22 * ry * np.sqrt(np.clip(1 - u * u, 0, 1))
            close = _s(0.55, 1.0, upper) * (1 - flat)        # lower lid rises to meet a closing upper lid
            if upper > 0.01:
                # shutting follows the meeting curve; a squint (flat) keeps the deeper, older arc
                arc = top + upper * ((meet * (1 - flat) + bot * flat) - top)
                straight = np.minimum((cy - ry - pad) + upper * 2 * (ry + pad), meet)
                edge = arc * (1 - flat) + np.maximum(straight, top) * flat
                lid_h = np.maximum(edge - top, 1)
                pos = np.clip((Y - top) / lid_h, 0, 1)
                vol = 1.0 + 0.05 * np.exp(-((pos - 0.35) ** 2) / 0.05) * (1 - np.abs(u) ** 2) - 0.06 * pos ** 3
                rnd = (vol * (1 - 0.18 * np.exp(-((Y - edge) ** 2) / (60 * (ry / 77) ** 2))))[..., None]
                lid = ell * (1 - _ss(edge - lw * 0.8, edge + lw * 0.8, Y))
                shade = ell * _ss(edge - 1, edge + 1, Y) * np.exp(-np.maximum(Y - edge, 0) / (8 * ry / 77)) * 0.5
                o *= (1 - shade)[..., None]
                o[:] = o * (1 - lid[..., None]) + up_img[y0:y1, x0:x1] * rnd * lid[..., None]
                span = np.clip(1 - np.abs(u) ** 6, 0, 1) * (np.abs(X - cx) <= rx + pad)
                line = span * np.exp(-((Y - edge) ** 2) / (2 * lw * lw)) * min(1.0, upper * 5)
                line *= (0.85 + 0.15 * (1 - np.abs(u)))
                o[:] = o * (1 - 0.85 * line[..., None]) + 15 * 0.85 * line[..., None]
            if lower > 0.01 or close > 0.01:
                edge_lo = bot - np.maximum(lower * (bot - top), close * (bot - meet))
                lid = ell * _ss(edge_lo - lw * 0.8, edge_lo + lw * 0.8, Y)
                o[:] = o * (1 - lid[..., None]) + lo_img[y0:y1, x0:x1] * 0.97 * lid[..., None]
                line = ell * np.exp(-((Y - edge_lo) ** 2) / (2 * lw * lw)) * min(1.0, max(lower, close) * 6) * 0.4
                o[:] = o * (1 - line[..., None]) + 30 * line[..., None]
        return out

    # -- body-level ------------------------------------------------------------
    def _source_map(self, st):
        """Inverse map (output pixel -> source pixel) for bounce, breathing, head and ears."""
        np = self.np
        a = self.a
        X, Y = self.X, self.Y
        n0, n1 = a.get("neck") or [self.h * 0.55, self.h * 0.7]
        px, py = a.get("head_pivot") or [self.w / 2, n1]
        gx, gy = a.get("chest") or [px, (n1 + self.h) / 2]
        # bounce: squash/stretch around the bottom centre of the character
        b = st["bounce"]
        if abs(b) > 1e-4:
            X = gx + (X - gx) * (1 + b * 0.5)
            Y = self.h + (Y - self.h) / (1 + b)
        # weights stay near this character: other subjects in the mask (another character) do not move
        ex = sum(e[0] for e in a["eyes"]) / len(a["eyes"])
        ey = sum(e[1] for e in a["eyes"]) / len(a["eyes"])
        R = 1.6 * math.hypot(px - ex, py - ey)
        near_head = 1 - _ss(R, R * 1.3, np.sqrt((X - ex) ** 2 + (Y - ey) ** 2))
        near_body = 1 - _ss(R, R * 1.3, np.abs(X - gx) * 1.6)
        w_head = (1 - _ss(n0, n1, Y)) * near_head
        w_body = _ss(n0, n1, Y) * near_body
        # breathing: chest widens, head rides along a little
        br = st["breath"]
        sx = X - (X - gx) * 0.010 * br * w_body
        sy = Y - (Y - self.h) * 0.004 * br * w_body + 2.0 * (self.h / 1376) * br * w_head
        # head: rotation, scale and shift around the pivot
        th, k = st["rot"], st["scale"]
        tx, ty = st["shift"][0] * self._head_h * 2, st["shift"][1] * self._head_h * 2
        dx, dy = (X - px - tx) / k, (Y - py - ty) / k
        c, s = math.cos(-th), math.sin(-th)
        hx, hy = px + c * dx - s * dy, py + s * dx + c * dy
        sx = sx + (hx - X) * w_head
        sy = sy + (hy - Y) * w_head
        # ears: extra rotation around the ear base, in the head's frame
        for i, ang in st["ears"].items():
            ears = a.get("ears") or []
            if i >= len(ears) or abs(ang) < 1e-4:
                continue
            w = self._ear_weight(i)
            bx = (ears[i]["base"][0][0] + ears[i]["base"][1][0]) / 2
            by = (ears[i]["base"][0][1] + ears[i]["base"][1][1]) / 2
            ex, ey = sx - bx, sy - by
            c, s = math.cos(-ang * 1.0), math.sin(-ang * 1.0)
            sx = sx + (bx + c * ex - s * ey - sx) * w
            sy = sy + (by + s * ex + c * ey - sy) * w
        return sx.astype(np.float32), sy.astype(np.float32)

    def _ear_weight(self, i):
        np, cv2 = self.np, self.cv2
        if not hasattr(self, "_earw"):
            self._earw = {}
        if i in self._earw:
            return self._earw[i]
        e = self.a["ears"][i]
        tip = np.array(e["tip"], np.float32)
        b0, b1 = np.array(e["base"][0], np.float32), np.array(e["base"][1], np.float32)
        tri = np.zeros((self.h, self.w), np.float32)
        poly = np.array([tip + (tip - (b0 + b1) / 2) * 0.15, b0, b1], np.int32)
        cv2.fillPoly(tri, [poly], 1.0)
        tri = cv2.dilate(tri, np.ones((15, 15), np.uint8))
        # 0 at the base line, 1 from 35% of the way to the tip
        n = np.array([-(b1 - b0)[1], (b1 - b0)[0]], np.float32)
        n /= np.linalg.norm(n) + 1e-6
        if np.dot(tip - b0, n) < 0:
            n = -n
        height = float(np.dot(tip - b0, n))
        dist = ((self.X - b0[0]) * n[0] + (self.Y - b0[1]) * n[1]) / max(height, 1)
        w = tri * _ss(-0.05, 0.35, dist)
        w = cv2.GaussianBlur(w, (0, 0), 6) * self.alpha
        self._earw[i] = w
        return w

    # -- one frame -------------------------------------------------------------
    def render(self, t, events, breathe=1.0):
        np, cv2 = self.np, self.cv2
        st = state(events, t, breathe)
        img = self._eyes_warp(self.img, st["pupil"], st["look"])
        img = self._lids_draw(img, min(1.0, st["lid"] * 1.04), st["lower"], st["flat"])
        sx, sy = self._source_map(st)
        rgba = np.dstack([img, self.alpha * 255])
        cat = cv2.remap(rgba, sx, sy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        a = np.clip(cat[..., 3:4] / 255, 0, 1)
        # the filled background shows only where the character actually moved away; everywhere else the
        # original frame stays (no blurry halo around a still character)
        # where the character moved, its whole old footprint (soft dark fur fringe included) is replaced by the
        # filled background; where nothing moved, the frame stays untouched (no halo on still edges)
        if not hasattr(self, "_k_rev"):
            self._k_rev = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
            self._alpha_d = cv2.dilate(self.alpha, self._k_rev)
        mag = np.sqrt((sx - self.X) ** 2 + (sy - self.Y) ** 2)
        moving = _ss(0.25, 0.9, cv2.dilate(mag, self._k_rev))
        reveal = np.clip(self._alpha_d * moving - a[..., 0], 0, 1)
        reveal = np.clip(cv2.GaussianBlur(reveal, (0, 0), 1.0) * 1.5, 0, 1)[..., None]
        base = self.img * (1 - reveal) + self.plate * reveal
        return np.clip(base * (1 - a) + cat[..., :3] * a, 0, 255)


# ---------------------------------------------------------------- clip writer
def write_clip(anim, events, seconds, out, fps=30, size=(1080, 1920), zoom=0.0, label=None, font=None):
    """Render a clip: the frame scaled to `size`, an optional slow push-in (`zoom`, e.g. 0.05) and a label."""
    import numpy as np, cv2
    W, H = size
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                             "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                             "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    lab = _label_image(label, W, font) if label else None
    n = int(round(fps * seconds))
    for i in range(n):
        t = i / fps
        f = anim.render(t, events)
        p = _s(0, seconds, t)
        z = max(W / anim.w, H / anim.h) * (1 + zoom * p)
        M = np.float32([[z, 0, W / 2 - z * anim.w / 2], [0, z, H / 2 - z * anim.h / 2]])
        f = cv2.warpAffine(f, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
        if lab is not None:
            img, al = lab
            y0 = 80
            roi = f[y0:y0 + img.shape[0]]
            roi[:] = roi * (1 - al) + img * al
        proc.stdin.write(np.clip(f, 0, 255).astype(np.uint8).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    return out


def _label_image(text, W, font=None):
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    f = None
    for cand in [font, "DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf"]:
        if not cand:
            continue
        try:
            f = ImageFont.truetype(cand, 58)
            break
        except OSError:
            pass
    f = f or ImageFont.load_default(size=58)
    im = Image.new("RGBA", (W, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    tw = d.textlength(text, font=f)
    d.rounded_rectangle([(W - tw) / 2 - 30, 10, (W + tw) / 2 + 30, 110], 26, fill=(0, 0, 0, 150))
    d.text(((W - tw) / 2, 26), text, font=f, fill=(255, 255, 255, 255))
    a = np.asarray(im).astype(np.float32)
    return a[..., 2::-1], a[..., 3:4] / 255


# ---------------------------------------------------------------- plan helpers
def _find_frame(d, file):
    for s in d["scenes"]:
        for fr in s["frames"]:
            if fr["file"] == file:
                return fr
    sys.exit(T(f"Frame not in the plan: {file}", f"Kare planda yok: {file}"))


def _parse_pts(text, n):
    vals = [float(v) for v in text.replace(";", ",").split(",") if v.strip()]
    if len(vals) % n:
        sys.exit(T(f"expected groups of {n} numbers: {text}", f"{n}'li sayı grupları bekleniyordu: {text}"))
    return [vals[i:i + n] for i in range(0, len(vals), n)]


def _setup(a):
    from . import core
    ep = core.episode_dir(a.episode)
    d = core.load_plan(ep)
    fr = _find_frame(d, a.frame)
    path = core.ep_path(ep, "frames", a.frame)
    if not os.path.exists(path):
        sys.exit(T(f"Frame file missing: {path}", f"Kare dosyası yok: {path}"))
    cache = core.ep_path(ep, "frames", "_animate")
    return core, ep, d, fr, path, cache


def _anchors(fr):
    an = (fr.get("animate") or {}).get("anchors")
    if not an or not an.get("eyes"):
        sys.exit(T("This frame has no animation anchors yet: run 'series animate grid' and 'series animate set'.",
                   "Bu karede canlandırma noktaları yok: önce 'series animate grid', sonra 'series animate set'."))
    return an


# ---------------------------------------------------------------- commands
def cmd_presets(a):
    if a.json:
        print(json.dumps({k: {"label": v["label"], "events": v["events"]} for k, v in PRESETS.items()},
                         ensure_ascii=False, indent=2))
        return 0
    from .i18n import lang
    for k, v in PRESETS.items():
        types = sorted({e["type"] for e in v["events"]})
        need = T(" (needs ears)", " (kulak noktası gerekir)") if v.get("needs") == "ears" else ""
        print(f"{k:<11} {v['label'][1 if lang() == 'tr' else 0]:<16} {', '.join(types)}{need}")
    print(T("event types: ", "olay türleri: ") + ", ".join(EVENT_TYPES))
    return 0


def cmd_grid(a):
    """A copy of the frame with a pixel grid, to read anchor coordinates from."""
    import cv2
    core, ep, d, fr, path, cache = _setup(a)
    img = cv2.imread(path)
    h, w = img.shape[:2]
    step = a.step
    for x in range(0, w, step):
        cv2.line(img, (x, 0), (x, h), (0, 0, 255) if x % (step * 5) == 0 else (0, 220, 255), 1)
        if x % (step * 5) == 0:
            cv2.putText(img, str(x), (x + 2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
    for y in range(0, h, step):
        cv2.line(img, (0, y), (w, y), (0, 0, 255) if y % (step * 5) == 0 else (0, 220, 255), 1)
        if y % (step * 5) == 0:
            cv2.putText(img, str(y), (2, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
    an = (fr.get("animate") or {}).get("anchors") or {}
    for cx, cy, rx, ry in an.get("eyes", []):
        cv2.ellipse(img, (int(cx), int(cy)), (int(rx), int(ry)), 0, 0, 360, (0, 255, 0), 2)
    if an.get("head_pivot"):
        cv2.circle(img, tuple(int(v) for v in an["head_pivot"]), 7, (255, 0, 255), -1)
    for y in an.get("neck", []):
        cv2.line(img, (0, int(y)), (w, int(y)), (255, 0, 255), 2)
    for e in an.get("ears", []):
        pts = [e["tip"], e["base"][0], e["base"][1]]
        cv2.polylines(img, [__import__("numpy").array(pts, "int32")], True, (255, 255, 0), 2)
    os.makedirs(cache, exist_ok=True)
    out = a.out or os.path.join(cache, os.path.splitext(a.frame)[0] + "_grid.jpg")
    cv2.imwrite(out, img)
    print(out)
    return 0


def cmd_set(a):
    core, ep, d, fr, path, cache = _setup(a)
    anim = fr.setdefault("animate", {})
    an = anim.setdefault("anchors", {})
    if a.eyes:
        an["eyes"] = _parse_pts(a.eyes, 4)
    if a.head_pivot:
        an["head_pivot"] = _parse_pts(a.head_pivot, 2)[0]
    if a.neck:
        an["neck"] = _parse_pts(a.neck, 2)[0]
    if a.chest:
        an["chest"] = _parse_pts(a.chest, 2)[0]
    if a.ears:
        an["ears"] = [{"tip": p[0:2], "base": [p[2:4], p[4:6]]} for p in _parse_pts(a.ears, 6)]
    if a.preset:
        if a.preset not in PRESETS:
            sys.exit(T(f"unknown preset: {a.preset}", f"bilinmeyen paket: {a.preset}"))
        anim["preset"] = a.preset
    if a.dry_run:
        print(json.dumps(anim, ensure_ascii=False))
        return 0
    core.save_plan(ep, d)
    print(T(f"{a.frame}: animation saved", f"{a.frame}: canlandırma kaydedildi") + f"  {json.dumps(anim, ensure_ascii=False)}")
    return 0


def _events_for(fr, preset, seconds):
    anim = fr.get("animate") or {}
    if preset:
        return preset_events(preset, seconds)
    if anim.get("events"):
        return anim["events"]
    return preset_events(anim.get("preset", "idle"), seconds)


def cmd_preview(a):
    core, ep, d, fr, path, cache = _setup(a)
    an = _anchors(fr)
    if a.preset and a.preset not in PRESETS:
        sys.exit(T(f"unknown preset: {a.preset}", f"bilinmeyen paket: {a.preset}"))
    anim = Animator(path, an, cache)
    ev = _events_for(fr, a.preset, a.seconds)
    name = a.preset or (fr.get("animate") or {}).get("preset", "custom")
    out = a.out or os.path.join(cache, f"{os.path.splitext(a.frame)[0]}_{name}.mp4")
    write_clip(anim, ev, a.seconds, out, zoom=a.zoom)
    print(out)
    return 0


def cmd_demo(a):
    """Every preset on one frame, one after another, with labels (for choosing)."""
    from .i18n import lang
    core, ep, d, fr, path, cache = _setup(a)
    an = _anchors(fr)
    anim = Animator(path, an, cache)
    names = a.only.split(",") if a.only else [k for k, v in PRESETS.items() if not v.get("needs") or an.get(v["needs"])]
    parts = []
    for k in names:
        p = os.path.join(cache, f"_demo_{k}.mp4")
        label = PRESETS[k]["label"][1 if lang() == "tr" else 0]
        write_clip(anim, preset_events(k, a.seconds), a.seconds, p, label=label)
        parts.append(p)
        print(f"  {k}")
    out = a.out or os.path.join(cache, f"{os.path.splitext(a.frame)[0]}_demo.mp4")
    lst = os.path.join(cache, "_demo_list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.abspath(p)}'\n" for p in parts)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], check=True)
    for p in parts + [lst]:
        os.remove(p)
    print(out)
    return 0


def auto_anchors(ep, d, frames=None, write=False, quiet=False):
    """Find anchors for frames that ask for an effect ("animate" with a preset or events) and have no hand-placed
    anchors. Hand-placed anchors (no "anchors_auto") are never touched. Returns the number written/found."""
    from . import core, anchors as anc
    n = 0
    for s_ in d["scenes"]:
        for fr in s_["frames"]:
            an = fr.get("animate")
            if not an or (frames and fr["file"] not in frames):
                continue
            if an.get("anchors") and not an.get("anchors_auto"):
                continue
            path = core.ep_path(ep, "frames", fr["file"])
            if not os.path.exists(path):
                continue
            found = anc.find(path)
            if not quiet:
                print(f"{fr['file']:<24} " + (json.dumps(found["eyes"]) if found else T("no eyes found", "göz bulunamadı")))
            if found and write:
                an["anchors"] = found
                an["anchors_auto"] = True
                n += 1
            elif found:
                n += 1
    return n


def cmd_anchors(a):
    from . import core
    ep = core.episode_dir(a.episode)
    d = core.load_plan(ep)
    n = auto_anchors(ep, d, a.frames or None, write=a.write)
    if a.write and n:
        core.save_plan(ep, d)
        print(T(f"anchors written for {n} frames", f"{n} karenin noktaları yazıldı"))
    return 0


def single_frame(ep, file):
    """Called when a frame is saved: if the plan asks for an effect on it, write its anchors."""
    from . import core
    d = core.load_plan(ep)
    if auto_anchors(ep, d, [file], write=True, quiet=True):
        core.save_plan(ep, d)
        return True
    return False


def cmd(a):
    if a.action == "anchors":
        return cmd_anchors(a)
    return {"presets": cmd_presets, "grid": cmd_grid, "set": cmd_set, "preview": cmd_preview, "demo": cmd_demo}[a.action](a)


def add_parser(sp):
    p = sp.add_parser("animate", help=T("small motions on a still frame, no generative AI (optional extra)",
                                        "durağan karede küçük hareketler, üretken AI yok (opsiyonel)"))
    s = p.add_subparsers(dest="action", required=True, metavar="<action>")
    q = s.add_parser("anchors", help=T("find eye/head anchors for frames that ask for an effect (needs [subtitles])",
                                       "efekt istenen karelerde göz/kafa noktalarını bul ([subtitles] gerekir)"))
    q.add_argument("episode")
    q.add_argument("frames", nargs="*")
    q.add_argument("--write", action="store_true", help=T("write them to the plan", "plana yaz"))
    q = s.add_parser("presets", help=T("list motion presets", "hareket paketlerini listele"))
    q.add_argument("--json", action="store_true")
    for name, hlp in (("grid", T("frame with a pixel grid, to read anchors from", "nokta okumak için ızgaralı kare")),
                      ("set", T("write anchors / preset into the plan", "noktaları / paketi plana yaz")),
                      ("preview", T("render one clip of a frame", "bir karenin klibini üret")),
                      ("demo", T("all presets on one frame, labelled", "bir karede bütün paketler, etiketli"))):
        q = s.add_parser(name, help=hlp)
        q.add_argument("episode")
        q.add_argument("frame")
        q.add_argument("--out")
        if name == "grid":
            q.add_argument("--step", type=int, default=20)
        if name == "set":
            q.add_argument("--eyes", help="cx,cy,rx,ry;cx,cy,rx,ry")
            q.add_argument("--head-pivot", help="x,y")
            q.add_argument("--neck", help="y0,y1")
            q.add_argument("--chest", help="x,y")
            q.add_argument("--ears", help="tipx,tipy,b0x,b0y,b1x,b1y;...")
            q.add_argument("--preset")
            q.add_argument("--dry-run", action="store_true")
        if name in ("preview", "demo"):
            q.add_argument("--seconds", type=float, default=4.0)
        if name == "preview":
            q.add_argument("--preset")
            q.add_argument("--zoom", type=float, default=0.0)
        if name == "demo":
            q.add_argument("--only", help=T("comma-separated presets", "virgülle paketler"))
    p.set_defaults(func=cmd)
