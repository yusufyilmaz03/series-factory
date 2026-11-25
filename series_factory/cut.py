"""Motion-comic cut: more shots from the same frames, no generated pixels.

`series assemble <ep> --cut [calm|medium|lively]` keeps the whole assemble pipeline (audio mix, lines, titles,
subtitle positions) and only replaces the picture: each frame is split into a few shots at sentence/clause ends,
alternating a wide shot and a closer one framed on the subject. Subtitles highlight the word being spoken.

Rules (decided on real episodes, 25 Nov 2026):
- medium density by default: a shot every ~2-3 s, cuts only at the end of a sentence or clause;
- moves are slow pushes, no shakes, no speed lines; accents ("!", "?") only where the plan asks for one;
- a frame with a character effect (`frame.animate`, see `series animate`) is not cut: the camera pushes in to at most
  1.35x, stops where the effect starts and stays still; the effect keeps its last pose (it does not go back) and
  breathing is off.

Frame fields (optional):
    "cut": {"subject": [x, y], "close": 1.8, "split": false}   # override framing / do not split this frame
    "accent": {"mark": "?", "word": "bakarım."}                  # a small mark that pops in at that word
"""
import math, os, subprocess

from .i18n import T

DENSITY = {          # min seconds per shot, target seconds per shot, max shots per frame
    "calm": (3.2, 4.0, 2),
    "medium": (1.8, 2.6, 3),
    "lively": (1.2, 1.8, 4),
}
ANIM_MAX_ZOOM = 1.35
PUNCT = ".,!?;:…"


def _ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- planning
def split_times(t0, t1, words, density):
    """Cut times inside [t0, t1): midpoints after words that end a sentence or clause."""
    mn, target, mx = DENSITY[density]
    cands = []
    for i, (txt, a, b) in enumerate(words):
        if txt and txt[-1] in PUNCT and t0 + mn <= b and i + 1 < len(words):
            c = (b + words[i + 1][1]) / 2
            if c <= t1 - mn:
                cands.append(c)
    cuts, last = [], t0
    for c in cands:
        if len(cuts) + 1 >= mx:
            break
        if c - last >= max(mn, target * 0.8) and t1 - c >= mn:
            cuts.append(c)
            last = c
    return cuts


def detect_boxes(img_path):
    """Object boxes [(class, conf, x0, y0, x1, y1)] in 0..1 of the frame; [] without the detector."""
    try:
        from . import subplace
        boxes, _ = subplace.detect(img_path)
        return boxes
    except Exception:
        return []


def subject_box(img_path, fr, boxes=None):
    """Subject centre and height (0..1) from the plan, or the object detector, or the picture centre."""
    from PIL import Image
    c = (fr.get("cut") or {})
    if c.get("subject"):
        return c["subject"][0], c["subject"][1], c.get("height", 0.5), True
    boxes = detect_boxes(img_path) if boxes is None else boxes
    if not boxes:
        return None
    w, h = Image.open(img_path).size
    animals = [b for b in boxes if b[0] in ("cat", "dog", "bird")]
    b = (animals or boxes)[0]
    return ((b[2] + b[4]) / 2 * w, (b[3] + b[5]) / 2 * h, b[5] - b[3], False)


def shot_position(boxes, w, h, view, W, H, P, fr):
    """Subtitle band for one shot, judged on what is actually on screen: the frame's boxes are moved into the
    shot's framing (centre, zoom) and the emptiest band wins (same weights and preference as `series subtitles`).
    view: (cx, cy, z) of the shot. A hand-picked "cut": {"subtitle_pos": ...} on the frame wins."""
    hand = (fr.get("cut") or {}).get("subtitle_pos")
    if hand:
        return hand
    if not boxes or "bands" not in P:
        return None
    from . import subplace
    cx, cy, z = view
    scale = max(W / w, H / h) * z
    sb = []
    for cls, conf, x0, y0, x1, y1 in boxes:
        X0, X1 = ((x0 * w - cx) * scale + W / 2) / W, ((x1 * w - cx) * scale + W / 2) / W
        Y0, Y1 = ((y0 * h - cy) * scale + H / 2) / H, ((y1 * h - cy) * scale + H / 2) / H
        if X1 <= 0 or X0 >= 1 or Y1 <= 0 or Y0 >= 1:
            continue
        sb.append((cls, conf, X0, Y0, X1, Y1))
    bands = P["bands"]
    score = {}
    for name, band in bands["narration"].items():
        p = subplace._overlap(sb, band[0] / H, band[1] / H, bands["horizontal"])
        if "line" in bands and name in bands["line"]:
            lb = bands["line"][name]
            p = max(p, subplace._overlap(sb, lb[0] / H, lb[1] / H, bands["horizontal"]))
        score[name] = p
    least = min(score.values())
    return next(t for t in subplace.PREFERENCE if t in score and score[t] - least < subplace.TOLERANCE)


def framings(n, w, h, subj, close_max):
    """n framings: wide, close, medium, ... as (start(cx, cy, z), end(cx, cy, z))."""
    cx0, cy0 = w / 2, h / 2
    if subj:
        sx, sy, sh = subj[0], subj[1], subj[2]
        zc = max(1.35, min(close_max, 0.62 / max(sh, 0.05)))
    else:
        sx, sy, zc = cx0, cy0, 1.5
    zc = min(zc, close_max)
    out = []
    for k in range(n):
        if k % 2 == 0 and k == 0:                     # wide: slow push towards the subject
            a = (cx0, cy0, 1.0)
            b = (cx0 + (sx - cx0) * 0.25, cy0 + (sy - cy0) * 0.25, 1.08)
        elif k % 2 == 1:                              # close on the subject
            a = (sx, sy, zc)
            b = (sx, sy, zc * 1.06)
        else:                                         # medium, between the two
            zm = (1 + zc) / 2
            mx_, my_ = (cx0 + sx) / 2, (cy0 + sy) / 2
            a = (mx_, my_, zm)
            b = (mx_ + (sx - mx_) * 0.2, my_ + (sy - my_) * 0.2, zm * 1.05)
        out.append((a, b))
    return out


def _clamp(cx, cy, z, w, h, W, H):
    """Keep the crop inside the picture."""
    scale = max(W / w, H / h) * z
    hw, hh = W / scale / 2, H / scale / 2
    return min(max(cx, hw), w - hw), min(max(cy, hh), h - hh)


def anim_events(fr, seconds):
    """The frame's effect timeline, starting at 0 and holding its last pose (no return)."""
    from . import animate as A
    an = fr.get("animate") or {}
    ev = an.get("events") or A.preset_events(an.get("preset", "idle"), seconds)
    out = []
    for e in ev:
        e = dict(e)
        if e["type"] in ("pupils", "squint", "look") or (e["type"] == "tilt" and e.get("hold")):
            e["dur"] = seconds - e["start"] + 1.0     # never eases out inside the shot
            e["out"] = 0.01
        out.append(e)
    return out


def plan_shots(shots, frames_dir, plan_frames, words, density, W, H, FPS, P=None):
    """Sub-shots for every assemble shot: [(f0, f1, frame, start(cx,cy,z), end(cx,cy,z), kind, extra)]."""
    from PIL import Image
    out = []
    for sh in shots:
        f0, f1 = sh["f0"], sh["f1"]
        fr = plan_frames.get(sh["frame"], {})
        path = os.path.join(frames_dir, sh["frame"])
        w, h = Image.open(path).size
        close_max = min(2.0, 2.6 * w / 768)           # do not enlarge small frames too much
        boxes = detect_boxes(path)
        subj = subject_box(path, fr, boxes)
        t0, t1 = f0 / FPS, f1 / FPS
        mid = lambda a, b: tuple((a[j] + b[j]) / 2 for j in range(3))  # noqa: E731
        pos = lambda v: {"pos": shot_position(boxes, w, h, v, W, H, P or {}, fr)}  # noqa: E731
        if fr.get("animate") and not (fr["animate"].get("anchors") or {}).get("eyes"):
            # effect asked for, no anchors yet: find them now (no eyes found -> the frame is cut normally)
            from . import anchors as anc
            found = anc.find(path, boxes)
            if found:
                fr = dict(fr, animate=dict(fr["animate"], anchors=found))
                plan_frames[sh["frame"]] = fr
            else:
                print(T(f"  effect skipped, no eyes found: {sh['frame']}", f"  efekt atlandı, göz bulunamadı: {sh['frame']}"))
                fr = {k: v for k, v in fr.items() if k != "animate"}
                plan_frames[sh["frame"]] = fr
        if fr.get("animate"):
            # effect frame: push to the effect framing, then still
            za = min(ANIM_MAX_ZOOM, (fr.get("cut") or {}).get("close", ANIM_MAX_ZOOM))
            sx, sy = (subj[0], subj[1]) if subj else (w / 2, h / 2)
            fz = (w / 2 + (sx - w / 2) * 0.6, h / 2 + (sy - h / 2) * 0.6, za)
            push = min(1.0, 0.3 * (t1 - t0))
            fpush = f0 + round(push * FPS)
            # one subtitle band for the whole effect frame, judged on the still framing
            p_ = pos(fz)
            out.append((f0, fpush, sh["frame"], (w / 2, h / 2, 1.0), fz, "push", dict(p_)))
            out.append((fpush, f1, sh["frame"], fz, fz, "anim", {"t_start": fpush / FPS, **p_}))
            continue
        cuts = [] if (fr.get("cut") or {}).get("split") is False else split_times(t0, t1, words, density)
        bounds = [f0] + [round(c * FPS) for c in cuts] + [f1]
        fs = framings(len(bounds) - 1, w, h, subj, close_max)
        if sh.get("motion", "in").startswith("pan") and len(fs) == 1:
            d = 60 if sh["motion"] == "panR" else -60
            fs = [((w / 2 - d, h / 2, 1.12), (w / 2 + d, h / 2, 1.15))]
        for k in range(len(bounds) - 1):
            out.append((bounds[k], bounds[k + 1], sh["frame"], fs[k][0], fs[k][1], "cut",
                        pos(mid(fs[k][0], fs[k][1]))))
    return out


# ---------------------------------------------------------------- rendering
def render_video(ep, shots, plan_frames, words, out, W, H, FPS, density="medium", frames_dir=None, P=None):
    import numpy as np, cv2
    from PIL import Image, ImageDraw, ImageFont
    from . import core
    frames_dir = frames_dir or core.ep_path(ep, "frames")
    plan = plan_shots(shots, frames_dir, plan_frames, words, density, W, H, FPS, P)
    total = shots[-1]["f1"]
    imgs, anims = {}, {}

    def src(name):
        if name not in imgs:
            imgs[name] = cv2.imread(os.path.join(frames_dir, name)).astype(np.float32)
        return imgs[name]

    for f0, f1, name, a, b, kind, extra in plan:
        if kind == "anim" and name not in anims:
            from . import animate as A
            fr = plan_frames[name]
            cache = os.environ.get("SERIES_ANIMATE_CACHE") or os.path.join(frames_dir, "_animate")
            anims[name] = (A.Animator(os.path.join(frames_dir, name), fr["animate"]["anchors"], cache),
                           anim_events(fr, (f1 - f0) / FPS))

    # accents: (time, mark) from the plan's frame "accent"
    accents = []
    for sh in shots:
        acc = (plan_frames.get(sh["frame"]) or {}).get("accent")
        if acc:
            t0, t1 = sh["f0"] / FPS, sh["f1"] / FPS
            ts = [wa for (tx, wa, wb) in words if t0 <= wa < t1 and tx == acc.get("word")]
            accents.append((ts[0] if ts else t0 + 0.5, t1, acc.get("mark", "!")))
    font_path = None
    for cand in ("DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/System/Library/Fonts/Supplemental/Arial Bold.ttf"):
        try:
            ImageFont.truetype(cand, 10)
            font_path = cand
            break
        except OSError:
            pass

    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                             "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    k = 0
    for i in range(total):
        while k + 1 < len(plan) and i >= plan[k][1]:
            k += 1
        f0, f1, name, a, b, kind, extra = plan[k]
        t = i / FPS
        u = (i - f0) / max(1, f1 - f0)
        e = _ease(u)
        cx, cy, z = (a[j] + (b[j] - a[j]) * e for j in range(3))
        if kind == "anim":
            an, ev = anims[name]
            img = an.render(t - extra["t_start"], ev, breathe=0.0)
        else:
            img = src(name)
        h, w = img.shape[:2]
        cx, cy = _clamp(cx, cy, z, w, h, W, H)
        scale = max(W / w, H / h) * z
        M = np.float32([[scale, 0, W / 2 - scale * cx], [0, scale, H / 2 - scale * cy]])
        f = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)
        if scale > 2.0:
            f = f + 0.45 * (f - cv2.GaussianBlur(f, (0, 0), 1.6))
        f = np.clip(f, 0, 255).astype(np.uint8)
        for (ta, tb, mark) in accents:
            if ta <= t < tb and font_path:
                x = t - ta
                sc = min(1.0, x / 0.15) * (1 + 0.1 * math.exp(-x * 9) * math.cos(x * 25))
                if sc > 0.05:
                    im = Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
                    ImageDraw.Draw(im).text((W * 0.78, H * 0.30), mark, font=ImageFont.truetype(font_path, int(130 * sc)),
                                            fill=(255, 255, 255), stroke_width=10, stroke_fill=(0, 0, 0), anchor="mm")
                    f = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
        proc.stdin.write(f.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit(T("cut: video encoding failed", "kurgu: video kodlanamadı"))
    n_shots = len(plan)
    print(T(f"cut ({density}): {n_shots} shots from {len(shots)} frames",
            f"kurgu ({density}): {len(shots)} kareden {n_shots} çekim"))
    return plan


def positions(plan, FPS):
    """[(t0, t1, pos)] from a cut plan (pos None = keep the frame's own position)."""
    return [(f0 / FPS, f1 / FPS, (extra or {}).get("pos")) for f0, f1, _, _, _, _, extra in plan]


def karaoke(events, words, color="&H0000D6FF&"):
    """Subtitle events with the spoken word highlighted: each narration event (any Default* style, i.e. after the
    position is chosen) is split per word; the chunk keeps one position."""
    out = []
    for st, a, b, tx in events:
        if not st.startswith("Default"):
            out.append((st, a, b, tx))
            continue
        toks = tx.split(" ")
        ws = [w for w in words if a - 0.06 <= w[1] < b]
        # match the event's words by order
        times = []
        j = 0
        for tok in toks:
            while j < len(ws) and ws[j][0] != tok:
                j += 1
            times.append(ws[j][1] if j < len(ws) else None)
            j += 1
        if None in times or not toks:
            out.append((st, a, b, tx))
            continue
        for i, tok in enumerate(toks):
            s_ = a if i == 0 else times[i]
            e_ = times[i + 1] if i + 1 < len(toks) else b
            if e_ - s_ < 0.02:
                continue
            txt = " ".join(("{\\c" + color + "}" + x + "{\\r}") if q == i else x for q, x in enumerate(toks))
            out.append((st, s_, e_, txt))
    return out
