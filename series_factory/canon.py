"""Canon (the series character file) and compact script context.

  series canon CAT DOG             only these characters' sections from the canon doc (--list: headings)
  series context G-12 [--character DOG] [--example 021] [--full-narrator]
                                 compact context for writing a script (instead of every doc)

series.json:
  "docs": {"canon": "characters.md"}
  "characters": {"CODE": {"aliases": ["Name", "[Nn]ickname"]}}   regexes that find a character in idea texts
                                 (proper names are matched as written, so adjectives are not taken as names)
  "context": {"always": ["NARRATOR", "HUMAN"], "narrator_strip": "### Looks.*?(?=### Personality)"}
"""
import json, re, sys

from . import catalog, core, docs
from .catalog import ascii_upper, nfc
from .i18n import T


def canon_name():
    return docs.dcfg().get("canon", "characters.md")


def sections():
    lines_ = docs.read(canon_name()).split("\n")
    heads = [(i, len(m.group(1)), m.group(2)) for i, s in enumerate(lines_) if (m := re.match(r"^(#{2,3}) (.+)$", s))]
    return lines_, heads


def part(code, lines_, heads):
    code = ascii_upper(code)
    for n, (i, lvl, h) in enumerate(heads):
        if ascii_upper(h).split(" ")[0].strip("—:-") == code or ascii_upper(h).startswith(code + " "):
            j = next((x[0] for x in heads[n + 1:] if x[1] <= lvl), len(lines_))
            return "\n".join(lines_[i:j]).strip()
    # not a heading: bullet lines that mention the name
    name = code.capitalize()
    rows = [s for s in lines_ if s.startswith("- ") and ascii_upper(s).find(code) != -1]
    return (f"### {name} ({T('bullet lines', 'madde satırları')})\n" + "\n".join(rows)) if rows else ""


def aliases():
    return {k: v["aliases"] for k, v in core.cfg().get("characters", {}).items() if v.get("aliases")}


def find_characters(text):
    m = nfc(text)
    return [k for k, v in aliases().items()
            if re.search(r"(?<!\w)(?:" + "|".join(v) + ")", m) or re.search(r"\b" + k + r"\b", m)]


def cmd_canon(a):
    lines_, heads = sections()
    if a.list or not a.code:
        for i, lvl, h in heads:
            print(("  " if lvl == 3 else "") + h)
        return 0
    for k in a.code:
        print(part(k, lines_, heads) or T(f"{k}: not found in the canon", f"{k}: kanonda bulunamadı"))
        print()
    return 0


def cmd_context(a):
    from . import ideas, script
    pool, lines_ = ideas.parse()
    parts = []
    for code in a.idea:
        o = next((x for x in pool if x["code"] == code.upper()), None)
        if not o:
            sys.exit(T(f"{code}: not in the idea pool", f"{code}: olay havuzunda yok"))
        parts.append("\n".join(lines_[o["start"]:o["end"]]).strip())
    idea_text = "\n\n".join(parts)
    used = ideas.used_codes()
    warn = [k for k in a.idea if k.upper() in used]
    print(T("# Script context:", "# Senaryo bağlamı:"), ", ".join(a.idea))
    if warn:
        print(T("WARNING: already used in a plan:", "UYARI: bu olay(lar) zaten planda kullanılmış:"), {k: used[k.upper()] for k in warn})
    print(T("\n## Idea\n", "\n## Olay\n") + idea_text)

    ctx = core.cfg().get("context", {})
    always = ctx.get("always") or [core.narrator()]
    cl, ch = sections()
    chars = list(always) + [k for k in find_characters(idea_text) + [x.upper() for x in a.character] if k not in always]
    print(T("\n## Canon (relevant characters only)", "\n## Kanon (yalnızca ilgili karakterler)"))
    for k in dict.fromkeys(c for c in chars if c):
        p = part(k, cl, ch)
        if p:
            if k == core.narrator() and not a.full_narrator and ctx.get("narrator_strip"):
                p = re.sub(ctx["narrator_strip"], "", p, flags=re.S)
            print(p + "\n")

    c = core.cfg()
    print(T("## Approved codes", "## Onaylı kodlar"))
    print(T("Character:", "Karakter:"), ", ".join(c.get("character_descriptions", {})))
    print(T("Location:", "Mekân:"), ", ".join(c.get("location_descriptions", {})))
    try:
        sfx, mz = script.sound_library()
        print(T("Sfx library:", "Efekt kütüphanesi:"), "; ".join(x.split(":")[0] for x in sfx))
        print(T("Music library:", "Müzik kütüphanesi:"), "; ".join(x.split(":")[0] for x in mz))
        print(T("\n## Plan format (script.json, format 3)\n", "\n## Plan formatı (script.json, format 3)\n") + script.format_rules().strip())
    except Exception as e:
        print(T("(could not read the format:", "(format okunamadı:"), e, ")")

    print(T("\n## Previous episodes", "\n## Önceki bölümler"))
    print("; ".join(f"{b['folder'][:3]} {b['plan'].get('title')} ({b['plan'].get('source_idea')})"
                    for b in catalog.episodes() if "plan" in b))
    if a.example:
        j = core.load_plan(core.episode_dir(a.example))
        j["scenes"] = j["scenes"][:2]
        for k in ("tts", "canon_updates"):
            j.pop(k, None)
        print(T("\n## Example (first two scenes, for format)\n", "\n## Örnek (ilk iki sahne, biçim için)\n")
              + json.dumps(j, ensure_ascii=False, separators=(",", ":")))
    print(T("\nSave: write script.json -> series script save answer.json (the script md is generated) "
            "-> series check <no> -> series idea-status <code> \"written (episode NNN 'Title')\"",
            "\nKayıt: script.json'u yaz -> series script save cevap.json (senaryo md otomatik üretilir) "
            "-> series check <no> -> series idea-status <kod> \"yazıldı (bölüm NNN 'Başlık')\""))
    return 0


def add_parser(sp):
    p = sp.add_parser("canon", help=T("canon sections of characters", "karakterlerin kanon bölümleri"))
    p.add_argument("code", nargs="*"); p.add_argument("--list", action="store_true")
    p.set_defaults(func=cmd_canon)
    p = sp.add_parser("context", help=T("compact context for writing a script", "senaryo yazmak için kompakt bağlam"))
    p.add_argument("idea", nargs="+"); p.add_argument("--character", nargs="*", default=[])
    p.add_argument("--example"); p.add_argument("--full-narrator", action="store_true")
    p.set_defaults(func=cmd_context)
