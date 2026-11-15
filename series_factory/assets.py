"""Asset map (series.json paths.asset_map): the single index of image and sound assets.

id -> path + description, tags, characters. Everything is found here instead of scanning folders.
id = file name without extension.

  series assets list [--type sfx] [--search door] [--character CAT]
  series assets find <id>                     print the path
  series assets check                         in the map but missing on disk / on disk but not in the map
  series assets add <file> --description "..." [--tags a,b] [--characters CAT]
  series assets scan                          add unregistered files from the watched folders (no description)
  series assets import <file> --folder Cat --name cat_waiting --description "..." [--tags ..] [--characters CAT]
      HEIC is converted to JPG (original moved to <trash>/heic_originals); near-duplicates are refused
      (--replace <id> to swap in a better version, --force to add anyway); stored as <references>/<folder>/<name>.<ext>
  series assets prepare-incoming [folder]     live-photo rule: a MOV next to a same-named HEIC/JPG goes to the trash
  series assets similar <file>                only show the duplicate check
  series assets rename <id> <new_name> [--folder Places/Hall]
  series assets heic-convert                  convert every HEIC in the map to JPG

In code:
  assets.find("id") -> absolute path or None
  assets.sound_path("id", "sfx") -> path from the map; otherwise <audio_assets>/sfx/<id>.mp3
  assets.listing("sfx") -> [(id, entry), ...]
  assets.register(id, path, type=..., description=..., ...)
"""
import json, os, shutil, subprocess, sys, unicodedata

from . import core, heic
from .i18n import T
from .migrate import assets_to_v2

FOTO_EXT = (".heic", ".heif", ".jpg", ".jpeg", ".png")
SIMILARITY = 6            # mean pixel difference on a 0-255 scale; below = same picture
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".svg", ".mov", ".mp4")
SOUND_EXT = (".mp3", ".wav", ".m4a", ".ogg")
VIDEO_EXT = (".mov", ".mp4")
SECTIONS = ("images", "sounds")


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def map_path():
    return core.series_path("asset_map")


def _fingerprint_cache():
    return os.path.join(os.path.dirname(map_path()), ".asset_fingerprints.json")


def _trash(*p):
    return core.series_path("trash", *p)


def watched():
    c = core.cfg().get("assets", {})
    refs = core.cfg().get("paths", {}).get("references", core.DEFAULT_PATHS["references"])
    audio = core.cfg().get("paths", {}).get("audio_assets", core.DEFAULT_PATHS["audio_assets"])
    return c.get("watched", [refs, "assets/characters", "assets/backgrounds", audio])


def excluded():
    p = core.cfg().get("paths", {})
    return [p.get("upload_staging", core.DEFAULT_PATHS["upload_staging"]), p.get("incoming", core.DEFAULT_PATHS["incoming"])]


def load():
    if not os.path.exists(map_path()):
        return {"_note": "", "images": {}, "sounds": {}}
    return assets_to_v2(json.load(open(map_path(), encoding="utf-8")))


def save(h):
    for b in SECTIONS:
        h[b] = dict(sorted(h.get(b, {}).items()))
    os.makedirs(os.path.dirname(map_path()), exist_ok=True)
    core.write_json(map_path(), h)


def _all(h=None):
    h = h or load()
    for b in SECTIONS:
        for i, k in h.get(b, {}).items():
            yield b, i, k


def entry(id_, h=None):
    for _, i, k in _all(h):
        if i == id_:
            return k
    return None


def find(id_):
    k = entry(id_)
    if not k:
        return None
    p = core.path(k["path"])
    return p if os.path.exists(p) else None


def sound_path(id_, kind="sfx", folder=None):
    """A sound's file: the map first, then the default layout (target path when it is still to be generated)."""
    p = find(id_)
    if p:
        return p
    base = folder or core.series_path("audio_assets")
    return os.path.join(base, "sfx", id_ + ".mp3") if kind == "sfx" else os.path.join(base, id_ + ".mp3")


def listing(kind=None, search=None, character=None):
    out = []
    for _, i, k in _all():
        if kind and k.get("type") != kind:
            continue
        if character and character.upper() not in k.get("characters", []):
            continue
        if search:
            text = " ".join([i, k.get("description", ""), " ".join(k.get("tags", []))]).lower()
            if search.lower() not in text:
                continue
        out.append((i, k))
    return out


def guess_type(rel_):
    r = rel_.lower()
    name = os.path.basename(r)
    audio = core.cfg().get("paths", {}).get("audio_assets", core.DEFAULT_PATHS["audio_assets"]).lower().rstrip("/") + "/"
    refs = core.cfg().get("paths", {}).get("references", core.DEFAULT_PATHS["references"]).lower().rstrip("/") + "/"
    if r.startswith(audio):
        if "/sfx/" in r:
            return "sfx"
        if "/ses_denemeleri/" in r or "/voice_tests/" in r:
            return "voice_test"
        if name.startswith(("muzik_", "music_")):
            return "music"
        if "anlatim" in name or "narration" in name:
            return "narration"
        return "audio"
    if r.startswith("assets/backgrounds/"):
        return "location_plate"
    if r.startswith("assets/characters/"):
        return "character_preview" if ("onizleme" in name or "preview" in name) else "character_sheet"
    if name.endswith(("_kontakt.jpg", "_contact.jpg")):
        return "contact"
    if r.startswith(refs + "stil/") or r.startswith(refs + "style/"):
        return "style"
    if name.endswith(VIDEO_EXT):
        return "live_photo_video" if ("_canli." in name or "_live." in name) else "video"
    return "photo"


def duration_sec(p):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                           capture_output=True, text=True, timeout=30)
        return round(float(r.stdout.strip()), 2)
    except Exception:
        return None


def register(id_, file, kind=None, **fields):
    """Add or update an asset. file may be absolute or relative to the series root."""
    r = _nfc(os.path.relpath(file, core.root()) if os.path.isabs(file) else file)
    kind = kind or guess_type(r)
    section = "sounds" if r.lower().endswith(SOUND_EXT) else "images"
    h = load()
    k = h.setdefault(section, {}).get(id_, {})
    k.update({"path": r, "type": kind})
    for a, v in fields.items():
        if v not in (None, "", []):
            k[a] = v
    if r.lower().endswith(SOUND_EXT + VIDEO_EXT) and "duration_sec" not in fields:
        s = duration_sec(core.path(r))
        if s:
            k["duration_sec"] = s
    k.setdefault("description", "")
    k.setdefault("tags", [])
    h[section][id_] = k
    save(h)
    return k


def files_on_disk():
    out = []
    ex = excluded()
    for top in watched():
        for d, dirs, fs in os.walk(core.path(top)):
            rd = _nfc(os.path.relpath(d, core.root()))
            if any(rd == x or rd.startswith(x + "/") for x in ex):
                dirs[:] = []
                continue
            for f in fs:
                if f.startswith(".") or not f.lower().endswith(IMAGE_EXT + SOUND_EXT):
                    continue
                out.append(_nfc(os.path.join(rd, f)))
    return sorted(out)


def new_id(rel_, h):
    base = os.path.splitext(os.path.basename(rel_))[0]
    if base not in {i for _, i, _ in _all(h)}:
        return base
    return f"{os.path.basename(os.path.dirname(rel_)).lower()}_{base}"


# ---------------------------------------------------------------- duplicate check
def _compute_print(p):
    """16x16 grey thumbnail (256 bytes). For a video, the frame at 0.5 s."""
    cmd = ["ffmpeg", "-v", "error"]
    if p.lower().endswith(VIDEO_EXT):
        cmd += ["-ss", "0.5"]
    cmd += ["-i", p, "-frames:v", "1", "-vf", "scale=16:16,format=gray", "-f", "rawvideo", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return list(r.stdout) if len(r.stdout) == 256 else None


def fingerprint(p, cache=None):
    k = _nfc(os.path.relpath(p, core.root()))
    mt = int(os.path.getmtime(p))
    if cache is not None and k in cache and cache[k]["mtime"] == mt:
        return bytes.fromhex(cache[k]["print"])
    v = _compute_print(p)
    if v is not None and cache is not None:
        cache[k] = {"mtime": mt, "print": bytes(v).hex()}
    return bytes(v) if v is not None else None


def _rotate(v):
    return bytes(v[(15 - c) * 16 + r] for r in range(16) for c in range(16))


def _diff(a, b):
    best = 999.0
    for _ in range(4):
        best = min(best, sum(abs(x - y) for x, y in zip(a, b)) / 256)
        b = _rotate(b)
    return best


def similar(file, threshold=SIMILARITY):
    """Images in the map that look like this file: [(difference, id, path), ...]"""
    try:
        cache = json.load(open(_fingerprint_cache(), encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    target = bytes(_compute_print(file) or [])
    if not target:
        return []
    out = []
    for i, k in load().get("images", {}).items():
        p = core.path(k["path"])
        if not os.path.exists(p) or k.get("type") in ("contact", "character_sheet", "character_preview"):
            continue
        v = fingerprint(p, cache)
        if v:
            d = _diff(target, v)
            if d <= threshold:
                out.append((round(d, 1), i, k["path"]))
    try:
        json.dump(cache, open(_fingerprint_cache(), "w", encoding="utf-8"))
    except OSError:
        pass
    return sorted(out)


def size(p):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", p], capture_output=True, text=True, timeout=30)
        w, h = r.stdout.strip().split("\n")[0].split(",")[:2]
        return int(w), int(h)
    except Exception:
        return None


def exif_date(p):
    """Capture date YYYY-MM-DD (None if unknown). For HEIC call this BEFORE converting."""
    if shutil.which("identify") and not p.lower().endswith(VIDEO_EXT):
        r = subprocess.run(["identify", "-format", "%[EXIF:DateTimeOriginal]", p + "[0]"], capture_output=True, text=True)
        if r.stdout.strip()[:4].isdigit():
            return r.stdout.strip()[:10].replace(":", "-")
    if shutil.which("mdls"):   # macOS
        r = subprocess.run(["mdls", "-raw", "-name", "kMDItemContentCreationDate", p], capture_output=True, text=True)
        if r.stdout.strip()[:4].isdigit():
            return r.stdout.strip()[:10]
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=creation_time", "-of", "csv=p=0", p],
                           capture_output=True, text=True, timeout=30)
        if r.stdout.strip()[:4].isdigit():
            return r.stdout.strip()[:10]
    except Exception:
        pass
    return None


def _move(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        raise FileExistsError(dst)
    shutil.move(src, dst)


def live_pair(file):
    """A MOV with a same-named photo (HEIC/JPG) in the same folder -> that photo's path; else None."""
    if not file.lower().endswith(VIDEO_EXT):
        return None
    d = os.path.dirname(os.path.abspath(file))
    stem = _nfc(os.path.splitext(os.path.basename(file))[0]).lower()
    for f in os.listdir(d):
        s, u = os.path.splitext(f)
        if _nfc(s).lower() == stem and u.lower() in FOTO_EXT:
            return os.path.join(d, f)
    return None


def prepare_incoming(folder=None):
    d = folder if folder and os.path.isabs(folder) else (core.path(folder) if folder else core.series_path("incoming"))
    n = 0
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        if os.path.isfile(p) and live_pair(p):
            _move(p, _trash("live_photo_videos", f))
            n += 1
    rest = [f for f in sorted(os.listdir(d)) if not f.startswith(".")]
    print(T(f"{n} live-photo videos moved to the trash; {len(rest)} files waiting",
            f"{n} canlı fotoğraf videosu çöp klasörüne taşındı; {len(rest)} dosya işlenmeyi bekliyor"))
    return rest


def import_file(file, folder, name, description="", tags=None, characters=None, kind=None, force=False, replace=None):
    """Take a new photo/video as <references>/<folder>/<name>.<ext> and register it."""
    if not os.path.exists(file):
        raise SystemExit(T(f"file not found: {file}", f"dosya yok: {file}"))
    if live_pair(file) and not force:
        _move(file, _trash("live_photo_videos", os.path.basename(file)))
        raise SystemExit(T("live-photo video (a same-named photo is next to it), moved to the trash; import the photo. "
                           "Use --force to keep the video anyway",
                           "canlı fotoğraf videosu (yanında aynı adlı fotoğraf var), çöp klasörüne taşındı; fotoğrafı içe al. "
                           "Videoyu yine de istiyorsan --force"))
    if not name or name != name.lower() or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in name):
        raise SystemExit(T(f"name may only contain lowercase ASCII letters, digits and _: {name!r}",
                           f"ad yalnızca küçük harf, rakam ve _ içermeli (Türkçe karakter yok): {name!r}"))
    h = load()
    if entry(name, h) and name != replace:
        raise SystemExit(T(f"'{name}' is already in the map; pick another name or use --replace {name}",
                           f"'{name}' id'si haritada zaten var; başka bir ad seç ya da --replace {name} kullan"))
    date = exif_date(file)
    if heic.is_heic(file):
        jpg = heic.convert(file, os.path.join(os.path.dirname(os.path.abspath(file)), name + ".jpg"))
        _move(file, _trash("heic_originals", name + os.path.splitext(file)[1].lower()))
        print("HEIC -> JPG:", os.path.basename(file), "->", name + ".jpg")
        file = jpg
    ext = os.path.splitext(file)[1].lower()
    ext = ".jpg" if ext == ".jpeg" else ext
    if not force:
        b = [x for x in similar(file) if x[1] != replace]
        if b:
            nb = size(file)
            print(T("Similar picture(s) already in the map:", "Benzer kare(ler) zaten haritada:"))
            for d, i, p in b:
                print(f"  {i}  ({T('difference', 'fark')} {d})  {p}  {size(core.path(p))}  <- {T('new file', 'yeni dosya')}: {nb}")
            print(T("Same picture: do not add. Better version: --replace <id>. Different picture: --force",
                    "Aynı kareyse ekleme. Yenisi daha iyiyse: --replace <id>; farklı bir kareyse: --force"))
            raise SystemExit(2)
    if replace:
        old = entry(replace, h)
        if not old:
            raise SystemExit(T(f"--replace: '{replace}' is not in the map", f"--replace: '{replace}' haritada yok"))
        if os.path.exists(core.path(old["path"])):
            _move(core.path(old["path"]), _trash("reference_duplicates", old["path"]))
            print(T("old version moved aside:", "eski sürüm kenara alındı:"), old["path"])
        section = "sounds" if old["path"].lower().endswith(SOUND_EXT) else "images"
        if name != replace:
            h[section].pop(replace, None)
            save(h)
        before = {k: v for k, v in old.items() if k not in ("path", "type", "duration_sec")}
    else:
        before = {}
    r = os.path.join(core.cfg().get("paths", {}).get("references", core.DEFAULT_PATHS["references"]), folder, name + ext)
    _move(file, core.path(r))
    fields = dict(before)
    fields.update({k: v for k, v in dict(description=description, tags=tags or [], characters=characters or [],
                                         date=date).items() if v})
    k = register(name, r, kind, **fields)
    print(T(f"added: {name} -> {r}", f"eklendi: {name} -> {r}"))
    return k


def rename(id_, new_name, folder=None):
    h = load()
    for b in SECTIONS:
        if id_ in h.get(b, {}):
            break
    else:
        raise SystemExit(T(f"'{id_}' is not in the map", f"'{id_}' haritada yok"))
    if entry(new_name, h):
        raise SystemExit(T(f"'{new_name}' already exists", f"'{new_name}' zaten var"))
    k = h[b].pop(id_)
    ext = os.path.splitext(k["path"])[1]
    refs = core.cfg().get("paths", {}).get("references", core.DEFAULT_PATHS["references"])
    d = os.path.join(refs, folder) if folder else os.path.dirname(k["path"])
    r = _nfc(os.path.join(d, new_name + ext))
    _move(core.path(k["path"]), core.path(r))
    k["path"] = r
    h[b][new_name] = k
    save(h)
    print(f"{id_} -> {new_name} ({r})")


def heic_convert_all():
    h = load()
    n = 0
    for b in SECTIONS:
        for i, k in h.get(b, {}).items():
            if not heic.is_heic(k["path"]):
                continue
            src = core.path(k["path"])
            if not k.get("date"):
                k["date"] = exif_date(src)
            jpg = heic.convert(src)
            _move(src, _trash("heic_originals", k["path"]))
            k["path"] = _nfc(os.path.relpath(jpg, core.root()))
            save(h)
            n += 1
            print(T("converted:", "çevrildi:"), i, "->", k["path"])
    print(T(f"{n} HEIC converted; originals in the trash", f"{n} HEIC çevrildi; orijinaller çöp klasöründe"))


# ---------------------------------------------------------------- commands
def _csv(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def cmd(a):
    op = a.op
    if op == "list":
        for i, k in listing(a.type, a.search, a.character):
            tags = f"  [{', '.join(k.get('tags', []))}]" if k.get("tags") else ""
            print(f"{i:45} {k.get('type', ''):17} {k['path']}\n{'':45} {k.get('description', '')}{tags}")
    elif op == "find":
        p = find(a.id)
        if not p:
            sys.exit(T(f"{a.id}: not in the map or file missing", f"{a.id}: haritada yok ya da dosya eksik"))
        print(p)
    elif op == "check":
        h = load()
        known = {_nfc(k["path"]) for _, _, k in _all(h)}
        missing = [(i, k["path"]) for _, i, k in _all(h) if not os.path.exists(core.path(k["path"]))]
        unknown = [f for f in files_on_disk() if f not in known]
        nodesc = [i for _, i, k in _all(h) if not k.get("description")]
        print(T(f"{len(known)} assets in the map", f"haritada {len(known)} varlık"))
        for i, p in missing:
            print(T("  MISSING FILE :", "  EKSİK DOSYA :"), i, "->", p)
        for f in unknown:
            print(T("  UNREGISTERED :", "  KAYITSIZ    :"), f)
        if nodesc:
            print(T("  no description:", "  açıklamasız :"), ", ".join(nodesc))
        inc = core.series_path("incoming")
        if os.path.isdir(inc):
            waiting = [f for f in sorted(os.listdir(inc)) if not f.startswith(".")]
            if waiting:
                print(T(f"  {len(waiting)} files waiting in {core.rel(inc)}/:", f"  {core.rel(inc)}/ içinde işlenmeyi bekleyen {len(waiting)} dosya:"),
                      ", ".join(waiting[:10]), "..." if len(waiting) > 10 else "")
        if not missing and not unknown:
            print(T("ok: map and folders match", "tamam: harita ile klasörler uyumlu"))
        return 1 if missing else 0
    elif op == "add":
        r = os.path.relpath(os.path.abspath(a.file), core.root()) if os.path.exists(a.file) else a.file
        if not os.path.exists(core.path(r)):
            sys.exit(T(f"file not found: {r}", f"dosya yok: {r}"))
        id_ = a.id or new_id(r, load())
        k = register(id_, r, a.type, description=a.description, tags=_csv(a.tags),
                     characters=[x.upper() for x in _csv(a.characters)])
        print(id_, "->", k["path"])
    elif op == "scan":
        h = load()
        known = {_nfc(k["path"]) for _, _, k in _all(h)}
        n = 0
        for f in files_on_disk():
            if f in known:
                continue
            id_ = new_id(f, h)
            register(id_, f)
            h = load()
            n += 1
            print(T("added:", "eklendi:"), id_, "->", f)
        print(T(f"{n} new entries (fill in their descriptions)", f"{n} yeni kayıt (açıklamalarını doldurmayı unutma)"))
    elif op == "import":
        import_file(a.file, a.folder, a.name, a.description, _csv(a.tags), [x.upper() for x in _csv(a.characters)],
                    a.type, a.force, a.replace)
    elif op == "similar":
        b = similar(a.file)
        for d, i, p in b:
            print(f"{i}  ({T('difference', 'fark')} {d})  {p}")
        if not b:
            print(T("no similar picture", "benzer kare yok"))
    elif op == "prepare-incoming":
        prepare_incoming(a.folder)
    elif op == "rename":
        rename(a.id, a.new_name, a.folder)
    elif op == "heic-convert":
        heic_convert_all()
    return 0


def add_parser(sp):
    p = sp.add_parser("assets", help=T("asset map: list, find, check, import", "varlık haritası: liste, bul, kontrol, içe al"))
    s = p.add_subparsers(dest="op", required=True)
    x = s.add_parser("list"); x.add_argument("--type"); x.add_argument("--search"); x.add_argument("--character")
    x = s.add_parser("find"); x.add_argument("id")
    s.add_parser("check"); s.add_parser("scan"); s.add_parser("heic-convert")
    x = s.add_parser("import"); x.add_argument("file"); x.add_argument("--folder", required=True)
    x.add_argument("--name", required=True); x.add_argument("--description", default=""); x.add_argument("--tags")
    x.add_argument("--characters"); x.add_argument("--type"); x.add_argument("--force", action="store_true")
    x.add_argument("--replace")
    x = s.add_parser("similar"); x.add_argument("file")
    x = s.add_parser("prepare-incoming"); x.add_argument("folder", nargs="?")
    x = s.add_parser("rename"); x.add_argument("id"); x.add_argument("new_name"); x.add_argument("--folder")
    x = s.add_parser("add"); x.add_argument("file"); x.add_argument("--id"); x.add_argument("--type")
    x.add_argument("--description", default=""); x.add_argument("--tags"); x.add_argument("--characters")
    p.set_defaults(func=cmd)
