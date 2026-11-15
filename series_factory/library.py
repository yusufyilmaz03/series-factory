"""Character and location library (series.json paths.library).

  series library list                         entries and their state
  series library generate CAT DOG             character sheet / location set (new version, old ones kept)
  series library generate LIVING --angle reverse   only one angle of a location
  series library approve CAT [--version 2]    write the approved version into series.json as a reference
  series library contact                      one-page overview of every approved reference
Browser generation (no API credit):
  series library guide CAT LIVING [--out guide.md]   prepare upload folders + write prompts and output names
  series library guide LIVING --angle sofa           one angle (or: guide HALL HALL:door)
  series library place                               move results from <incoming>/ into assets, register them

Character: a template (e.g. animal / human) with a style reference, plus real photos from ref_assets / ref_folder.
Location: first the master plate (from photos), then every angle generated looking at the master.
File names: <name>_<library.sheet_suffix>_vN.jpg and <name>_<library.master_suffix>.jpg (series.json "library").
"""
import glob, json, os, re, subprocess, sys

from . import assets, core, images
from .i18n import T
from .migrate import library_to_v2


def lib():
    return library_to_v2(json.load(open(core.series_path("library"), encoding="utf-8")))


def sheet_suffix():
    return core.cfg().get("library", {}).get("sheet_suffix", "character_sheet")


def master_suffix():
    return core.cfg().get("library", {}).get("master_suffix", "master")


def versions(folder, stem):
    out = []
    for f in glob.glob(os.path.join(core.path(folder), f"{stem}_v*.jpg")):
        m = re.search(r"_v(\d+)\.jpg$", f)
        if m:
            out.append((int(m.group(1)), f))
    return sorted(out)


def photos(folder, n=4):
    if not folder or not os.path.isdir(core.path(folder)):
        return []
    fs = sorted(f for f in glob.glob(os.path.join(core.path(folder), "*")) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")))
    return fs[:n]


def ref_photos(rec, folder_field, n):
    ids = rec.get("ref_assets")
    if ids:
        out = []
        for i in ids:
            p = assets.find(i)
            if p:
                out.append(p)
            else:
                print(T(f"  warning: reference asset not found: {i}", f"  uyarı: referans varlık bulunamadı: {i}"))
        return out
    return photos(rec.get(folder_field), n)


def character_plan(code, k, L):
    c = core.cfg()
    t = L["templates"][k["template"]]
    refs = c.get("references", {})
    style = [core.path(refs[r]) if r in refs else core.path(r) for r in k.get("style_refs", t["style_refs"])]
    photo = ref_photos(k, "ref_folder", 4)
    prompt = t["intro"] + k["prompt"]
    if photo:
        a, b = len(style) + 1, len(style) + len(photo)
        prompt += (f" Image{'s' if b > a else ''} {a}{f' to {b}' if b > a else ''} "
                   f"{'are real photos' if b > a else 'is a real photo'} of this exact animal: match its real colors, "
                   "markings, body shape and face, turned into the stylized 3D look.")
    prompt += " " + images.G().get("style", "")
    stem = f"{k['name']}_{sheet_suffix()}"
    n = (versions(k["folder"], stem) or [(0, None)])[-1][0] + 1
    out = os.path.join(core.path(k["folder"]), f"{stem}_v{n}.jpg")
    return {"kind": "character", "prompt": prompt, "style": style, "photo": photo, "out": out, "aspect": t["aspect"]}


def _set_intro():
    return images.G().get("intro", "").replace("cinematic still", "establishing shot of an empty set")


SKETCH = ("Image 1 is a top-down layout sketch of this room (not to scale): follow its furniture placement exactly, "
          "and render the view from the red CAMERA dot in the direction of the red triangle. Do not draw the sketch, "
          "its labels or the red marks in the image.")


def _seq(a, b, one, many):
    return f"Image {a} {one}" if a == b else f"Images {a} to {b} {many}"


def master_plan(code, m):
    sk = [core.path(m["sketch"])] if m.get("sketch") else []
    photo = ref_photos(m, "photo_folder", 6)
    p = f"{_set_intro()} {m['master']} "
    if sk:
        p += SKETCH + " "
    if photo:
        a = len(sk) + 1
        p += (_seq(a, a + len(photo) - 1, "is a photo", "are photos") + " of the real place: keep its furniture, "
              "proportions, materials and colors faithfully, simplified and stylized for the film; ignore any people or animals in them. ")
    p += "No people, no animals. " + images.G().get("style", "")
    out = os.path.join(core.path(m["folder"]), f"{m['name']}_{master_suffix()}.jpg")
    return {"kind": "location", "prompt": p, "style": sk, "photo": photo, "out": out, "aspect": core.profile()["aspect"]}


def angle_plan(code, m, name, pr):
    a = pr if isinstance(pr, dict) else {"prompt": pr}
    master = os.path.join(core.path(m["folder"]), f"{m['name']}_{master_suffix()}.jpg")
    sk = [core.path(a["sketch"])] if a.get("sketch") else []
    mref = [master] if os.path.exists(master) else []
    photo = ref_photos(a, "-", 6) if a.get("ref_assets") else []
    p = f"{_set_intro()} "
    if sk:
        p += SKETCH + " "
    if mref:
        n = len(sk) + 1
        p += (f"Image {n} is the approved master shot of this set ({m['description']}): show the SAME place from the new camera "
              "position, keeping every piece of furniture, every material and color consistent. ")
    p += a["prompt"] + " "
    if photo:
        s = len(sk) + len(mref) + 1
        p += (_seq(s, s + len(photo) - 1, "is a photo", "are photos") + " of the real place from roughly this direction: "
              "keep its furniture and proportions, simplified and stylized; ignore any people or animals in them. ")
    p += "No people, no animals. " + images.G().get("style", "")
    out = os.path.join(core.path(m["folder"]), f"{m['name']}_{name}.jpg")
    return {"kind": "angle", "prompt": p, "style": sk + mref, "photo": photo, "out": out, "aspect": core.profile()["aspect"]}


def plans_for(code, L, angle=None):
    if code in L["characters"]:
        return [character_plan(code, L["characters"][code], L)]
    m = L["locations"][code]
    if angle:
        return [angle_plan(code, m, angle, m["angles"][angle])]
    return [master_plan(code, m)]


def guide_section(no, code, p, L):
    rec = L["characters"].get(code) or L["locations"].get(code)
    head = {"character": T("Character sheet", "Karakter sayfası"), "location": T("Location master", "Mekân ana planı"),
            "angle": T("Location angle", "Mekân açısı")}[p["kind"]]
    fname = rec["name"].capitalize() if p["kind"] == "character" else "Place_" + rec["name"].capitalize()
    if p["kind"] == "angle":
        fname += "_" + os.path.basename(p["out"])[len(rec["name"]) + 1:-4]
    files = [("style_" if p["kind"] == "character" else "", f) for f in p["style"]] + [("", f) for f in p["photo"]]
    folder, names = images.prepare_upload_folder(fname, files)
    out = os.path.basename(p["out"])
    inc = core.rel(core.series_path("incoming"))
    rows = [f"## {no}) {code} — {head}", "", T(f"**Upload (in order, {len(names)} images):** `{folder}/`",
                                                f"**Yüklenecek (sırayla, {len(names)} görsel):** `{folder}/`")]
    for n in names:
        rows.append(f"- `{n}`" + (T("  ← style/layout reference (another character)", "  ← stil/yerleşim referansı (başka bir karakter)")
                                  if n[3:].startswith("style_") and p["kind"] == "character" else ""))
    rows += ["", T(f"**Aspect:** {p['aspect']}  ·  **Output name:** `{out}`  ·  **Then:** put it in `{inc}/`",
                   f"**En-boy:** {p['aspect']}  ·  **Çıktı adı:** `{out}`  ·  **Sonra:** `{inc}/` klasörüne at"), "",
             "```", p["prompt"], "```", ""]
    return "\n".join(rows)


def cmd(a):
    if a.op == "guide":
        L = lib()
        parts = []
        for i, code in enumerate(a.codes, 1):      # CODE or CODE:angle
            code, _, angle = code.partition(":")
            for p in plans_for(code, L, angle or a.angle):
                parts.append(guide_section(i, code, p, L))
        text = "\n".join(parts)
        if a.out:
            open(a.out, "w", encoding="utf-8").write(text)
            print(T("written:", "yazıldı:"), a.out)
        else:
            print(text)
    elif a.op == "place":
        L = lib()
        expected = {}
        for code in list(L["characters"]) + [k for k in L["locations"] if not k.startswith("_")]:
            for p in plans_for(code, L):
                expected[os.path.basename(p["out"])] = (code, p)
            if code in L["locations"]:
                for n in L["locations"][code].get("angles", {}):
                    p = plans_for(code, L, n)[0]
                    expected[os.path.basename(p["out"])] = (code, p)
        inc = core.series_path("incoming")
        n = 0
        for f in sorted(os.listdir(inc)):
            name, ext = os.path.splitext(f)
            if name + ".jpg" not in expected:
                continue
            code, p = expected[name + ".jpg"]
            src = os.path.join(inc, f)
            os.makedirs(os.path.dirname(p["out"]), exist_ok=True)
            if ext.lower() in (".jpg", ".jpeg"):
                os.replace(src, p["out"])
            else:
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-q:v", "2", p["out"]], check=True)
                os.makedirs(core.series_path("trash", "incoming_original"), exist_ok=True)
                os.replace(src, core.series_path("trash", "incoming_original", f))
            open(p["out"][:-4] + "_prompt.txt", "w", encoding="utf-8").write(p["prompt"])
            assets.register(name, p["out"], None, description=f"{code} {p['kind']} ({T('made in the browser', 'tarayıcıda üretildi')})",
                            characters=[code] if p["kind"] == "character" else [], prompt_file=core.rel(p["out"][:-4] + "_prompt.txt"))
            print(f"{f} -> {core.rel(p['out'])}")
            n += 1
        print(T(f"{n} files placed. To approve: series library approve <CODE> [--version N]",
                f"{n} dosya yerleştirildi. Onaylamak için: series library approve <KOD> [--version N]"))
    elif a.op == "generate":
        L = lib()
        if images.G().get("adapter") == "manual" and not a.api:
            sys.exit(T("Image adapter is 'manual' (no API). For the browser guide: series library guide ", "Görsel adaptörü 'manual' (API kullanılmıyor). Tarayıcı rehberi için: series library guide ")
                     + " ".join(a.codes) + T("   (--api to use the API)", "   (API ile üretmek için --api)"))
        for code in a.codes:
            try:
                if code in L["characters"]:
                    p = character_plan(code, L["characters"][code], L)
                    if L["characters"][code].get("ref_folder") and not p["photo"]:
                        print(T(f"{code}: no reference photo; generating from the description only.", f"{code}: referans fotoğraf yok; yalnızca tarifle üretiliyor."))
                    plans = [p]
                elif code in L["locations"]:
                    m = L["locations"][code]
                    os.makedirs(core.path(m["folder"]), exist_ok=True)
                    plans = ([master_plan(code, m)] if not a.angle or a.angle == "master" else []) + \
                        [angle_plan(code, m, n, pr) for n, pr in m.get("angles", {}).items() if not a.angle or a.angle == n]
                else:
                    print(T(f"{code}: not in the library", f"{code}: kütüphanede yok"))
                    continue
                for p in plans:
                    os.makedirs(os.path.dirname(p["out"]), exist_ok=True)
                    images.gemini_generate(p["prompt"], p["style"] + p["photo"], p["out"], aspect=p["aspect"])
                    open(p["out"][:-4] + "_prompt.txt", "w", encoding="utf-8").write(p["prompt"])
                    print(f"{code}: {core.rel(p['out'])}")
            except RuntimeError as e:
                print(T(f"{code}: ERROR {str(e)[:300]}", f"{code}: HATA {str(e)[:300]}"))
    elif a.op == "approve":
        L, c = lib(), core.cfg()
        code = a.code
        if code in L["characters"]:
            k = L["characters"][code]
            sv = dict(versions(k["folder"], f"{k['name']}_{sheet_suffix()}"))
            n = a.version or max(sv)
            c.setdefault("references", {})[code] = core.rel(sv[n])
            c.setdefault("character_descriptions", {})[code] = k["description"]
        else:
            m = L["locations"][code]
            c.setdefault("references", {})[code] = os.path.join(m["folder"], f"{m['name']}_{master_suffix()}.jpg")
            c.setdefault("location_descriptions", {})[code] = m["description"]
            for n in m.get("angles", {}):
                f = os.path.join(m["folder"], f"{m['name']}_{n}.jpg")
                if os.path.exists(core.path(f)):
                    c["references"][f"{code}_{n.upper()}"] = f
                    c["location_descriptions"][f"{code}_{n.upper()}"] = m["description"]
                else:
                    print(T(f"  {code}_{n.upper()}: file missing, waiting", f"  {code}_{n.upper()}: dosya yok, bekliyor"))
        core.save_cfg(c)
        print(T(f"{code} approved -> {c['references'][code]}", f"{code} onaylandı -> {c['references'][code]}"))
    elif a.op == "list":
        L, c = lib(), core.cfg()
        refs = c.get("references", {})
        for code, k in L["characters"].items():
            sv = versions(k["folder"], f"{k['name']}_{sheet_suffix()}")
            print(f"{T('character', 'karakter')} {code:8} {T('approved', 'onaylı')}: {refs.get(code, '-'):60} "
                  f"{T('versions', 'sürümler')}: {[n for n, _ in sv]}")
        for code in L["locations"]:
            if not code.startswith("_"):
                print(f"{T('location', 'mekân')}    {code:8} {T('approved', 'onaylı')}: {refs.get(code, '-')}")
    elif a.op == "contact":
        refs = core.cfg().get("references", {})
        fs = [core.path(p) for p in refs.values() if os.path.exists(core.path(p))]
        out = core.path("assets", "_library_contact.jpg")
        ins = sum([["-i", f] for f in fs], [])
        n = len(fs)
        cols = min(n, 5)
        fl = "".join(f"[{i}]scale=360:480:force_original_aspect_ratio=decrease,pad=360:480:(ow-iw)/2:(oh-ih)/2:color=0xdddddd[v{i}];"
                     for i in range(n))
        lay = "|".join(f"{(i % cols) * 360}_{(i // cols) * 480}" for i in range(n))
        fl += "".join(f"[v{i}]" for i in range(n)) + f"xstack=inputs={n}:layout={lay}:fill=0xdddddd"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", fl, "-frames:v", "1", "-q:v", "3", out], check=True)
        print(out)
    return 0


def add_parser(sp):
    p = sp.add_parser("library", help=T("character sheets and location plates", "karakter sayfaları ve mekân planları"))
    p.add_argument("op", choices=["list", "generate", "approve", "contact", "guide", "place"])
    p.add_argument("codes", nargs="*"); p.add_argument("--angle"); p.add_argument("--api", action="store_true")
    p.add_argument("--version", type=int); p.add_argument("--out")
    p.set_defaults(func=lambda a: cmd(_fix(a)))


def _fix(a):
    a.code = a.codes[0] if a.codes else None
    return a
