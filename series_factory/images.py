"""Frames: builds each frame's prompt and references, then hands it to an image adapter.

Adapters (series.json image.adapter):
  gemini      Gemini image API ("Nano Banana"), key GEMINI_API_KEY in <series root>/.env
  manual      no API: writes frames/<guide> with numbered upload folders + ready prompts for a browser tool
  higgsfield  optional, driven through the Higgsfield MCP tools (see `series hf`)
A frame prompt = intro + reference sentences + the frame prompt + style block (series.json image).
References: character sheets, locations (series.json references), SET (= set_frame) or an earlier frame.

  series frames <episode>                        generate missing frames
  series frames <episode> --frame 03_x.jpg --redo   regenerate specific frames
  series frames <episode> --manual               write the browser guide instead of calling an API
  series frames <episode> --place                move finished files from <incoming>/ into the episode
  series frames <episode> --dry-run              what would be generated (count, references), nothing is called
  series frames models                           image models the Gemini key can use
"""
import base64, json, os, subprocess, sys, tempfile

from . import core
from .i18n import T

API = "https://generativelanguage.googleapis.com/v1beta"


def G():
    return core.cfg().get("image", {})


def expr_suffix():
    return G().get("expression_suffix", "_EXPR")


def reference_file(ref, ep, d):
    refs = core.cfg().get("references", {})
    if ref in refs:
        return core.path(refs[ref])
    if ref == "SET":
        return core.ep_path(ep, "frames", d["set_frame"]["file"])
    return core.ep_path(ep, "frames", ref)


def reference_sentence(refs):
    if not refs:
        return ""
    c = core.cfg()
    cd, ld = c.get("character_descriptions", {}), c.get("location_descriptions", {})
    s = []
    for i, r in enumerate(refs, 1):
        if r in cd:
            if r.endswith(expr_suffix()):
                s.append(f"Image {i} is an expression sheet: {cd[r]}.")
            else:
                s.append(f"Image {i} is a character sheet: {cd[r]}; "
                         "keep this character exactly identical to the sheet (markings, colors, proportions, outfit).")
        elif r in ld:
            s.append(f"Image {i} is the set: {ld[r]}. Use this exact place as the location and keep its "
                     "layout, furniture, colors and lighting consistent (the camera angle may change).")
        elif r == "SET":
            s.append(f"Image {i} is the set: use this exact room as the location and keep its layout, "
                     "furniture, colors and lighting consistent.")
        else:
            s.append(f"Image {i} is the previous shot of this scene: keep the same set, character positions, "
                     "camera side and lighting for continuity.")
    return "Use the attached reference images. " + " ".join(s)


def frame_refs(frame):
    """References to upload. With 'edit': the source frame first, then extra references."""
    if frame.get("edit"):
        return [frame["edit"]["source"]] + frame["edit"].get("refs", [])
    return frame.get("refs", [])


def full_prompt(frame):
    if frame.get("edit"):     # an edit on top of an approved frame (room and characters kept exactly)
        return frame["edit"]["prompt"]
    g = G()
    return " ".join(x for x in (g.get("intro", ""), reference_sentence(frame.get("refs", [])),
                                frame["prompt"].strip(), g.get("style", "")) if x)


def shrink(p, tmp, max_px=1536):
    o = os.path.join(tmp, os.path.basename(p) + ".jpg")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", p, "-vf",
                    f"scale='min({max_px},iw)':'min({max_px},ih)':force_original_aspect_ratio=decrease", "-q:v", "3", o],
                   check=True)
    return o


def frame_items(d):
    """[(frame, scene_no)] — the set frame first, then the plan order."""
    out = []
    if d.get("set_frame"):
        out.append(({**d["set_frame"], "refs": d["set_frame"].get("refs", [])}, 0))
    for s in d["scenes"]:
        for k in s["frames"]:
            out.append((k, s["no"]))
    return out


# ---------------------------------------------------------------- manual (browser) flow
def prepare_upload_folder(name, files):
    """<upload_staging>/<name>/ with numbered, downsized copies (old contents moved to the trash)."""
    d = core.series_path("upload_staging", name)
    if os.path.isdir(d):
        for f in os.listdir(d):
            if not f.startswith("."):
                dst = core.series_path("trash", "upload_old", name)
                os.makedirs(dst, exist_ok=True)
                os.replace(os.path.join(d, f), os.path.join(dst, f))
    os.makedirs(d, exist_ok=True)
    out = []
    for i, (pre, f) in enumerate(files, 1):
        n = f"{i:02d}_{pre}{os.path.splitext(os.path.basename(f))[0]}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f, "-vf",
                        "scale='min(2048,iw)':'min(2048,ih)':force_original_aspect_ratio=decrease", "-q:v", "3",
                        os.path.join(d, n)], check=True)
        out.append(n)
    return core.rel(d), out


def write_guide(ep, d, targets):
    no = core.episode_no(ep)
    ready, waiting = [], []
    for k, s_no in targets:
        refs = [reference_file(r, ep, d) for r in frame_refs(k)]
        (waiting if any(not os.path.exists(r) for r in refs) else ready).append((k, s_no, refs))
    aspect = core.profile()["aspect"]
    inc = core.rel(core.series_path("incoming"))
    rows = [T(f"# {no} {d.get('title', '')} — frame guide (browser generation)",
              f"# {no} {d.get('title', '')} — kare rehberi (tarayıcıda üretim)"), "",
            T(f"For each frame: upload the images in the folder **in number order**, set the aspect to {aspect}, paste the prompt "
              f"as is. Save the result with the **Output name** into `{inc}/`. Then: `series frames {no} --place`.",
              f"Her kare için: klasördeki görselleri **numara sırasıyla** yükle, en-boyu {aspect} yap, prompt'u olduğu gibi "
              f"yapıştır. Çıktıyı **Çıktı adı** ile kaydedip `{inc}/` klasörüne at. Sonra: `series frames {no} --place`."), ""]
    for i, (k, s_no, refs) in enumerate(ready, 1):
        folder, names = prepare_upload_folder(f"{no}_{os.path.splitext(k['file'])[0]}", [("", r) for r in refs])
        rows += [f"## {i}) {k['file']}" + (T(f" — scene {s_no}", f" — sahne {s_no}") if s_no else T(" — set", " — mekân")), "",
                 T(f"**Upload (in order, {len(names)} images):** `{folder}/`",
                   f"**Yüklenecek (sırayla, {len(names)} görsel):** `{folder}/`")] + [f"- `{n}`" for n in names]
        rows += ["", T(f"**Aspect:** {aspect}  ·  **Output name:** `{k['file']}`",
                       f"**En-boy:** {aspect}  ·  **Çıktı adı:** `{k['file']}`"), "", "```", full_prompt(k), "```", ""]
    if waiting:
        rows += [T("## Next round", "## Sonraki tur"),
                 T("These frames reference one of the frames above; write the guide again once those are placed:",
                   "Bu kareler yukarıdakilerden birine bakıyor; onlar yerleşince rehberi yeniden çıkaracağım:"), ""]
        rows += [f"- `{k['file']}` ({T('waiting for', 'bekleyen referans')}: "
                 + ", ".join(os.path.basename(r) for r in refs if not os.path.exists(r)) + ")" for k, _, refs in waiting]
    p = core.ep_path(ep, "frames", core.layout("guide"))
    open(p, "w", encoding="utf-8").write("\n".join(rows) + "\n")
    print(T(f"written: {p}  ({len(ready)} frames ready, {len(waiting)} next round)",
            f"yazıldı: {p}  ({len(ready)} kare hazır, {len(waiting)} kare sonraki turda)"))


def place(ep, d):
    """Move frame files (named as in the plan) from <incoming>/ into the episode's frames folder."""
    kd = core.ep_path(ep, "frames")
    expected = {os.path.splitext(k["file"])[0]: k for k, _ in frame_items(d)}
    inc = core.series_path("incoming")
    n = 0
    for f in sorted(os.listdir(inc)) if os.path.isdir(inc) else []:
        name, ext = os.path.splitext(f)
        if name not in expected:
            continue
        k = expected[name]
        out = os.path.join(kd, k["file"])
        if os.path.exists(out):   # old version to the archive
            arc = os.path.join(kd, core.layout("old_frames"))
            os.makedirs(arc, exist_ok=True)
            os.replace(out, os.path.join(arc, f"{name}_{int(os.path.getmtime(out))}.jpg"))
        src = os.path.join(inc, f)
        if ext.lower() in (".jpg", ".jpeg"):
            os.replace(src, out)
        else:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-q:v", "2", out], check=True)
            os.makedirs(core.series_path("trash", "incoming_original"), exist_ok=True)
            os.replace(src, core.series_path("trash", "incoming_original", f))
        os.makedirs(os.path.join(kd, core.layout("prompt_dir")), exist_ok=True)
        open(os.path.join(kd, core.layout("prompt_dir"), k["file"] + ".txt"), "w", encoding="utf-8").write(full_prompt(k))
        after_frame_saved(ep, k["file"])
        print(f"{f} -> {core.layout('frames')}/{k['file']}")
        n += 1
    print(T(f"{n} frames placed.", f"{n} kare yerleştirildi."))


def after_frame_saved(ep, file):
    """Hook for every adapter: decide the subtitle position if the optional extra is available."""
    try:
        from . import subplace
        return subplace.single_frame(ep, file)
    except Exception:
        return None


# ---------------------------------------------------------------- gemini adapter
def gemini_generate(prompt, ref_files, out, model=None, aspect=None):
    g = G()
    model = model or g.get("model")
    tmp = tempfile.mkdtemp()
    parts = [{"inlineData": {"mimeType": "image/jpeg",
                             "data": base64.b64encode(open(shrink(f, tmp), "rb").read()).decode()}} for f in ref_files]
    parts.append({"text": prompt})
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"],
                                 "imageConfig": {"aspectRatio": aspect or core.profile()["aspect"],
                                                 "imageSize": g.get("size", "1K")}}}
    res = core.http("POST", f"{API}/models/{model}:generateContent", {"x-goog-api-key": core.key("GEMINI_API_KEY")},
                    body, timeout=300)
    try:   # usage log (cost tracking)
        import datetime
        with open(core.series_path("image_usage_log"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t": datetime.datetime.now().isoformat(timespec="seconds"), "model": model,
                                 "output": core.rel(out), "refs": len(ref_files),
                                 "usage": res.get("usageMetadata", {})}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    for cand in res.get("candidates", []):
        for p in cand.get("content", {}).get("parts", []):
            if "inlineData" in p:
                raw = os.path.join(tmp, "raw")
                open(raw, "wb").write(base64.b64decode(p["inlineData"]["data"]))
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-q:v", "2", out], check=True)
                return
    why = (res.get("promptFeedback") or {}).get("blockReason") or [c.get("finishReason") for c in res.get("candidates", [])]
    raise RuntimeError(T(f"no image returned ({why})", f"görsel dönmedi ({why})"))


def models():
    res = core.http("GET", f"{API}/models?pageSize=200", {"x-goog-api-key": core.key("GEMINI_API_KEY")})
    for m in res.get("models", []):
        if "image" in m["name"]:
            print(m["name"].split("/")[-1], "-", m.get("displayName", ""))


# ---------------------------------------------------------------- command
def cmd(a):
    if a.episode == "models":
        return models()
    ep = core.episode_dir(a.episode)
    d = core.load_plan(ep)
    kd = core.ep_path(ep, "frames")
    os.makedirs(os.path.join(kd, core.layout("prompt_dir")), exist_ok=True)
    if a.place:
        return place(ep, d)
    targets = []
    for k, no in frame_items(d):
        exists = os.path.exists(os.path.join(kd, k["file"]))
        if a.frame and k["file"] not in a.frame:
            continue
        if exists and not a.redo:
            continue
        targets.append((k, no))
    adapter = G().get("adapter", "gemini")
    if a.dry_run:
        rows = [{"file": k["file"], "scene": no, "refs": frame_refs(k)} for k, no in targets]
        core.emit({"episode": os.path.basename(ep), "adapter": adapter, "to_generate": rows, "count": len(rows)}, a.json, [
            T(f"[dry-run] {os.path.basename(ep)}: {len(rows)} frames to generate with '{adapter}'",
              f"[kuru] {os.path.basename(ep)}: '{adapter}' ile üretilecek {len(rows)} kare")]
            + [f"  {r['file']}  refs: {', '.join(r['refs']) or '-'}" for r in rows])
        return 0
    if not targets:
        print(T("all frames ready:", "tüm kareler hazır:"), kd)
        return 0
    if adapter == "higgsfield" and not a.api:
        print(T(f"image adapter is 'higgsfield': run 'series hf batch {core.episode_no(ep)}' and drive the Higgsfield tools.",
                f"görsel adaptörü 'higgsfield': 'series hf batch {core.episode_no(ep)}' ile Higgsfield araçlarını sür."))
        return 0
    manual = a.manual or (adapter == "manual" and not a.api)
    if manual or not core.key("GEMINI_API_KEY", required=False):
        if not manual:
            print(T("no GEMINI_API_KEY; writing the browser guide.", "GEMINI_API_KEY yok; tarayıcıda üretim için rehber yazılıyor."))
        return write_guide(ep, d, targets)
    errors = 0
    for k, no in targets:
        refs = [reference_file(r, ep, d) for r in frame_refs(k)]
        missing = [r for r in refs if not os.path.exists(r)]
        if missing:
            print(T(f"{k['file']}: reference missing, skipped -> {missing}", f"{k['file']}: referans eksik, atlandı -> {missing}"))
            errors += 1
            continue
        prompt = full_prompt(k)
        out = os.path.join(kd, k["file"])
        try:
            gemini_generate(prompt, refs, out, a.model)
        except RuntimeError as e:
            print(T(f"{k['file']}: ERROR {e}", f"{k['file']}: HATA {e}"))
            errors += 1
            if "404" in str(e):
                sys.exit(T("Model not found. Check the name with 'series frames models' and update series.json image.model.",
                           "Model bulunamadı. 'series frames models' ile adı kontrol edip series.json > image.model'i güncelle."))
            continue
        open(os.path.join(kd, core.layout("prompt_dir"), k["file"] + ".txt"), "w", encoding="utf-8").write(prompt)
        after_frame_saved(ep, k["file"])
        print(T(f"{k['file']}: generated", f"{k['file']}: üretildi"))
    if errors:
        sys.exit(T(f"{errors} frames could not be generated; running again only retries the missing ones.",
                   f"{errors} kare üretilemedi; yeniden çalıştırınca yalnızca eksikler denenir."))
    return 0


def add_parser(sp):
    p = sp.add_parser("frames", help=T("generate episode frames (adapter)", "bölüm karelerini üret (adaptör)"))
    p.add_argument("episode", help=T("episode, or 'models'", "bölüm ya da 'models'"))
    p.add_argument("--frame", action="append"); p.add_argument("--redo", action="store_true")
    p.add_argument("--manual", action="store_true"); p.add_argument("--api", action="store_true")
    p.add_argument("--place", action="store_true"); p.add_argument("--model")
    p.add_argument("--dry-run", action="store_true"); p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd)
