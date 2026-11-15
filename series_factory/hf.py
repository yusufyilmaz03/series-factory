"""Higgsfield frame adapter (optional). Driven by hand or by an agent through the Higgsfield MCP tools.

Needs:
  - series.json paths.hf_media: JSON file {CODE: higgsfield media id} for character / location references
  - HF_CDN_BASE in <series root>/.env: the CDN prefix your results land on (private, never committed)

  series hf next 013                       next frame's request (medias + prompt), JSON
  series hf wait 013 03_x.jpg JOB [URL]    wait for the result (polls the CDN), download, then print the next request
  series hf drop 013 03_x.jpg              forget a frame (to generate it again)
  series hf batch 013                      every pending frame whose references are ready (for generate_image_batch,
                                         at most 12); set frame first, then the rest = about 2 rounds per episode
  series hf download 013 '[{"file":"03_x.jpg","job":"..","url":".."}, ...]'
                                         after jobs_wait, download all in parallel (no url: poll the CDN)
Frame log: frames/<hf_log> (file -> job id).
"""
import datetime, io, json, os, tempfile, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import core, images
from .i18n import T


def media():
    return core.read_json(core.series_path("hf_media"), {}) or {}


def log_path(ep):
    return core.ep_path(ep, "frames", core.layout("hf_log"))


def log(ep):
    return core.read_json(log_path(ep), {}) or {}


def save_log(ep, k):
    json.dump(k, open(log_path(ep), "w"), indent=2)


def resolve(ref, d, k, M):
    if ref in M:
        return M[ref]
    if ref == "SET":
        ref = d["set_frame"]["file"]
    return k.get(ref)


def nxt(ep):
    d, k, M = core.load_plan(ep), log(ep), media()
    for fr, no in images.frame_items(d):
        if fr["file"] in k:
            continue
        refs = images.frame_refs(fr)
        ids = [resolve(r, d, k, M) for r in refs]
        if None in ids:
            print(json.dumps({"status": "waiting_for_dependency", "file": fr["file"],
                              "missing": [r for r, i in zip(refs, ids) if i is None]}))
            return
        print(json.dumps({"file": fr["file"], "scene": no, "aspect": fr.get("aspect", core.profile()["aspect"]),
                          "medias": ids, "refs": refs, "prompt": images.full_prompt(fr)}, ensure_ascii=False))
        return
    print(json.dumps({"status": "EPISODE_DONE", "frames": len(k)}))


def _exists(u):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, method="HEAD"), timeout=10)
        return r.status == 200
    except Exception:
        return False


def wait(ep, file, job, timeout=150, url=None):
    from PIL import Image
    t0 = time.time()
    found = url
    if not found:
        cdn = core.key("HF_CDN_BASE")
        mark = os.path.join(tempfile.gettempdir(), f"hf_job_{job}")
        if not os.path.exists(mark):
            open(mark, "w").write(str(time.time()))
        now = datetime.datetime.utcfromtimestamp(float(open(mark).read()) + 5)
        cands = [cdn + "hf_" + (now - datetime.timedelta(seconds=s)).strftime("%Y%m%d_%H%M%S") + f"_{job}.png"
                 for s in range(0, 200)]
        with ThreadPoolExecutor(32) as ex:
            while time.time() - t0 < timeout and not found:
                for u, ok in zip(cands, ex.map(_exists, cands)):
                    if ok:
                        found = u
                        break
                if not found:
                    time.sleep(12)
    if not found:
        print(json.dumps({"status": "not_yet", "file": file, "job": job}))
        return False
    data = urllib.request.urlopen(found, timeout=120).read()
    im = Image.open(io.BytesIO(data)).convert("RGB")
    kd = core.ep_path(ep, "frames")
    target = os.path.join(kd, file)
    if os.path.exists(target):
        arc = os.path.join(kd, core.layout("old_frames"))
        os.makedirs(arc, exist_ok=True)
        os.replace(target, os.path.join(arc, f"{len(os.listdir(arc)):02d}_{file}"))
    im.save(target, quality=92)
    k = log(ep)
    k[file] = job
    save_log(ep, k)
    sub = images.after_frame_saved(ep, file)
    print(json.dumps({"downloaded": file, "size": im.size, "sec": int(time.time() - t0), "subtitle": sub}))
    return True


def batch(ep, limit=12):
    d, k, M = core.load_plan(ep), log(ep), media()
    out, waiting = [], []
    for i, (fr, no) in enumerate(images.frame_items(d)):
        if fr["file"] in k:
            continue
        refs = images.frame_refs(fr)
        ids = [resolve(r, d, k, M) for r in refs]
        if None in ids:
            waiting.append(fr["file"])
            continue
        if len(out) < limit:
            out.append({"index": i, "file": fr["file"], "aspect": fr.get("aspect", core.profile()["aspect"]),
                        "medias": ids, "prompt": images.full_prompt(fr)})
    status = "EPISODE_DONE" if not out and not waiting else ("waiting_for_dependency" if not out else "send")
    print(json.dumps({"status": status, "frames": out, "next_round": waiting}, ensure_ascii=False))


def download(ep, items):
    with ThreadPoolExecutor(len(items) or 1) as ex:
        res = list(ex.map(lambda x: wait(ep, x["file"], x["job"], url=x.get("url")), items))
    print(json.dumps({"downloaded": sum(res), "total": len(items)}))


def cmd(a):
    ep = core.episode_dir(a.episode)
    os.makedirs(core.ep_path(ep, "frames"), exist_ok=True)
    if a.op == "drop":
        k = log(ep)
        k.pop(a.args[0], None)
        save_log(ep, k)
        print(T("dropped", "silindi"), a.args[0])
        nxt(ep)
    elif a.op == "batch":
        batch(ep)
    elif a.op == "download":
        download(ep, json.loads(a.args[0]))
        batch(ep)
    elif a.op == "wait":
        if wait(ep, a.args[0], a.args[1], url=(a.args[2] if len(a.args) > 2 else None)):
            nxt(ep)
    else:
        nxt(ep)
    return 0


def add_parser(sp):
    p = sp.add_parser("hf", help=T("Higgsfield frame adapter (optional)", "Higgsfield kare adaptörü (opsiyonel)"))
    p.add_argument("op", choices=["next", "wait", "drop", "batch", "download"])
    p.add_argument("episode"); p.add_argument("args", nargs="*")
    p.set_defaults(func=cmd)
