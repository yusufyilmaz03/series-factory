"""Cards: character / location / sound. They copy nothing; every run derives them from the sources
(asset map, series.json, hf media map, episode plans, canon doc, references folder).

  series character CAT        sheet, expression sheet, Higgsfield id, sound signature, reference photos, episodes
  series location LIVING      plate, variants, sketch, Higgsfield id, episodes
  series sound <id|words>     sfx/music: file, description, episodes + similar sounds (look before generating new)
Conventions: character sheets live under .../characters/..., location plates under .../backgrounds/...
"""
import difflib, os, re, sys

from . import assets, canon, catalog, core
from .catalog import ascii_upper, fold, nfc
from .i18n import T, lang

CARD_ROWS = 15
PHOTO_EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
VIDEO_EXT = {".mov", ".mp4"}


def hf_media():
    return core.read_json(core.series_path("hf_media"), {}) or {}


def expr():
    return core.cfg().get("image", {}).get("expression_suffix", "_EXPR")


def file_note(r):
    return "" if r and os.path.exists(core.path(r)) else T("  (FILE MISSING)", "  (DOSYA YOK)")


def write_card(rows):
    if len(rows) > CARD_ROWS:
        rows = rows[:CARD_ROWS - 1] + ["…"]
    print("\n".join(rows))


def resolve(arg, codes, what):
    k = ascii_upper(arg).replace(" ", "_").replace("-", "_")
    if k in codes:
        return k
    near = difflib.get_close_matches(k, sorted(codes), 3, 0.6)
    sys.exit(T(f"{what} not found: {arg}", f"{what} bulunamadı: {arg}") + (T(f" — close: {', '.join(near)}", f" — yakın: {', '.join(near)}") if near else "")
             + T("\ncodes: ", "\nkodlar: ") + ", ".join(sorted(codes)))


def location_codes():
    c = core.cfg()
    return set(c.get("location_descriptions", {})) | {k for k, v in c.get("references", {}).items() if "/backgrounds/" in v}


def character_codes():
    c = core.cfg()
    img = assets.load().get("images", {})
    k = set(c.get("character_descriptions", {})) | {x for v in img.values() for x in v.get("characters", [])} | set(hf_media())
    k |= {x for x, v in c.get("references", {}).items() if "/characters/" in v}
    return {x for x in k - location_codes() if not x.endswith(expr())}


def find_sheet(code, expression, img):
    cand = sorted((i, x) for i, x in img.items() if code in x.get("characters", []) and x.get("type") == "character_sheet"
                  and ("expression_sheet" in x.get("tags", [])) == expression)
    return cand[-1][1]["path"] if cand else ""


def sound_signature(text):
    """Sound signature sfx ids from the character's canon section ('sound signature' section/line or 'sound:' line)."""
    sig = core.cfg().get("cards", {}).get("signature_words") or (["ses imzası", "ses"] if lang() == "tr" else ["sound signature", "sound"])
    head, line_word = sig[0], sig[-1]
    ids, active = [], False
    for s in text.split("\n"):
        if re.match(r"#{2,4} ", s):
            active = bool(re.search(head, s, re.I))
        if active or re.search(rf"{head}|\*\*{line_word}[:*]", s, re.I):
            ids += re.findall(r"`([a-z][a-z0-9_]{2,})`", s)
    return list(dict.fromkeys(ids))


def count_media(folder):
    photo = video = 0
    for _, _, files in os.walk(folder):
        for f in files:
            e = os.path.splitext(f)[1].lower()
            photo += e in PHOTO_EXT
            video += e in VIDEO_EXT
    return photo, video


def reference_row(code, text):
    refs = core.cfg().get("paths", {}).get("references", core.DEFAULT_PATHS["references"])
    top = core.path(refs)
    if not os.path.isdir(top):
        return T(f"{refs}/ missing", f"{refs}/ yok")
    have = {nfc(d): d for d in os.listdir(top) if os.path.isdir(os.path.join(top, d))}
    cand = [nfc(d) for d in re.findall(rf"`{re.escape(refs)}/([^/`]+)/`", text)] + [d for d in have if ascii_upper(d) == code]
    out = []
    for d in dict.fromkeys(cand):
        if d in have:
            p, v = count_media(os.path.join(top, have[d]))
            out.append(f"{refs}/{d}/ — {p} " + T("photos", "foto") + (f", {v} video" if v else ""))
    return " · ".join(out) or T(f"no {refs}/ folder", f"{refs}/ klasörü yok")


def cmd_character(a):
    c = core.cfg()
    ref, hf = c.get("references", {}), hf_media()
    h = assets.load()
    img, snd = h.get("images", {}), h.get("sounds", {})
    code = resolve(" ".join(a.code), character_codes(), T("character", "karakter"))
    cl, ch = canon.sections()
    text = canon.part(code, cl, ch)
    first = text.split("\n")[0] if text else ""
    rows = [re.sub(r"^#+\s*", "", first) if first.startswith("#") else T(f"{code} (no own canon section)", f"{code} (kanonda ayrı bölümü yok)")]

    def sheet(k, expression):
        if k in ref:
            return f"{ref[k]} · {T('approved', 'onaylı')}{file_note(ref[k])}"
        y = find_sheet(code, expression, img)
        return f"{y} · {T('NOT in series.json', 'series.json’da YOK')}{file_note(y)}" if y else T("none", "yok")

    rows.append(T("sheet       ", "sayfa       ") + sheet(code, False))
    rows.append(T("expression  ", "ifade       ") + sheet(code + expr(), True) + (f" · HF {hf[code + expr()]}" if code + expr() in hf else ""))
    rows.append("higgsfield  " + hf.get(code, T("none", "yok")))
    sig = sound_signature(text)
    if sig:
        rows.append(T("signature   ", "ses imzası  ") + " · ".join(
            f"{i} ✓" if i in snd and os.path.exists(core.path(snd[i]["path"]))
            else f"{i} ✗ " + (T("file missing", "dosya yok") if i in snd else T("not in library", "kütüphanede yok")) for i in sig))
    else:
        rows.append(T("signature   not defined in the canon", "ses imzası  kanonda tanımlı değil"))
    rel_ = [i for i, x in snd.items() if x.get("type") == "sfx" and i not in sig
            and (code in x.get("characters", []) or code.lower() in x.get("tags", []))]
    if rel_:
        rows.append(T("related sfx ", "ilgili sfx  ") + ", ".join(rel_[:4]) + (f" (+{len(rel_) - 4})" if len(rel_) > 4 else ""))
    rows.append(T("references  ", "referans    ") + reference_row(code, text))
    u = catalog.usage()
    nos = sorted(set(u["frame"].get(code, [])) | set(u["dialogue"].get(code, [])), key=u["order"].index)
    rows.append(T("episodes    ", "bölümler    ") + catalog.usage_row(nos))
    write_card(rows)
    return 0


def location_file(code, img):
    return core.cfg().get("references", {}).get(code) or (img.get(code.lower()) or {}).get("path") or ""


def cmd_location(a):
    img = assets.load().get("images", {})
    hf, u = hf_media(), catalog.usage()
    codes = location_codes()
    code = resolve(" ".join(a.code), codes, T("location", "mekân"))
    f = location_file(code, img)
    root_ = max((k for k in codes if code.startswith(k + "_")), key=len, default=None)
    rows = [code + (T(f" (variant; root: {root_})", f" (varyant; kök: {root_})") if root_ else "")]
    rows.append(T("plate       ", "arka plan   ") + (f or T("none", "yok")) + file_note(f))
    variants = sorted(k for k in codes if k.startswith(code + "_"))
    for v in variants:
        vf = location_file(v, img)
        rows.append(T("variant     ", "varyant     ") + f"{v} → {vf or T('none', 'yok')}{file_note(vf)}" + (f" · HF {hf[v]}" if v in hf else ""))
    folder = os.path.dirname(f)
    used = {f} | {location_file(v, img) for v in variants}
    other = sorted(i for i, x in img.items() if folder and x.get("type") == "location_plate"
                   and os.path.dirname(x.get("path", "")) == folder and x["path"] not in used)
    if other:
        rows.append(T("other angle ", "diğer açı   ") + ", ".join(other[:5]) + (f" (+{len(other) - 5})" if len(other) > 5 else ""))
    sketches = {i: x for i, x in img.items() if x.get("type") == "sketch"}
    own = sorted(i for i, x in sketches.items() if (folder and os.path.dirname(x["path"]) == folder) or i.startswith(code.lower()))
    general = sorted(i for i, x in sketches.items() if os.path.basename(os.path.dirname(x["path"])) == "plan" and i not in own)
    rows.append(T("sketch      ", "kroki       ") + (", ".join(own) or T("none", "yok")) + (T(f" · general: {', '.join(general)}", f" · genel: {', '.join(general)}") if general else ""))
    rows.append("higgsfield  " + hf.get(code, T("none", "yok")))
    for n, k in enumerate([code] + variants):
        rows.append((T("episodes    ", "bölümler    ") if n == 0 else "            ") + f"{k} {catalog.usage_row(u['frame'].get(k, []))}")
    write_card(rows)
    return 0


def sound_row(i, x, used):
    dur = f" {x['duration_sec']:g} {T('s', 'sn')}" if x.get("duration_sec") else ""
    return f"{i} [{x.get('type', '?')}]{dur} · {catalog.ranges(used) if used else T('unused', 'kullanılmadı')}" + \
        (f" · {x['description'][:60]}" if x.get("description") else "")


def in_canon(i):
    cl, ch = canon.sections()
    out = []
    for n, (start, _, head) in enumerate(ch):
        end = ch[n + 1][0] if n + 1 < len(ch) else len(cl)
        if any(f"`{i}`" in s for s in cl[start:end]):
            out.append(head.split(" — ")[0])
    return out


def similar_sounds(q, snd, kind=None, exclude=(), n=8):
    tok = {t for t in re.split(r"[^a-z0-9]+", fold(q)) if len(t) >= 3 and not t.isdigit()}
    qid = fold(q).replace(" ", "_")
    out = []
    for i, x in snd.items():
        if i in exclude or (kind and x.get("type") != kind):
            continue
        text = fold(x.get("description", "") + " " + " ".join(x.get("tags", [])))
        ratio = difflib.SequenceMatcher(None, qid, fold(i)).ratio()
        p = 2 * len(tok & set(re.split(r"[^a-z0-9]+", fold(i)))) + sum(t in text for t in tok) + (2 if ratio >= 0.6 else 0)
        if p >= 2:
            out.append((p + ratio, i))
    return [i for _, i in sorted(out, reverse=True)[:n]]


def cmd_sound(a):
    snd = assets.load().get("sounds", {})
    u = catalog.usage()["sound"]
    q = " ".join(a.query).strip()
    qid = fold(q).replace(" ", "_")
    if qid in snd:
        x, used = snd[qid], u.get(qid, [])
        print(f"{qid} [{x.get('type')}] {x['path']}{file_note(x['path'])}" + (f" · {x['duration_sec']:g} {T('s', 'sn')}" if x.get("duration_sec") else ""))
        if x.get("description"):
            print("  " + x["description"][:200])
        print(T("  episodes: ", "  bölümler: ") + catalog.usage_row(used) + T("  (from plans)", "  (planlardan)"))
        h = x.get("used_in")
        if h is not None and set(h) != set(used):
            print(T(f"  note: used_in in the map ({','.join(h) or '—'}) disagrees with the plans; plans win",
                    f"  uyarı: haritadaki used_in ({','.join(h) or '—'}) planlarla uyuşmuyor; planlar esas"))
        sim = similar_sounds(qid, snd, x.get("type"), {qid})
        if sim:
            print(T("  similar:", "  benzer adlı:"))
            for i in sim:
                print("    " + sound_row(i, snd[i], u.get(i, [])))
        return 0
    words = [fold(w) for w in q.split()]

    def text(i, x):
        return fold(" ".join([i, x.get("description", ""), " ".join(x.get("tags", [])), x.get("prompt", "")]))

    hit = [i for i, x in snd.items() if all(w in text(i, x) for w in words)]
    planned = [i for i in u if i not in snd and all(w in fold(i) for w in words)]
    partial = False
    if not hit and not planned:
        hit = [i for i, x in snd.items() if any(w in text(i, x) for w in words if len(w) >= 3)]
        partial = bool(hit)
    for i in hit[:15]:
        print(sound_row(i, snd[i], u.get(i, [])))
    if len(hit) > 15:
        print(T(f"… +{len(hit) - 15} more (narrow the words)", f"… +{len(hit) - 15} daha (kelimeyi daralt)"))
    for i in planned:
        print(T(f"{i} [in a plan, not in the map] · {catalog.ranges(u[i])} (to be generated)",
                f"{i} [planda var, haritada yok] · {catalog.ranges(u[i])} (üretilecek)"))
    if partial:
        print(T("(nothing has every word; entries with one of the words)", "(tüm kelimeleri içeren yok; kelimelerden biri geçenler)"))
    if not hit and not planned:
        kn = in_canon(qid)
        if kn:
            print(T(f"{qid}: not in the map but defined in the canon ({', '.join(kn)}); not generated yet",
                    f"{qid}: haritada yok ama kanonda tanımlı ({', '.join(kn)}); henüz üretilmemiş"))
        sim = similar_sounds(q, snd)
        print((T("similar: ", "benzer adlı: ") + ", ".join(sim)) if sim else
              (T("no match — a new sfx can be generated", "eşleşme yok — yeni efekt üretilebilir") if not kn else T("no similar entry", "benzer adlı kayıt yok")))
    return 0


def add_parser(sp):
    p = sp.add_parser("character", help=T("character card", "karakter kartı")); p.add_argument("code", nargs="+")
    p.set_defaults(func=cmd_character)
    p = sp.add_parser("location", help=T("location card", "mekân kartı")); p.add_argument("code", nargs="+")
    p.set_defaults(func=cmd_location)
    p = sp.add_parser("sound", help=T("sfx/music card + similar sounds", "efekt/müzik kartı + benzerleri"))
    p.add_argument("query", nargs="+"); p.set_defaults(func=cmd_sound)
