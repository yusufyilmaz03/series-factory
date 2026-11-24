"""Episode catalog: every episode folder with its plan, production stage and usage of codes/sounds.

Shared by status, ideas, cards and publish. Nothing here is copied into files; it is derived from the episodes
on every call.
"""
import glob, json, os, re, unicodedata

from . import core
from .i18n import T

STAGES = ("script", "frames", "frames_done", "audio", "carousel", "video")


def stage_name(s):
    return {"script": T("script", "senaryo"), "frames": T("frames", "kareler"),
            "frames_done": T("frames done", "kareler tamam"), "audio": T("audio", "ses"),
            "video": T("video", "video"), "carousel": T("carousel", "karusel")}.get(s, s)


def nfc(s):
    return unicodedata.normalize("NFC", s)


def ascii_upper(s):
    s = nfc(s).replace("ı", "i").replace("İ", "I")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()


def fold(s):
    return ascii_upper(s).lower()


def episodes():
    out = []
    for path, fmt in core.episode_folders():
        d = os.path.basename(path)
        if not os.path.exists(os.path.join(path, core.layout("plan"))):
            continue
        try:
            j = core.load_plan(path)
        except Exception as e:
            out.append({"folder": d, "path": path, "error": str(e)})
            continue
        out.append({"folder": d, "path": path, "plan": j, "format": fmt or core.episode_format(path, j)})
    return out


def episode_summary(b):
    j, ep = b["plan"], b["path"]
    frames = core.all_frame_files(j)
    have = sum(os.path.exists(core.ep_path(ep, "frames", f)) for f in frames)
    audio = os.path.exists(core.ep_path(ep, "audio", core.layout("words")))
    outs = sorted(glob.glob(core.ep_path(ep, "output", "*.mp4")), key=os.path.getmtime)
    last = os.path.basename(outs[-1]) if outs else ""
    dur = ""
    tj = sorted(glob.glob(core.ep_path(ep, "output", "*" + core.layout("timing_suffix"))), key=os.path.getmtime)
    if tj:
        try:
            z = json.load(open(tj[-1]))
            dur = f"{z.get('duration', z.get('sure')):.1f}"
        except Exception:
            pass
    fmt = b.get("format") or core.episode_format(ep, j)
    outs_wanted = core.format_outputs(fmt)
    slides = sorted(glob.glob(core.ep_path(ep, "carousel", "*.jpg")))
    slides = [x for x in slides if not os.path.basename(x).startswith("_")]
    n_slides = len((j.get("carousel") or {}).get("slides", []))
    carousel_done = bool(slides) and (not n_slides or len(slides) >= n_slides)
    have_out = {"video": bool(last), "carousel": carousel_done}
    rule = any if core.formats().get(fmt, {}).get("ready") == "any" else all
    done = rule(have_out.get(o, False) for o in outs_wanted)
    if last:
        stage = "video"
    elif carousel_done:
        stage = "carousel"
    elif audio:
        stage = "audio"
    elif frames and have == len(frames):
        stage = "frames_done"
    elif have:
        stage = "frames"
    else:
        stage = "script"
    return {"no": b["folder"][:4].rstrip("_"), "title": j.get("title", ""), "idea": j.get("source_idea") or "",
            "format": fmt, "frames": f"{have}/{len(frames)}", "stage": stage, "duration": dur, "video": last,
            "carousel": len(slides), "outputs": outs_wanted, "ready": done}


def episode_no(folder):
    return re.match(r"\d{3}[a-z]?", folder).group(0)


_USAGE = {}


def usage():
    """From the plans: frame refs / dialogue -> {code: [episode no]}, sounds -> {id: [episode no]}, order."""
    if _USAGE:
        return _USAGE
    frame, dialogue, sound, order = {}, {}, {}, []

    def add(d, k, no):
        if k and no not in d.setdefault(k, []):
            d[k].append(no)

    for b in episodes():
        if "plan" not in b:
            continue
        no, j = episode_no(b["folder"]), b["plan"]
        order.append(no)
        for s in j.get("scenes", []):
            for k in s.get("frames", []):
                for r in k.get("refs", []):
                    add(frame, r, no)
            for r in s.get("dialogue", []):
                add(dialogue, r.get("character"), no)
        for e in j.get("sfx") or []:
            add(sound, e.get("id") if isinstance(e, dict) else None, no)
        m = j.get("music")
        add(sound, m.get("id") if isinstance(m, dict) else None, no)
    _USAGE.update(frame=frame, dialogue=dialogue, sound=sound, order=order)
    return _USAGE


def ranges(nos):
    """Join consecutive episodes in episode order: 001,002,003,005 -> 001-003,005"""
    order = usage()["order"]
    idx = sorted({order.index(n) for n in nos if n in order})
    out, i = [], 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and idx[j + 1] == idx[j] + 1:
            j += 1
        out.append(order[idx[i]] if j == i else order[idx[i]] + ("-" if j > i + 1 else ",") + order[idx[j]])
        i = j + 1
    return ",".join(out) or "—"


def usage_row(nos):
    return f"{ranges(nos)} ({len(nos)})" if nos else T("— (in no plan)", "— (hiçbir planda yok)")
