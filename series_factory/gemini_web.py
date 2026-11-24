"""Gemini web adapter: frames are made in the Gemini web app (a browser the user is signed in to), not through the API.

The engine only prepares and collects; the browser side is a small page helper plus an Apps Script bridge
(templates/bridge/: gemini_page.js, bridge.gs). Exchange goes through a Drive-synced folder (paths.exchange):

  series gemini prepare 067 [--frames 05b_screen,06_end]   references + job list -> <exchange>/<no>_job.json
  series gemini collect 066 [--wait 4]                     returned frames -> episode frames/ (+ subtitle position)
  series gemini status                                     jobs and returned files waiting in the exchange folder

Reference kinds in a job: "file.jpg" = read from the exchange folder by name; {"previous": "<no>_<frame>"} = a frame
made earlier in the same run (kept in the page). Returned files: <exchange>/<out>/<no>_<frame>.<ext>.
series.json "image": {"gemini_web": {"out_dir": "_out", "job_name": "{no}_job.json", "max_px": 2048, "legacy_keys": false}}
"""
import glob, json, os, subprocess, time

from . import core, images
from .i18n import T


def W():
    return {"out_dir": "_out", "job_name": "{no}_job.json", "max_px": 2048, "legacy_keys": False,
            **core.cfg().get("image", {}).get("gemini_web", {})}


def exchange():
    return core.series_path("exchange")


def out_dir():
    return os.path.join(exchange(), W()["out_dir"])


def _copy(src, name):
    dst = os.path.join(exchange(), name)
    if not (os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src)):
        mp = W()["max_px"]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf",
                        f"scale='min({mp},iw)':'min({mp},ih)':force_original_aspect_ratio=decrease", "-q:v", "3", dst], check=True)
    return name


def prepare(episode, only=None):
    ep = core.episode_dir(episode)
    no = core.episode_no(ep)
    d = core.load_plan(ep)
    fdir = core.ep_path(ep, "frames")
    items = images.frame_items(d)
    if only:
        target = [k for k, _ in items if os.path.splitext(k["file"])[0] in only]
    else:
        target = [k for k, _ in items if not os.path.exists(os.path.join(fdir, k["file"]))]
    in_run = {k["file"] for k in target}
    os.makedirs(exchange(), exist_ok=True)
    default_aspect = core.profile(core.episode_format(ep, d))["aspect"]
    jobs, waiting = [], []
    for k in target:
        refs, missing = [], []
        for r in images.frame_refs(k):
            f = d["set_frame"]["file"] if r == "SET" else r
            if f in in_run and f != k["file"]:
                refs.append({"previous": f"{no}_{os.path.splitext(f)[0]}"})
                continue
            p = images.reference_file(r, ep, d)
            if not os.path.exists(p):
                missing.append(r)
                continue
            base = os.path.splitext(os.path.basename(p))[0]
            refs.append(_copy(p, f"{no}_k_{base}.jpg" if p.startswith(fdir) else f"ref__{base}.jpg"))
        if missing:
            waiting.append({"frame": k["file"], "missing": missing})
            continue
        aspect = k.get("aspect", default_aspect)
        prompt = images.full_prompt(k).replace("Vertical 9:16", "Vertical " + aspect, 1)
        jobs.append({"name": f"{no}_{os.path.splitext(k['file'])[0]}", "aspect": aspect, "refs": refs, "prompt": prompt})
    # order: frames that use a previous frame come after it
    ordered, rest = [], list(jobs)
    while rest:
        done = {j["name"] for j in ordered}
        ok = [j for j in rest if all(not isinstance(r, dict) or r["previous"] in done for r in j["refs"])]
        if not ok:
            waiting += [{"frame": j["name"], "missing": "cycle"} for j in rest]
            break
        ordered += ok
        rest = [j for j in rest if j not in ok]
    job = {"episode": no, "frames": ordered}
    if W()["legacy_keys"]:      # the page helper of the source pipeline reads Turkish keys
        job = {"bolum": no, "kareler": [{"ad": j["name"], "oran": j["aspect"], "prompt": j["prompt"],
                                          "refs": [{"onceki": r["previous"]} if isinstance(r, dict) else r for r in j["refs"]]}
                                         for j in ordered]}
    name = W()["job_name"].format(no=no)
    core.write_json(os.path.join(exchange(), name), job)
    return {"job": name, "frames": [j["name"] for j in ordered], "waiting": waiting}


def returned(no):
    D = out_dir()
    return sorted(f for f in os.listdir(D) if f.startswith(no + "_") and not f.startswith(".")) if os.path.isdir(D) else []


def collect(episode, wait=0, wait_max=170):
    ep = core.episode_dir(episode)
    no = core.episode_no(ep)
    if wait:
        t0 = time.time()
        while len(returned(no)) < wait and time.time() - t0 < wait_max:
            time.sleep(8)
    fdir = core.ep_path(ep, "frames")
    pdir = os.path.join(fdir, core.layout("prompt_dir"))
    os.makedirs(pdir, exist_ok=True)
    d = core.load_plan(ep)
    plan = {os.path.splitext(k["file"])[0]: k for k, _ in images.frame_items(d)}
    out = []
    for f in returned(no):
        name = os.path.splitext(f[len(no) + 1:])[0]
        if name not in plan:
            out.append({"skipped": f})
            continue
        k = plan[name]
        dst = os.path.join(fdir, k["file"])
        if os.path.exists(dst):
            old = os.path.join(fdir, core.layout("old_frames"))
            os.makedirs(old, exist_ok=True)
            os.replace(dst, os.path.join(old, f"{name}_{int(os.path.getmtime(dst))}.jpg"))
        src = os.path.join(out_dir(), f)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-q:v", "2", dst], check=True)
        trash = core.series_path("trash", "gemini_out")
        os.makedirs(trash, exist_ok=True)
        os.replace(src, os.path.join(trash, f))
        open(os.path.join(pdir, k["file"] + ".txt"), "w", encoding="utf-8").write(images.full_prompt(k))
        out.append({"frame": k["file"], "subtitle": images.after_frame_saved(ep, k["file"])})
    return out


def cmd(a):
    if a.op == "prepare":
        r = prepare(a.episode, a.frames.split(",") if a.frames else None)
        core.emit(r, a.json, [T(f"job: {r['job']} · {len(r['frames'])} frames", f"iş: {r['job']} · {len(r['frames'])} kare")]
                  + [T(f"  waiting: {w['frame']} (missing {w['missing']})", f"  bekleyen: {w['frame']} (eksik {w['missing']})") for w in r["waiting"]])
    elif a.op == "collect":
        r = collect(a.episode, a.wait or 0)
        core.emit(r, a.json, [(f"{x['frame']} ← {T('subtitle', 'altyazı')}: {x['subtitle']}" if "frame" in x
                               else T(f"skipped (not in plan): {x['skipped']}", f"atlandı (planda yok): {x['skipped']}")) for x in r]
                  or [T("nothing returned yet", "henüz gelen yok")])
    else:
        jobs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(exchange(), W()["job_name"].format(no="*"))))
        back = sorted(os.listdir(out_dir())) if os.path.isdir(out_dir()) else []
        core.emit({"jobs": jobs, "returned": back}, a.json,
                  [T("jobs: ", "işler: ") + (", ".join(jobs) or "-"), T("returned: ", "gelen: ") + (", ".join(back) or "-")])
    return 0


def add_parser(sp):
    p = sp.add_parser("gemini", help=T("Gemini web adapter: prepare jobs / collect frames", "Gemini web: iş hazırla / kareleri al"))
    p.add_argument("op", choices=["prepare", "collect", "status"]); p.add_argument("episode", nargs="?")
    p.add_argument("--frames"); p.add_argument("--wait", type=int); p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd)
