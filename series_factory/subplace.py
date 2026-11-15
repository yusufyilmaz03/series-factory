"""Subtitle placement (optional extra): decides where subtitles go (top | middle | bottom) as soon as a frame exists.

Finds cats, dogs, birds and people in the frame with a YOLO11n ONNX model run by onnxruntime, weights faces more
(upper part of the box), accounts for how the Ken Burns motion shifts the bands, scores how much each band overlaps
"subjects" and picks the emptiest band.

Install:  pip install "series-factory[subtitles]"
Model:    the YOLO11n weights (Ultralytics, AGPL-3.0) are NOT shipped. Export them once:
            pip install ultralytics && yolo export model=yolo11n.pt format=onnx
          then point to the file with SERIES_YOLO_MODEL=/path/yolo11n.onnx, series.json "subtitles": {"model": "..."},
          or put it at ~/.cache/series-factory/yolo11n.onnx.  `series subtitles model` shows what is found.
Without the extra or the model, frames without "subtitle_pos" get "bottom" (or set it by hand in the plan).

  series subtitles 013                 show decisions (does not write the plan)
  series subtitles 013 --write         write to frames without a hand-picked position ("subtitle_pos" + "subtitle_auto")
  series subtitles 013 --write --redo  recompute automatic ones too (hand-picked ones are never touched)
  series subtitles 013 --compare       compare with hand-picked positions
  series subtitles --image x.jpg [--motion in]
"""
import os, sys

from . import core
from .i18n import T

PREFERENCE = ["top", "bottom", "middle"]   # if scores are within TOLERANCE, this order wins
TOLERANCE = 0.1
ZOOM = {"in": (1.0, 1.12), "out": (1.0, 1.12), "fast": (1.0, 1.3), "panL": (1.12, 1.12), "panR": (1.12, 1.12),
        "static": (1.0, 1.0)}
# 77 = teddy bear: the model sometimes sees stylised 3D cats this way
CLASSES = {0: "person", 14: "bird", 15: "cat", 16: "dog", 77: "cat"}
THRESH = {"person": 0.30, "bird": 0.15, "cat": 0.12, "dog": 0.12}
# (face start, face end as a share of box height; face weight, body weight). Text may cover a body, ear or leg;
# the face is what to avoid.
WEIGHT = {"cat": (0.08, 0.42, 3.0, 0.3), "dog": (0.08, 0.42, 3.0, 0.3), "bird": (0.0, 1.0, 1.5, 1.5),
          "person": (0.0, 0.18, 3.0, 0.3)}
_session = None


def model_path():
    cands = [os.environ.get("SERIES_YOLO_MODEL")]
    try:
        m = core.cfg().get("subtitles", {}).get("model")
        cands.append(core.path(m) if m else None)
    except SystemExit:
        pass
    cands.append(os.path.expanduser("~/.cache/series-factory/yolo11n.onnx"))
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def session():
    global _session
    if _session is None:
        import onnxruntime as ort
        m = model_path()
        if not m:
            raise RuntimeError(T("YOLO11n model not found (see 'series subtitles model')",
                                 "YOLO11n modeli bulunamadı (bkz. 'series subtitles model')"))
        _session = ort.InferenceSession(m, providers=["CPUExecutionProvider"])
    return _session


def detect(path, thresh=0.12):
    """[(class, conf, x0, y0, x1, y1)] — coordinates 0..1 of the image."""
    import numpy as np
    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = 640 / max(w, h)
    nw, nh = round(w * s), round(h * s)
    canvas = Image.new("RGB", (640, 640), (114, 114, 114))
    ox, oy = (640 - nw) // 2, (640 - nh) // 2
    canvas.paste(im.resize((nw, nh)), (ox, oy))
    x = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
    o = session()
    out = o.run(None, {o.get_inputs()[0].name: x})[0][0].T          # (8400, 84)
    score = out[:, 4:]
    cls = score.argmax(1)
    conf = score.max(1)
    m = (conf > thresh) & np.isin(cls, list(CLASSES))
    boxes = []
    for (cx, cy, bw, bh), c, k in zip(out[m, :4], conf[m], cls[m]):
        x0, y0 = (cx - bw / 2 - ox) / s / w, (cy - bh / 2 - oy) / s / h
        x1, y1 = (cx + bw / 2 - ox) / s / w, (cy + bh / 2 - oy) / s / h
        if c < THRESH[CLASSES[int(k)]]:
            continue
        boxes.append([CLASSES[int(k)], float(c), max(0, x0), max(0, y0), min(1, x1), min(1, y1)])
    boxes.sort(key=lambda b: -b[1])
    chosen = []
    for b in boxes:                                                # class-agnostic NMS
        if all(iou(b, a) < 0.5 for a in chosen):
            chosen.append(b)
    return chosen, (w, h)


def iou(a, b):
    ix = max(0, min(a[4], b[4]) - max(a[2], b[2]))
    iy = max(0, min(a[5], b[5]) - max(a[3], b[3]))
    i = ix * iy
    u = (a[4] - a[2]) * (a[5] - a[3]) + (b[4] - b[2]) * (b[5] - b[3]) - i
    return i / u if u > 0 else 0


def source_band(band, motion, ratio, W, H):
    """Output band (pixels) -> 0..1 vertical range in the source image (at the motion's middle zoom).
    ratio: image width/height; if it differs from the output, the edit crops (fills from the centre)."""
    a, b = band[0] / H, band[1] / H
    target = W / H
    scale = target / ratio if ratio < target else 1.0                 # visible height / image height
    z0, z1 = ZOOM.get(motion or "in", (1.0, 1.12))
    z = (z0 + z1) / 2
    return tuple(0.5 + (0.5 + (y - 0.5) / z - 0.5) * scale for y in (a, b))


def _overlap(boxes, ya, yb, horiz):
    p = 0.0
    for cls, conf, x0, y0, x1, y1 in boxes:
        hz = max(0, min(x1, horiz[1]) - max(x0, horiz[0])) / (horiz[1] - horiz[0])
        if hz <= 0:
            continue
        ys, ye, wf, wb = WEIGHT[cls]
        fa, fb = y0 + (y1 - y0) * ys, y0 + (y1 - y0) * ye
        face = max(0, min(fb, yb) - max(fa, ya)) / (yb - ya)
        whole = max(0, min(y1, yb) - max(y0, ya)) / (yb - ya)
        p += conf * hz * (wf * face + wb * max(0, whole - face))
    return p


def score(boxes, motion, ratio, with_line=False):
    P = core.profile()
    W, H, bands = P["width"], P["height"], P["bands"]
    out = {}
    for name, band in bands["narration"].items():
        p = _overlap(boxes, *source_band(band, motion, ratio, W, H), bands["horizontal"])
        if with_line:
            p = max(p, _overlap(boxes, *source_band(bands["line"][name], motion, ratio, W, H), bands["horizontal"]))
        out[name] = round(float(p), 3)
    return out


def decide(image, motion="in", with_line=False):
    boxes, (w, h) = detect(image)
    p = score(boxes, motion, w / h, with_line)
    least = min(p.values())
    choice = next(t for t in PREFERENCE if p[t] - least < TOLERANCE)
    return choice, p, boxes


def episode(e, write=False, redo=False, compare=False, quiet=False):
    ep = core.episode_dir(e)
    d = core.load_plan(ep)
    same = diff = changed = 0
    for s in d["scenes"]:
        for fr in s["frames"]:
            g = core.ep_path(ep, "frames", fr["file"])
            if not os.path.exists(g):
                continue
            manual = fr.get("subtitle_pos") and not fr.get("subtitle_auto")
            if write and manual and not compare:
                continue
            if write and fr.get("subtitle_auto") and not redo:
                continue
            sel, p, boxes = decide(g, fr.get("motion", "in"), bool(s.get("dialogue")))
            summ = ", ".join(f"{k[0]}{k[1]:.2f}" for k in boxes[:4]) or T("no subject", "özne yok")
            if compare:
                if not manual:
                    continue
                eq = fr["subtitle_pos"] == sel
                same += eq
                diff += not eq
                if not eq or not quiet:
                    print(f"{'✓' if eq else '✗'} {core.episode_no(ep)}/{fr['file']:<22} "
                          f"{T('hand', 'elle')}={fr['subtitle_pos']:<6} auto={sel:<6} {p}  [{summ}]")
                continue
            if not quiet:
                print(f"{fr['file']:<24} {sel:<6} {p}  [{summ}]")
            if write and fr.get("subtitle_pos") != sel:
                fr["subtitle_pos"] = sel
                fr["subtitle_auto"] = True
                changed += 1
            elif write:
                fr["subtitle_auto"] = True
    if write and not compare:
        core.save_plan(ep, d)
        print(T(f"{os.path.basename(ep)}: subtitle position written for {changed} frames",
                f"{os.path.basename(ep)}: {changed} karenin altyazı yeri yazıldı"))
    return same, diff


def single_frame(ep, file):
    """Called when a frame is saved: writes the position to the plan unless it was picked by hand."""
    d = core.load_plan(ep)
    for s in d["scenes"]:
        for fr in s["frames"]:
            if fr["file"] == file and (not fr.get("subtitle_pos") or fr.get("subtitle_auto")):
                sel, _, _ = decide(core.ep_path(ep, "frames", file), fr.get("motion", "in"), bool(s.get("dialogue")))
                fr["subtitle_pos"] = sel
                fr["subtitle_auto"] = True
                core.save_plan(ep, d)
                return sel
    return None


def cmd(a):
    if a.target == "model":
        m = model_path()
        try:
            import onnxruntime  # noqa: F401
            rt = True
        except ImportError:
            rt = False
        print(T("onnxruntime: ", "onnxruntime: ") + (T("installed", "kurulu") if rt else T("missing (pip install \"series-factory[subtitles]\")", "yok (pip install \"series-factory[subtitles]\")")))
        print(T("model: ", "model: ") + (m or T("not found", "bulunamadı")))
        if not m:
            print(T("The YOLO11n weights are AGPL-3.0 and not shipped. To create them once:\n"
                    "  pip install ultralytics && yolo export model=yolo11n.pt format=onnx\n"
                    "then move yolo11n.onnx to ~/.cache/series-factory/ (or set SERIES_YOLO_MODEL).",
                    "YOLO11n ağırlıkları AGPL-3.0 lisanslı ve repoda yok. Bir kez oluşturmak için:\n"
                    "  pip install ultralytics && yolo export model=yolo11n.pt format=onnx\n"
                    "sonra yolo11n.onnx dosyasını ~/.cache/series-factory/ altına taşı (ya da SERIES_YOLO_MODEL ayarla)."))
        return 0
    if a.image:
        sel, p, boxes = decide(a.image, a.motion)
        print(sel, p, [(k[0], round(k[1], 2), [round(v, 2) for v in k[2:]]) for k in boxes])
        return 0
    if a.compare:
        ts = tf = 0
        for e in [a.target] + (a.more or []):
            x, y = episode(e, compare=True, quiet=a.quiet)
            ts += x
            tf += y
        print(T(f"agreement: {ts}/{ts + tf}", f"uyum: {ts}/{ts + tf}"))
        return 0
    episode(a.target, write=a.write, redo=a.redo)
    return 0


def add_parser(sp):
    p = sp.add_parser("subtitles", help=T("automatic subtitle position (optional extra)", "otomatik altyazı yeri (opsiyonel)"))
    p.add_argument("target", nargs="?", default="model", help=T("episode, or 'model'", "bölüm ya da 'model'"))
    p.add_argument("more", nargs="*")
    p.add_argument("--write", action="store_true"); p.add_argument("--redo", action="store_true")
    p.add_argument("--compare", action="store_true"); p.add_argument("--quiet", action="store_true")
    p.add_argument("--image"); p.add_argument("--motion", default="in")
    p.set_defaults(func=cmd)
