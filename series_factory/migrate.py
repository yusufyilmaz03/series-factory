"""Legacy (Turkish field names) -> current (English) data conversion.

Every converter is idempotent: data that is already in the current shape is returned unchanged, so the
engine can call them on every read. `series migrate` writes the converted files permanently (after a backup).

Covered:
  plan_to_v3        episode plan, script.json "format": 2 -> 3
  settings_to_cfg   pipeline/ayarlar.json -> series.json
  timing_to_v2      montage timing file (<name>_zaman.json) -> English keys
  assets_to_v2      asset map (assets/varliklar.json)
  library_to_v2     character/location library (assets/kutuphane.json)
  publish_to_v2     publish log (yayin/yayin.json)
  record_to_v2      record store entries (kayit/<type>/<id>/<rev>.json)
Folder and file names are not renamed: a migrated series keeps them through series.json "layout" and "paths".
"""
import copy, datetime, glob, json, os, shutil

# ---------------------------------------------------------------- small helpers
MOTION = {"sabit": "static"}
SUB_POS = {"ust": "top", "orta": "middle", "alt": "bottom"}
TRANS = {"kes": "cut"}
SET_REF = {"MEKAN": "SET"}


def _ren(d, m):
    """Rename keys of dict d with map m (unknown keys kept, order kept)."""
    return {m.get(k, k): v for k, v in d.items()}


def _anchor(c):
    return _ren(c, {"sahne": "scene", "kelime": "word", "replik": "line", "kare": "frame"}) if isinstance(c, dict) else c


def _transition(g):
    if isinstance(g, str):
        return TRANS.get(g, g)
    if isinstance(g, dict):
        g = _ren(g, {"tur": "type", "sure": "duration"})
        if "type" in g:
            g["type"] = TRANS.get(g["type"], g["type"])
    return g


def _refs(rs):
    return [SET_REF.get(r, r) for r in rs]


def _edit(e):
    e = _ren(e, {"kaynak": "source", "referanslar": "refs"})
    e["source"] = SET_REF.get(e.get("source"), e.get("source"))
    if "refs" in e:
        e["refs"] = _refs(e["refs"])
    return e


# ---------------------------------------------------------------- plan
def _frame(k):
    k = _ren(k, {"dosya": "file", "hareket": "motion", "referanslar": "refs", "okumalar": "reads", "gecis": "transition",
                 "altyazi": "subtitle_pos", "altyazi_oto": "subtitle_auto", "bekle": "hold", "baslangic": "start_word",
                 "duzenle": "edit", "video_promptu": "video_prompt", "en_boy": "aspect"})
    if "motion" in k:
        k["motion"] = MOTION.get(k["motion"], k["motion"])
    if "subtitle_pos" in k:
        k["subtitle_pos"] = SUB_POS.get(k["subtitle_pos"], k["subtitle_pos"])
    if "transition" in k:
        k["transition"] = _transition(k["transition"])
    if "refs" in k:
        k["refs"] = _refs(k["refs"])
    if "edit" in k:
        k["edit"] = _edit(k["edit"])
    return k


def _scene(s):
    s = _ren(s, {"seslendirme": "narration", "diyalog": "dialogue", "ekran_yazisi": "title_text", "kareler": "frames",
                 "sure_sn": "duration_sec", "ekran_yazilari": "title_steps", "ekran_yazisi_sn": "title_sec",
                 "altyazi": "subtitle_pos"})
    if "subtitle_pos" in s:
        s["subtitle_pos"] = SUB_POS.get(s["subtitle_pos"], s["subtitle_pos"])
    s["dialogue"] = [_ren(r, {"karakter": "character", "metin": "text", "yer": "at"}) for r in s.get("dialogue", [])]
    for r in s["dialogue"]:
        if isinstance(r.get("at"), dict):
            r["at"] = _ren(r["at"], {"kare_basi": "frame_start", "kelime_sonrasi": "after_word"})
    if s.get("title_steps"):
        s["title_steps"] = [_ren(x, {"metin": "text", "capa": "anchor", "kayma": "offset"}) for x in s["title_steps"]]
        for x in s["title_steps"]:
            if "anchor" in x:
                x["anchor"] = _anchor(x["anchor"])
    s["frames"] = [_frame(k) for k in s.get("frames", [])]
    return s


def _sound(e):
    e = _ren(e, {"ad": "id", "capa": "anchor", "kayma": "offset", "ses": "volume", "sure": "duration",
                 "aciklama": "description", "sus": "mute"})
    if "anchor" in e:
        e["anchor"] = _anchor(e["anchor"])
    if e.get("mute"):
        e["mute"] = [dict(_ren(x, {"capa": "anchor", "kayma": "offset"})) for x in e["mute"]]
        for x in e["mute"]:
            x["anchor"] = _anchor(x.get("anchor"))
    return e


def _ambience(o):
    o = _ren(o, {"ad": "id", "ses": "volume", "bas": "start", "son": "end", "bas_kayma": "start_offset",
                 "son_kayma": "end_offset"})
    for k in ("start", "end"):
        if k in o:
            o[k] = _anchor(o[k])
    return o


def _duck(k):
    return _ren(k, {"esik": "threshold", "oran": "ratio", "atak": "attack", "birakma": "release"}) if isinstance(k, dict) else k


SLIDE_TYPES = {"kapak": "cover", "soz": "quote", "ozet": "summary", "madde": "item"}


def carousel_to_v2(k):
    if not isinstance(k, dict) or ("slaytlar" not in k and "ust" not in k):
        return k
    k = _ren(k, {"ust": "kicker", "baslik": "title", "slaytlar": "slides"})
    out = []
    for s in k.get("slides", []):
        s = _ren(s, {"kare": "frame", "tip": "type", "alt": "subtitle", "baslik": "title", "metin": "text",
                     "kirp": "crop", "imza": "signature", "maddeler": "bullets", "uyari": "warning", "son": "footer"})
        if "type" in s:
            s["type"] = SLIDE_TYPES.get(s["type"], s["type"])
        out.append(s)
    k["slides"] = out
    return k


def is_legacy_plan(d):
    return "sahneler" in d or d.get("format") == 2


def plan_to_v3(d):
    if not is_legacy_plan(d):
        return d
    d = _ren(copy.deepcopy(d), {
        "bolum_no": "episode_no", "baslik": "title", "kaynak_olay": "source_idea", "ozet": "summary", "kanca": "hook",
        "sahneler": "scenes", "efektler": "sfx", "tur": "genre", "muzik": "music", "sponsor_yuvasi": "sponsor_slot",
        "kapanis": "closing", "hashtagler": "hashtags", "kanon_guncellemesi": "canon_updates",
        "sure_hedef_sn": "target_sec", "mekan_karesi": "set_frame", "ses": "audio_notes", "kaynaklar": "sources",
        "karusel_notu": "carousel_note", "ortam": "ambience", "karusel": "carousel", "bicim": "format"})
    d["format"] = 3
    d["scenes"] = [_scene(s) for s in d.get("scenes", [])]
    d["sfx"] = [_sound(e) for e in d.get("sfx") or []]
    if isinstance(d.get("music"), dict):
        d["music"] = _sound(d["music"])
        if "kisma" in d["music"]:
            d["music"]["duck"] = _duck(d["music"].pop("kisma"))
    if d.get("ambience"):
        d["ambience"] = [_ambience(o) for o in d["ambience"]]
    if isinstance(d.get("carousel"), dict):
        d["carousel"] = carousel_to_v2(d["carousel"])
    if isinstance(d.get("set_frame"), dict):
        sf = _ren(d["set_frame"], {"dosya": "file", "referanslar": "refs", "duzenle": "edit"})
        if "refs" in sf:
            sf["refs"] = _refs(sf["refs"])
        if "edit" in sf:
            sf["edit"] = _edit(sf["edit"])
        d["set_frame"] = sf
    if isinstance(d.get("sponsor_slot"), dict):
        d["sponsor_slot"] = _ren(d["sponsor_slot"], {"sahne_no": "scene_no", "aciklama": "description"})
    if isinstance(d.get("closing"), dict):
        c = _ren(d["closing"], {"replik": "line", "gercek_goruntu_notu": "real_footage_note", "gercek_video": "real_video"})
        if isinstance(c.get("real_video"), dict):
            c["real_video"] = _ren(c["real_video"], {"dosya": "file", "baslangic": "start", "sure": "duration"})
        d["closing"] = c
    if isinstance(d.get("audio_notes"), dict):
        d["audio_notes"] = _ren(d["audio_notes"], {"anlatim": "narration", "zamanlama": "timing",
                                                   "replikler": "lines", "not": "note"})
    if isinstance(d.get("tts"), dict):
        d["tts"] = _ren(d["tts"], {"hiz": "speed"})
    return d


# ---------------------------------------------------------------- timing file
def timing_to_v2(z):
    if "kareler" not in z:
        return z
    z = _ren(copy.deepcopy(z), {"sure": "duration", "son_karartma": "end_fade", "kareler": "frames"})
    out = []
    for k in z["frames"]:
        k = _ren(k, {"sahne": "scene", "kare": "frame", "hareket": "motion", "soz_sonu": "speech_end", "bekle": "hold",
                     "gecis": "transition", "replik": "lines", "okumalar": "reads"})
        k["motion"] = MOTION.get(k.get("motion"), k.get("motion"))
        if isinstance(k.get("transition"), dict):
            k["transition"] = _transition(k["transition"])
        out.append(k)
    z["frames"] = out
    return z


# ---------------------------------------------------------------- asset map / library / publish log
ASSET_TYPES = {"foto": "photo", "karakter_sayfasi": "character_sheet", "mekan_plani": "location_plate",
               "canli_foto_video": "live_photo_video", "ses_denemesi": "voice_test", "muzik": "music",
               "kroki": "sketch", "kontakt": "contact", "anlatim": "narration", "karakter_onizleme": "character_preview",
               "stil": "style", "ses": "audio"}
ASSET_TAGS = {"ifade_sayfasi": "expression_sheet"}


def assets_to_v2(h):
    if "gorseller" not in h and "sesler" not in h:
        return h
    h = _ren(copy.deepcopy(h), {"_not": "_note", "gorseller": "images", "sesler": "sounds"})
    for b in ("images", "sounds"):
        new = {}
        for i, k in (h.get(b) or {}).items():
            k = _ren(k, {"yol": "path", "tur": "type", "aciklama": "description", "etiketler": "tags", "tarih": "date",
                         "prompt_dosyasi": "prompt_file", "karakterler": "characters", "onayli": "approved",
                         "sure_sn": "duration_sec", "not": "note", "kullanildigi_bolumler": "used_in"})
            k["type"] = ASSET_TYPES.get(k.get("type"), k.get("type"))
            k["tags"] = [ASSET_TAGS.get(t, t) for t in k.get("tags", [])]
            new[i] = k
        h[b] = new
    return h


def library_to_v2(k):
    if "sablonlar" not in k and "karakterler" not in k and "mekanlar" not in k:
        return k
    k = _ren(copy.deepcopy(k), {"_not": "_note", "sablonlar": "templates", "karakterler": "characters",
                                "mekanlar": "locations"})
    k["templates"] = {n: _ren(t, {"en_boy": "aspect", "stil_referansi": "style_refs", "giris": "intro"})
                      for n, t in (k.get("templates") or {}).items()}
    k["characters"] = {n: _ren(c, {"sablon": "template", "klasor": "folder", "ad": "name", "tanim": "description",
                                   "referans_varliklari": "ref_assets", "stil_referansi": "style_refs",
                                   "referans_klasoru": "ref_folder", "konuk": "guest"})
                       for n, c in (k.get("characters") or {}).items()}
    locs = {}
    for n, m in (k.get("locations") or {}).items():
        if not isinstance(m, dict):
            locs[n] = m
            continue
        m = _ren(m, {"klasor": "folder", "ad": "name", "tanim": "description", "ana": "master",
                     "referans_varliklari": "ref_assets", "acilar": "angles", "kroki": "sketch",
                     "fotograflar_klasoru": "photo_folder"})
        if isinstance(m.get("angles"), dict):
            m["angles"] = {a: (_ren(v, {"kroki": "sketch", "referans_varliklari": "ref_assets"}) if isinstance(v, dict) else v)
                           for a, v in m["angles"].items()}
        locs[n] = m
    k["locations"] = locs
    return k


PUBLISH_STATUS = {"planlandi": "scheduled", "yayinda": "published"}


def publish_to_v2(p):
    if "bolumler" not in p:
        return p
    p = _ren(copy.deepcopy(p), {"_not": "_note", "bolumler": "episodes"})
    for no, e in p["episodes"].items():
        e = _ren(e, {"platformlar": "platforms"})
        e["platforms"] = {pl: _ren(v, {"durum": "status", "tarih": "date"}) for pl, v in e.get("platforms", {}).items()}
        for v in e["platforms"].values():
            v["status"] = PUBLISH_STATUS.get(v.get("status"), v.get("status"))
        p["episodes"][no] = e
    return p


# ---------------------------------------------------------------- record store
RECORD_KEYS = {
    "idea": {"kod": "code", "grup": "group", "sira": "order", "bicim": "form", "metin": "text"},
    "idea_group": {"bolum": "section", "alt": "sub", "sira": "order", "aciklama": "description"},
    "todo": {"bolum": "section", "sira": "order", "bitti": "done", "arsiv": "archived", "metin": "text"},
    "todo_section": {"ad": "name", "aciklama": "description"},
}
COMMON_RECORD_KEYS = {"eklendi": "created", "guncellendi": "updated"}
FORMS = {"baslik": "heading", "madde": "item"}


def record_to_v2(kind, r):
    m = {**RECORD_KEYS.get(kind, {}), **COMMON_RECORD_KEYS}
    if not any(k in r for k in m):
        return r
    r = _ren(r, m)
    if "form" in r:
        r["form"] = FORMS.get(r["form"], r["form"])
    return r


# ---------------------------------------------------------------- settings -> series.json
# The layout the source pipeline used. A migrated series keeps these names; new series use the English defaults.
LEGACY_LAYOUT = {
    "plan": "script.json", "script_md": "senaryo.md", "frames": "kareler", "audio": "ses", "output": "cikti",
    "cover": "kapak", "narration": "anlatim", "words": "kelimeler.json", "line": "replik_{n:02d}",
    "timing_suffix": "_zaman.json", "prompt_dir": "_prompt", "prompts_md": "_promptlar.md", "guide": "_rehber.md",
    "contact": "_kontakt.jpg", "hf_log": "_higgsfield.json", "old_frames": "_eski", "prompt_file": "_istem.md",
    "records": {"idea": "olay", "idea_group": "olay_grup", "todo": "todo", "todo_section": "todo_bolum"},
    "docs_sync": ".proje_senkron.json",
}
LEGACY_PATHS = {
    "episodes": "episodes", "docs": "Dokümanlar", "records": "kayit", "audio_assets": "assets/audio",
    "asset_map": "assets/varliklar.json", "library": "assets/kutuphane.json", "references": "Referans",
    "incoming": "Referans/_gelen", "upload_staging": "Referans/Buzzy_Yukleme", "trash": "_to_delete",
    "preview": "_tmp_onizleme", "publish_log": "yayin/yayin.json", "drive_sync": "GoogleDrive",
    "hf_media": "pipeline/hf_medya.json", "image_usage_log": "assets/_gemini_kullanim.jsonl",
}


def settings_to_cfg(a, name=None, lang="tr"):
    """Legacy ayarlar.json dict -> series.json dict (series-specific extras are merged separately)."""
    from . import profiles
    v = a.get("video", {})
    base = profiles.PROFILES["vertical_short"]
    over = {}
    for old, new in (("genislik", "width"), ("yukseklik", "height"), ("fps", "fps")):
        if old in v and v[old] != base[new]:
            over[new] = v[old]
    g = a.get("gorsel", {})
    if g.get("en_boy") and g["en_boy"] != base["aspect"]:
        over["aspect"] = g["en_boy"]
    paths = dict(LEGACY_PATHS)
    y = a.get("yollar", {})
    for old, new in (("bolumler", "episodes"), ("ses_varliklari", "audio_assets"), ("dokumanlar", "docs")):
        if y.get(old):
            paths[new] = y[old]
    tts = _ren(a.get("tts", {}), {"hiz": "speed"})
    tts.setdefault("language_code", lang)
    ntts = {("_note" if k == "_not" else k): x for k, x in a.get("anlatim_tts", {}).items()}
    characters = {}
    for code in a.get("sesler", {}):
        shown = code.capitalize()
        if "Insan" in shown:          # the source pipeline wrote this one name with a dotted capital I
            characters[code] = {"display_name": shown.replace("Insan", "İnsan")}
    c = {
        "schema": 1,
        "name": name or "",
        "lang": lang,
        "profile": "vertical_short",
        "video": {"font": v.get("font", "DejaVu Sans"), "target_lufs": v.get("hedef_lufs", -14),
                  "end_fade": v.get("son_karartma", 0.4)},
        "narrator": a.get("anlatici"),
        "voices": {k: _ren(x, {"ad": "name"}) for k, x in a.get("sesler", {}).items()},
        "tts": tts,
        "narration_tts": ntts,
        "references": a.get("referanslar", {}),
        "character_descriptions": a.get("karakter_tanimlari", {}),
        "location_descriptions": a.get("mekan_tanimlari", {}),
        "characters": characters,
        "image": {"adapter": "manual" if g.get("mod") == "elle" else "gemini", "model": g.get("model"),
                  "size": g.get("boyut", "1K"), "intro": g.get("giris", ""), "style": g.get("stil", ""),
                  "expression_suffix": "_IFADE"},
        "script_writer": dict(a.get("senaryo", {})),
        "library": {"sheet_suffix": "3d_karakter_sayfasi", "master_suffix": "ana"},
        "publish": {"cover_file": "{no}_kapak.jpg"},
        "paths": paths,
        "layout": dict(LEGACY_LAYOUT),
    }
    if over:
        c["profile_overrides"] = over
    return c


def deep_merge(base, extra):
    out = copy.deepcopy(base)
    for k, val in (extra or {}).items():
        if isinstance(val, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], val)
        else:
            out[k] = val
    return out


# ---------------------------------------------------------------- the command
def _find_legacy_settings(root, given=None):
    for p in ([given] if given else []) + [os.path.join(root, "pipeline", "ayarlar.json"), os.path.join(root, "ayarlar.json")]:
        if p and os.path.exists(p):
            return p
    return None


def run(root, given=None, extra=None, name=None, lang="tr", dry=False, settings_only=False, as_json=False):
    """Convert a legacy series folder in place. Returns a summary dict."""
    from .i18n import T, set_lang
    set_lang(lang)
    root = os.path.abspath(root)
    from .core import CONFIG_NAME, config_file
    cfg_path = config_file(root) or os.path.join(root, CONFIG_NAME)
    summary = {"root": root, "series_json": None, "converted": {}, "backup": None, "dry_run": dry}
    if os.path.exists(cfg_path):
        c = json.load(open(cfg_path, encoding="utf-8"))
        summary["series_json"] = "exists"
    else:
        src = _find_legacy_settings(root, given)
        if not src:
            raise SystemExit(T("No series.json and no legacy ayarlar.json found (looked in <root>/pipeline/ and <root>/). "
                               "Pass --from <ayarlar.json>.",
                               "series.json da eski ayarlar.json da bulunamadı (<kök>/pipeline/ ve <kök>/ arandı). "
                               "--from <ayarlar.json> ver."))
        c = settings_to_cfg(json.load(open(src, encoding="utf-8")), name=name or os.path.basename(root), lang=lang)
        summary["series_json"] = "created from " + os.path.relpath(src, root)
    if extra:
        c = deep_merge(c, json.load(open(extra, encoding="utf-8")))
        summary["extra"] = os.path.relpath(os.path.abspath(extra), root)
    paths = {**LEGACY_PATHS, **c.get("paths", {})}
    lay = {**LEGACY_LAYOUT, **c.get("layout", {})}

    todo = []          # (path, converter, kind)
    if not settings_only:
        for f in sorted(glob.glob(os.path.join(root, paths["episodes"], "*", lay["plan"]))):
            todo.append((f, plan_to_v3, "plan"))
        for f in sorted(glob.glob(os.path.join(root, paths["episodes"], "*", lay["output"], "*" + lay["timing_suffix"]))):
            todo.append((f, timing_to_v2, "timing"))
        for key_, fn, kind in (("asset_map", assets_to_v2, "assets"), ("library", library_to_v2, "library"),
                               ("publish_log", publish_to_v2, "publish")):
            p = os.path.join(root, paths[key_])
            if os.path.exists(p):
                todo.append((p, fn, kind))
        recs = lay.get("records", {})
        for kind, folder in recs.items():
            for f in sorted(glob.glob(os.path.join(root, paths["records"], folder, "*", "*.json"))):
                todo.append((f, (lambda k: (lambda r: record_to_v2(k, r)))(kind), "record"))

    changes = []
    for f, fn, kind in todo:
        try:
            old = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError) as e:
            summary.setdefault("errors", []).append(f"{os.path.relpath(f, root)}: {e}")
            continue
        new = fn(old)
        if new != old:
            changes.append((f, new, kind))
    for _, _, kind in changes:
        summary["converted"][kind] = summary["converted"].get(kind, 0) + 1

    if not dry:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        bk = os.path.join(root, paths["trash"], f"migrate_backup_{stamp}")
        if changes:
            for f, _, _ in changes:
                dst = os.path.join(bk, os.path.relpath(f, root))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(f, dst)
            summary["backup"] = os.path.relpath(bk, root)
        for f, new, kind in changes:
            tmp = f + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(new, fh, ensure_ascii=False, indent=1 if kind in ("record", "timing") else 2)
                if kind == "record":
                    fh.write("\n")
            os.replace(tmp, f)
        with open(cfg_path + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(c, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(cfg_path + ".tmp", cfg_path)

    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=1))
    else:
        pre = "[dry-run] " if dry else ""
        print(pre + T("series.json: ", "series.json: ") + str(summary["series_json"]))
        conv = ", ".join(f"{n} {k}" for k, n in summary["converted"].items()) or T("nothing to convert", "çevrilecek dosya yok")
        print(pre + T("converted: ", "çevrilen: ") + conv)
        if summary["backup"]:
            print(T("originals backed up to: ", "orijinallerin yedeği: ") + summary["backup"])
        for e in summary.get("errors", []):
            print(T("could not read: ", "okunamadı: ") + e)
        if os.path.exists(os.path.join(root, "pipeline", ".env")) and not os.path.exists(os.path.join(root, ".env")):
            print(T("note: API keys are now read from <series root>/.env; copy pipeline/.env there.",
                    "not: API anahtarları artık <seri kökü>/.env'den okunur; pipeline/.env dosyasını oraya kopyala."))
    return summary
