"""Episode check: plan validation + style rules (+ timing warnings when the episode is assembled).

  series check 027 [--old] [--json]       --old: reads are not required (older plans)

Built-in style rules (series.json "rules", all optional):
  "emotion_tags": true          every scene's narration has at least one [emotion tag]
  "max_ellipsis": 2             at most this many "..." per scene
  "address_pattern": "regex"    privacy: address-like text (default: Turkish street/apartment patterns for "tr")
  "max_hashtags": 5
  "require_sponsor_slot": false
  "custom": [{"field": "narration" | "dialogue" | "dialogue:CODE" | "hashtags", "pattern": "regex",
              "flags": "i", "message": "..."}]      series-specific rules (per scene for narration/dialogue)
"""
import glob, json, os, re

from . import catalog, core, script
from .core import strip_tags
from .i18n import T, lang

ADDRESS = {
    "tr": r"\b[A-ZÇĞİÖŞÜ][a-zçğıöşü]+ (Caddesi|Cad\.|Sokağı|Sokak|Sk\.|Mahallesi|Mah\.|Apartmanı|Apt\.?)\b"
          r"|\b(daire|kapı) no ?:? ?\d|\bno: ?\d",
    "en": r"\b\d+ [A-Z][a-z]+ (Street|St\.|Avenue|Ave\.|Road|Rd\.|Lane|Ln\.)\b|\b(apt|apartment|flat) ?#? ?\d",
}


def rules():
    return core.cfg().get("rules", {})


def _flags(r):
    return re.I if "i" in r.get("flags", "") else 0


def style_rules(j):
    R = rules()
    custom = R.get("custom", [])
    h = []
    sc = T("scene", "sahne")
    for s in j.get("scenes", []):
        nar = s.get("narration", "")
        for r in custom:
            if r.get("field") == "narration" and re.search(r["pattern"], nar, _flags(r)):
                h.append(f"{sc} {s.get('no')}: {r['message']}")
        if R.get("emotion_tags", True) and nar.strip() and not re.search(r"\[[a-z ]+\]", nar):
            h.append(T(f"{sc} {s.get('no')}: no emotion tag in the narration ([dramatic] etc.)",
                       f"{sc} {s.get('no')}: seslendirmede hiç duygu etiketi yok ([dramatic] vb.)"))
        mx = R.get("max_ellipsis", 2)
        if nar.count("...") > mx:
            h.append(T(f"{sc} {s.get('no')}: too many '...' (use sparingly)", f"{sc} {s.get('no')}: '...' fazla (idareli kullan)"))
        for line in s.get("dialogue", []):
            for r in custom:
                f = r.get("field", "")
                if f == "dialogue" or (f.startswith("dialogue:") and f.split(":", 1)[1] == line.get("character")):
                    if re.search(r["pattern"], line.get("text", ""), _flags(r)):
                        h.append(f"{sc} {s.get('no')}: {r['message']}")
    texts = json.dumps({k: j.get(k) for k in ("scenes", "caption", "closing")}, ensure_ascii=False)
    pat = R.get("address_pattern", ADDRESS.get(lang(), ADDRESS["en"]))
    if pat and re.search(pat, texts):
        h.append(T(f"privacy: address-like text ('{re.search(pat, texts).group(0)}')",
                   f"mahremiyet: adres benzeri ifade var ('{re.search(pat, texts).group(0)}')"))
    tags = j.get("hashtags") or []
    mh = R.get("max_hashtags", 5)
    if mh and len(tags) > mh:
        h.append(T(f"{len(tags)} hashtags (limit {mh})", f"hashtag {len(tags)} tane (sınır {mh})"))
    for r in custom:
        if r.get("field") == "hashtags" and any(re.search(r["pattern"], t, _flags(r)) for t in tags):
            h.append(r["message"])
    if R.get("require_sponsor_slot") and not (j.get("sponsor_slot") or {}).get("description"):
        h.append(T("sponsor_slot is empty", "sponsor_slot boş"))
    return h


def check(e, old=False):
    ep = core.episode_dir(e)
    j = core.load_plan(ep)
    h = [("plan", x) for x in script.validate(j, reads_required=not old)]
    h += [(T("style", "yazım"), x) for x in style_rules(j)]
    words = len(" ".join(strip_tags(s["narration"]) for s in j["scenes"]).split())
    o = catalog.episode_summary({"folder": os.path.basename(ep), "path": ep, "plan": j})
    tj = sorted(glob.glob(core.ep_path(ep, "output", "*" + core.layout("timing_suffix"))), key=os.path.getmtime)
    if tj:
        from . import strips
        _, warn = strips.report(json.load(open(tj[-1])))
        h += [(T("timing", "zamanlama"), x) for x in warn]
    return ep, j, words, o, h


def cmd(a):
    ep, j, words, o, h = check(a.episode, a.old)
    if a.json:
        print(json.dumps({"episode": os.path.basename(ep), "title": j.get("title"), "words": words, "frames": o["frames"],
                          "stage": o["stage"], "duration": o["duration"], "problems": [{"kind": t, "text": x} for t, x in h]},
                         ensure_ascii=False, indent=1))
        return 0
    print(f"{os.path.basename(ep)} — {j.get('title')} · {words} {T('words', 'kelime')} · {T('frames', 'kare')} {o['frames']} · "
          f"{catalog.stage_name(o['stage'])}" + (f" · {o['duration']} {T('s', 'sn')}" if o["duration"] else ""))
    if not h:
        print(T("✓ no problems", "✓ sorun yok"))
    for t, x in h:
        print(f"  [{t}] {x}")
    return 0


def add_parser(sp):
    p = sp.add_parser("check", help=T("plan validation + style rules + timing", "plan doğrulama + yazım kuralları + zamanlama"))
    p.add_argument("episode"); p.add_argument("--old", action="store_true", help=T("reads not required (older plans)", "okumalar zorunlu değil (eski planlar)"))
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd)
