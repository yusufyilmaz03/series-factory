"""Production line in one command.

  series produce new [--idea G-05] [--note "..."]   1) write the script -> episodes/NNN_slug/ (stops for approval)
  series produce 002                                2) frames -> voice -> assemble (does what is missing)
        --stop-after-frames   stop when frames exist (check frames/<contact>)
        --no-sfx
  series produce status 002 [--json]                which steps are ready, what is missing
  series contact 002 [--video]                      contact sheet of the frames (or the video) in the preview folder
(after assembling, the timing report is printed; for strips: series strips 002)

Every step also runs alone: series script / frames / voice / assemble. Existing files are never regenerated (no wasted
credit); to start over use the step's own --redo.
"""
import glob, os, subprocess, sys, time

from . import core
from .core import all_frame_files, lines
from .i18n import T


def run_step(*args):
    r = subprocess.run([sys.executable, "-m", "series_factory", "--series", core.root(), *args])
    if r.returncode:
        sys.exit(T(f"\n✗ 'series {args[0]}' failed (exit {r.returncode}). Fix the error and run the same command again; "
                   "finished steps are skipped.",
                   f"\n✗ 'series {args[0]}' başarısız (çıkış {r.returncode}). Hatayı düzeltip aynı komutu yeniden çalıştır; "
                   "biten adımlar atlanır."))


def missing_frames(ep, d):
    return [f for f in all_frame_files(d) if not os.path.exists(core.ep_path(ep, "frames", f))]


def contact(ep):
    kd = core.ep_path(ep, "frames")
    if not glob.glob(os.path.join(kd, "[0-9]*.jpg")):
        return None
    c = core.profile()["contact"]
    tw, th = c["thumb"]
    out = os.path.join(kd, core.layout("contact"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-pattern_type", "glob", "-i", os.path.join(kd, "[0-9]*.jpg"),
                    "-vf", f"scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},tile={c['tile']}:padding=6",
                    "-frames:v", "1", "-q:v", "3", out])
    return out


def status(ep, as_json=False):
    d = core.load_plan(ep)
    mf = missing_frames(ep, d)
    aud = core.ep_path(ep, "audio")
    ml = [n for n, _, _ in lines(d) if not os.path.exists(os.path.join(aud, core.layout("line", n=n) + ".mp3"))]
    videos = [os.path.basename(c) for c in glob.glob(core.ep_path(ep, "output", "*.mp4"))]
    narr = os.path.exists(os.path.join(aud, core.layout("words")))
    data = {"episode": os.path.basename(ep), "title": d.get("title"), "plan": True, "missing_frames": mf,
            "narration": narr, "missing_lines": ml, "videos": videos}
    ready, none_ = T("ready", "hazır"), T("none", "yok")
    core.emit(data, as_json, [
        f"{os.path.basename(ep)} — {d.get('title')}",
        T("  plan     : ", "  plan     : ") + ready,
        T("  frames   : ", "  kareler  : ") + (ready if not mf else T(f"missing {len(mf)}: ", f"eksik {len(mf)}: ") + ", ".join(mf)),
        T("  narration: ", "  anlatım  : ") + (ready if narr else none_),
        T("  lines    : ", "  replikler: ") + (ready if not ml else T(f"missing: {ml}", f"eksik: {ml}")),
        T("  video    : ", "  video    : ") + (", ".join(videos) or none_)])
    return mf


def cmd(a):
    if a.target == "new":
        run_step("script", "new", *(["--idea", a.idea] if a.idea else []), *(["--note", a.note] if a.note else []))
        print(T("\n→ Check the script; if it is good: series produce <episode_no>",
                "\n→ Senaryoyu kontrol et; uygunsa: series produce <bolum_no>"))
        return 0
    if a.target == "status":
        status(core.episode_dir(a.rest[0]), a.json)
        return 0
    ep = core.episode_dir(a.target)
    print(T("● plan check", "● plan kontrolü"))
    run_step("script", "validate", ep)
    print(T("● frames", "● kareler"))
    run_step("frames", ep)
    mf = missing_frames(ep, core.load_plan(ep))
    k = contact(ep)
    if mf:
        print(T(f"\n→ {len(mf)} frames missing. Make them with the prompts in the guide, put them in {core.layout('frames')}/ "
                "(or the incoming folder + 'series frames --place'), then run the same command again.",
                f"\n→ {len(mf)} kare eksik. Rehberdeki prompt'larla üretip {core.layout('frames')}/ klasörüne koy "
                "(ya da gelen klasörüne + 'series frames --place'), sonra aynı komutu yeniden çalıştır."))
        return 0
    if a.stop_after_frames:
        print(T("\n→ Frames ready, check:", "\n→ Kareler hazır, kontrol için:"), k)
        return 0
    print(T("● voice", "● sesler"))
    run_step("voice", "episode", ep)
    print(T("● assemble", "● montaj"))
    run_step("assemble", ep, *(["--no-sfx"] if a.no_sfx else []))
    print(T("● timing check", "● zamanlama kontrolü"))
    subprocess.run([sys.executable, "-m", "series_factory", "--series", core.root(), "strips", ep, "--report"])
    print(T("\n✓ done:", "\n✓ bitti:"), core.ep_path(ep, "output", os.path.basename(ep) + ".mp4"))
    print(T("  to see the motion: series strips", "  hareketi görmek için: series strips"), core.episode_no(ep))
    return 0


def cmd_contact(a):
    ep = core.episode_dir(a.episode)
    stamp = time.strftime("%H%M%S")
    os.makedirs(core.series_path("preview"), exist_ok=True)
    out = core.series_path("preview", f"{core.episode_no(ep)}_{'video' if a.video else 'frames'}_{stamp}.jpg")
    P = core.profile()
    tw = 360
    th = round(tw * P["height"] / P["width"])
    if a.video:
        v = sorted(glob.glob(core.ep_path(ep, "output", "*.mp4")), key=os.path.getmtime)[-1]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", v, "-vf", "fps=1/3.5,scale=216:-2,tile=6x3",
                        "-frames:v", "1", "-q:v", "4", out], check=True)
    else:
        fs = sorted(glob.glob(core.ep_path(ep, "frames", "[0-9]*.jpg")))
        n = len(fs)
        cols = 5 if n > 8 else 4
        ins = sum([["-i", f] for f in fs], [])
        fl = "".join(f"[{i}]scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2[v{i}];"
                     for i in range(n))
        lay = "|".join(f"{(i % cols) * tw}_{(i // cols) * th}" for i in range(n))
        fl += "".join(f"[v{i}]" for i in range(n)) + f"xstack=inputs={n}:layout={lay}:fill=black"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", fl, "-frames:v", "1", "-q:v", "4", out],
                       check=True)
    print(out)
    return 0


def add_parser(sp):
    p = sp.add_parser("produce", help=T("whole line: plan check -> frames -> voice -> assemble", "tüm hat: plan kontrolü -> kareler -> ses -> montaj"))
    p.add_argument("target", help=T("episode, 'new' or 'status'", "bölüm, 'new' ya da 'status'"))
    p.add_argument("rest", nargs="*")
    p.add_argument("--stop-after-frames", action="store_true"); p.add_argument("--no-sfx", action="store_true")
    p.add_argument("--json", action="store_true"); p.add_argument("--idea"); p.add_argument("--note")
    p.set_defaults(func=cmd)
    c = sp.add_parser("contact", help=T("contact sheet of frames or video", "karelerin ya da videonun kontrol sayfası"))
    c.add_argument("episode"); c.add_argument("--video", action="store_true")
    c.set_defaults(func=cmd_contact)
