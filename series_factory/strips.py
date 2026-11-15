"""Motion strips and timing check (from the finished MP4).

A contact sheet shows frames; this shows motion: transitions, Ken Burns, subtitle timing. It knows frame borders and
reads from the timing file `series assemble` writes next to the video.

  series strips 003                     report + transition strips + overview (default)
  series strips 003 --report            timing report only (no images)
  series strips 003 --frame 05_x.jpg [--step 0.15]   one whole frame, dense
  series strips 003 --range 12:14.5 [--step 0.1]     chosen seconds
  series strips 003 --transitions [--pad 0.5]        ±0.5 s around every cut, one cut per row
  --video <mp4> (default: newest in output/)   --to <folder> (default: the preview folder)   --json (report as JSON)
Every thumbnail shows the video time in its corner.
"""
import glob, json, os, re, subprocess, sys, tempfile, time

from . import core
from .core import READ_SEC
from .i18n import T
from .migrate import timing_to_v2

LABEL = r"drawtext=text='%{{pts\:flt\:{ofs:.3f}}}':x=4:y=4:fontsize={fs}:fontcolor=white:box=1:boxcolor=black@0.55"
_label_ok = [True]


def ffmpeg(args):
    return subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)


def strip(video, a, b, step, cols, out, tw=None):
    """One picture every 'step' s from [a, b]; a grid with cols columns."""
    P = core.profile()
    tw = tw or P["strip_width"]
    n = max(1, round((b - a) / step) + 1)
    rows = -(-n // cols)
    th = round(tw * P["height"] / P["width"] / 2) * 2
    base = f"fps=1/{step},scale={tw}:{th}"
    r = None
    for lab in ([True, False] if _label_ok[0] else [False]):
        vf = base + ("," + LABEL.format(ofs=a, fs=max(12, tw // 12)) if lab else "") + \
            f",tile={cols}x{rows}:padding=4:color=0x202020"
        r = ffmpeg(["-ss", f"{max(0, a):.3f}", "-t", f"{b - a + step / 2:.3f}", "-i", video, "-vf", vf,
                    "-frames:v", "1", "-q:v", "4", out])
        if r.returncode == 0:
            return out
        if lab:
            _label_ok[0] = False      # font not found: try without labels
    raise SystemExit(T("ffmpeg error: ", "ffmpeg hatası: ") + r.stderr[-400:])


def stack(parts, out):
    if len(parts) == 1:
        os.replace(parts[0], out)
        return out
    ins = sum([["-i", p] for p in parts], [])
    fl = "".join(f"[{i}]pad=iw:ih+8:0:0:0x101010[p{i}];" for i in range(len(parts)))
    w = max(int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width",
                                "-of", "csv=p=0", p], capture_output=True, text=True).stdout) for p in parts)
    fl += "".join(f"[p{i}]pad={w}:ih:0:0:0x101010[q{i}];" for i in range(len(parts)))
    fl += "".join(f"[q{i}]" for i in range(len(parts))) + f"vstack=inputs={len(parts)}"
    r = ffmpeg([*ins, "-filter_complex", fl, "-frames:v", "1", "-q:v", "4", out])
    if r.returncode:
        raise SystemExit(T("ffmpeg error: ", "ffmpeg hatası: ") + r.stderr[-400:])
    return out


def scene_cuts(video):
    """No timing file: find cuts from the picture."""
    r = subprocess.run(["ffmpeg", "-i", video, "-vf", "select='gt(scene,0.25)',showinfo", "-f", "null", "-"],
                       capture_output=True, text=True)
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def report(z):
    """Timing check: do reads fit, dead frames, repeated motion/transition, does the last read land."""
    z = timing_to_v2(z)
    K = z["frames"]
    warn, rows = [], []
    rows.append(T(f"{'frame':<20}{'time':>13}{'dur':>6}{'silent':>7}{'reads':>6}{'s/rd':>6}  {'motion':<7} in",
                  f"{'kare':<20}{'zaman':>13}{'süre':>6}{'sessiz':>7}{'okuma':>6}{'sn/ok':>6}  {'hareket':<7} giriş"))
    for i, k in enumerate(K):
        d = k["t1"] - k["t0"]
        silent = k["t1"] - k.get("speech_end", k["t1"])
        n = len(k.get("reads") or [])
        g = k["transition"]["type"] + (f" {k['transition']['duration']:.2f}" if k["transition"]["type"] != "cut" else "")
        rows.append(f"{k['frame'][:19]:<20}{k['t0']:6.2f}–{k['t1']:<6.2f}{d:6.2f}{silent:7.2f}{n:6d}"
                    f"{(d / n if n else 0):6.2f}  {k['motion']:<7} {g}")
        f = k["frame"]
        if n and d / n < READ_SEC:
            warn.append(T(f"{f}: reads crammed ({n} reads in {d:.1f} s; ≥ {READ_SEC} per read)",
                          f"{f}: okumalar sıkışık ({n} okuma {d:.1f} sn'de; okuma başına ≥ {READ_SEC})"))
        if k["motion"] == "static" and d > 2:
            warn.append(T(f"{f}: {d:.1f} s without motion (dead frame)", f"{f}: {d:.1f} sn hareketsiz (ölü kare)"))
        if d < 1.0:
            warn.append(T(f"{f}: {d:.2f} s, too short to read", f"{f}: {d:.2f} sn, okunamayacak kadar kısa"))
        if d > 9:
            warn.append(T(f"{f}: single picture for {d:.1f} s; consider a second frame or stronger motion",
                          f"{f}: tek görüntü {d:.1f} sn; ikinci kare ya da daha belirgin hareket düşün"))
        if i and k["motion"] == K[i - 1]["motion"] and k["motion"] != "fast":
            warn.append(T(f"{f}: same motion as the previous frame ({k['motion']})",
                          f"{f}: önceki kareyle aynı hareket ({k['motion']})"))
        if i and k["scene"] != K[i - 1]["scene"] and k["transition"]["type"] == "cut":
            warn.append(T(f"{f}: hard cut at a scene start (needs a transition or a cut on action)",
                          f"{f}: sahne başında sert kesme (geçiş ya da hareketin ortasında kesme olmalı)"))
    if not any(k.get("reads") for k in K):
        warn.append(T("no reads in the plan: fit check not possible (required in new plans)",
                      "planda okumalar yok: sığma kontrolü yapılamadı (yeni planlarda zorunlu)"))
    last = K[-1]
    tail = last["t1"] - last.get("speech_end", last["t1"])
    if tail < 0.8:
        warn.append(T(f"{last['frame']}: the video ends {tail:.2f} s after the last word; ≥ 0.8 for the last read (hold)",
                      f"{last['frame']}: son söz bittikten {tail:.2f} sn sonra video bitiyor; son okuma için ≥ 0.8 (karede bekle)"))
    types = [k["transition"]["type"] for k in K[1:] if k["transition"]["type"] != "cut"]
    if len(types) >= 4 and len(set(types)) == 1:
        warn.append(T(f"note: every transition is the same ({types[0]}); vary them with the story",
                      f"not: bütün geçişler aynı ({types[0]}); hikâyeye göre çeşitlendir"))
    if K[0]["transition"]["type"] != "cut":
        warn.append(T("the first frame opens with a transition; the first frame is the hook and should start directly",
                      "ilk kare geçişle açılıyor; Reels'te ilk kare kancadır, doğrudan başlamalı"))
    return "\n".join(rows), warn


def latest_video(ep):
    return max(glob.glob(core.ep_path(ep, "output", "*.mp4")), key=os.path.getmtime, default=None)


def timing_for(video):
    zf = os.path.splitext(video)[0] + core.layout("timing_suffix")
    return timing_to_v2(json.load(open(zf, encoding="utf-8"))) if os.path.exists(zf) else None


def video_duration(v):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", v],
                                capture_output=True, text=True).stdout)


def cmd(a):
    ep = core.episode_dir(a.episode)
    video = a.video or latest_video(ep)
    if not video:
        sys.exit(T("No video: run 'series assemble' first.", "Video yok: önce 'series assemble' çalıştır."))
    z = timing_for(video)
    if a.json:
        table, warn = report(z) if z else ("", [])
        print(json.dumps({"video": os.path.basename(video), "warnings": warn, "frames": (z or {}).get("frames", [])},
                         ensure_ascii=False, indent=1))
        return 0
    to = a.to or core.series_path("preview")
    os.makedirs(to, exist_ok=True)
    pre = f"{core.episode_no(ep)}_{time.strftime('%H%M%S')}"
    everything = not (a.report or a.transitions or a.frame or a.range)
    print("video:", os.path.basename(video), f"({video_duration(video):.1f} {T('s', 'sn')})")
    if a.report or everything:
        if z:
            table, warn = report(z)
            print(table)
            print("\n" + ("\n".join("⚠ " + u for u in warn) if warn else T("✓ no timing problems", "✓ zamanlama kontrolünde sorun yok")))
        else:
            print(T("no timing file (old edit): rebuild with 'series assemble' for the report.",
                    "zaman dosyası yok (eski montaj): rapor için 'series assemble' ile yeniden üret."))
    out = []
    if a.range:
        x, y = map(float, a.range.split(":"))
        out.append(strip(video, x, y, a.step or 0.1, 8, os.path.join(to, f"{pre}_range.jpg")))
    if a.frame:
        if not z:
            sys.exit(T("--frame needs the timing file (rebuild with 'series assemble').",
                       "--frame için zaman dosyası gerekli ('series assemble' ile yeniden üret)."))
        k = next((k for k in z["frames"] if k["frame"] == a.frame), None) or sys.exit(T(f"no frame: {a.frame}", f"kare yok: {a.frame}"))
        out.append(strip(video, k["t0"], k["t1"], a.step or 0.15, 8, os.path.join(to, f"{pre}_{a.frame[:-4]}.jpg")))
    if a.transitions or everything:
        cuts = [k["t0"] for k in z["frames"][1:]] if z else scene_cuts(video)
        if cuts:
            tmp = tempfile.mkdtemp()
            step = a.step or 0.1
            parts = [strip(video, t - a.pad, t + a.pad, step, round(2 * a.pad / step) + 1,
                           os.path.join(tmp, f"g{i:02d}.jpg"), tw=round(core.profile()["strip_width"] * 0.75))
                     for i, t in enumerate(cuts)]
            out.append(stack(parts, os.path.join(to, f"{pre}_transitions.jpg")))
    if everything:
        s = video_duration(video)
        out.append(strip(video, 0, s - 0.05, 1.0, 10, os.path.join(to, f"{pre}_overview.jpg"),
                         tw=round(core.profile()["strip_width"] * 0.75)))
    for o in out:
        print("→", core.rel(o) if o.startswith(core.root()) else o)
    return 0


def add_parser(sp):
    p = sp.add_parser("strips", help=T("timing report + motion strips of a finished video", "bitmiş videonun zamanlama raporu + hareket şeritleri"))
    p.add_argument("episode"); p.add_argument("--video"); p.add_argument("--to")
    p.add_argument("--report", action="store_true"); p.add_argument("--transitions", action="store_true")
    p.add_argument("--frame"); p.add_argument("--range"); p.add_argument("--step", type=float)
    p.add_argument("--pad", type=float, default=0.5); p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd)
