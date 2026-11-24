"""Idea pool: every idea is a record (<records>/<idea>/<CODE>/), grouped by <records>/<idea_group>/.

The status is never typed by hand; it is derived from the episode folders and the publish log:
  waiting        no episode uses it
  in_production  it has an episode, no video yet
  video          its episode(s) have a video
  published      at least one of its episodes is published
  used           no episode of its own but used inside another episode / as a cover
  open_version   used, but its text says another version is "still available" (listed with --status waiting)
The markdown views (series.json docs.generated) are generated from the records with `series docs build`.

  series ideas [--type real,fiction] [--status waiting,in_production,...] [--character CAT] [--sponsor] [--search w]
             [--json [--full]]                 (--ready = --status waiting)
  series idea G-12 [K-14 ...]                    full text + derived status
  series idea-status G-12 "written (episode 027 'Title')"     the Status note inside the idea
  series idea-add --type K --group g08 --title "…" --text "…" [--star]  |  --file new.json  [--dry-run]
  series idea-edit K-43 --old "…" --new "…"  |  --json changes.json  |  --text "…"  [--group g05]
  series idea-group list | add --section "…" --sub "…" --description "…" | edit g08 --description "…"

Series settings (series.json "ideas"):
  "types": {"G": {"name": "real", "label": "real events"}, "K": "fiction", ...}   code prefixes, in sort order
  "labels": {...}  markers used inside idea texts (defaults follow the series language)
"""
import argparse, json, re, sys

from . import catalog, core, store
from .catalog import ascii_upper, nfc
from .i18n import T, lang

STATES = ("waiting", "in_production", "video", "published", "used")
STATE_ALIASES = {"bekliyor": "waiting", "uretimde": "in_production", "yayinda": "published", "kullanildi": "used"}


def state_name(s):
    return {"waiting": T("waiting", "bekliyor"), "in_production": T("in_production", "uretimde"),
            "video": "video", "published": T("published", "yayinda"), "used": T("used", "kullanildi")}.get(s, s)


LABELS = {
    "tr": {"status": "Durum", "what": "Ne oldu", "sponsor": "Sponsor fırsatı", "mini_series": "Mini seri",
           "ready": "hazır", "done_words": ["yazıldı", "yayında", "kullanıldı"], "used_word": "kullanıldı",
           "used_elsewhere": r"[Bb]ölüm \d{3}'(te|de|ta|da) .*kullanıldı|kapak", "cover": "kapak",
           "cover_note": "kapak/profil görseli", "still_open": r"h[âa]l[âa] haz[ıi]r",
           "published_fmt": "yayında (bölüm {eps})", "published_re": r"yayında \(bölüm ([0-9a-z, ]+)\)"},
    "en": {"status": "Status", "what": "What happened", "sponsor": "Sponsor opportunity", "mini_series": "Mini series",
           "ready": "ready", "done_words": ["written", "published", "used"], "used_word": "used",
           "used_elsewhere": r"[Ee]pisode \d{3}\b.*used|cover", "cover": "cover",
           "cover_note": "cover/profile image", "still_open": r"still (?:open|available)",
           "published_fmt": "published (episode {eps})", "published_re": r"published \(episode ([0-9a-z, ]+)\)"},
}


def icfg():
    return core.cfg().get("ideas", {})


def L(k):
    return icfg().get("labels", {}).get(k, LABELS.get(lang(), LABELS["en"])[k])


def types():
    out = {}
    for p, v in icfg().get("types", {}).items():
        out[p] = v if isinstance(v, dict) else {"name": v}
    return out


def code_re():
    t = types()
    return r"(?:%s)-\d+" % "|".join(map(re.escape, t)) if t else r"[A-Z]{1,3}-\d+"


def codes_in(text):
    return re.findall(code_re(), str(text or ""))


def type_of(code):
    t = types()
    p = code.split("-")[0]
    return t.get(p, {}).get("name", p)


def order_key(code):
    t = list(types())
    p, n = code.rsplit("-", 1)
    return (t.index(p) if p in t else len(t), int(n))


def _heading_re():
    return re.compile(r"^###\s+(%s)\s*·\s*(.+?)\s*$" % code_re())


def _item_re():
    return re.compile(r"^-\s+\*\*(%s)\s*·\s*(.+?):?\*\*:?\s*(.*)$" % code_re())


def _status_re():
    return re.compile(r"\s*·?\s*\*\*%s:\*\*\s*(.*)$" % re.escape(L("status")))


# ---------------------------------------------------------------- record store -> markdown
def groups():
    gs = store.all("idea_group")
    first = {}
    for g in gs:
        first[g["section"]] = min(first.get(g["section"], 10 ** 6), g["order"])
    return sorted(gs, key=lambda g: (first[g["section"]], g.get("sub") is not None, g["order"]))


def records():
    return sorted(store.all("idea"), key=lambda o: o["order"])


def pool_md(selected=None, compact=None):
    """Idea markdown from the records. selected: codes to show (None = all); compact: code -> one line."""
    ideas = records()
    by_group = {}
    for o in ideas:
        if selected is None or o["code"] in selected:
            by_group.setdefault(o["group"], []).append(o)
    gs = groups()
    filled = {g["section"] for g in gs if by_group.get(g["id"])}
    out, last = [], None
    for g in gs:
        if g["section"] not in filled:
            continue
        ev = by_group.get(g["id"], [])
        if g["section"] != last:
            if last is not None:
                out += ["---", ""]
            out.append(f"## {g['section']}")
            last = g["section"]
        if g.get("sub"):
            if not ev:
                continue
            out += ([] if out[-1] == "" else [""]) + [f"### {g['sub']}"]
        if g.get("description") and compact is None:
            out.append(g["description"])
        out.append("")
        for o in ev:
            if compact is not None:
                out.append(compact[o["code"]])
            elif o["form"] == "heading":
                out += [o["text"], ""]
            else:
                out.append(o["text"])
        if out[-1] != "":
            out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def parse(text=None):
    lines_ = (text or pool_md()).split("\n")
    H, I, S = _heading_re(), _item_re(), _status_re()
    out, i = [], 0
    while i < len(lines_):
        s = lines_[i]
        m = H.match(s)
        if m:
            j = i + 1
            while j < len(lines_) and not re.match(r"^(#{1,3} |---)", lines_[j]):
                j += 1
            block = lines_[i:j]
            st = next((S.search(x).group(1) for x in block if S.search(x)), "")
            out.append({"code": m.group(1), "title": m.group(2).replace("⭐", "").strip(), "start": i, "end": j,
                        "form": "heading", "status": st})
            i = j
            continue
        m = I.match(s)
        if m:
            dm = S.search(s)
            out.append({"code": m.group(1), "title": m.group(2).replace("⭐", "").strip(), "start": i, "end": i + 1,
                        "form": "item", "status": dm.group(1) if dm else ""})
        i += 1
    return out, lines_


def is_ready(o, used, full=""):
    return o["code"] not in used and not re.match(r"\s*(%s)" % "|".join(map(re.escape, L("done_words"))), o["status"]) \
        and not re.search(L("used_elsewhere"), full)


def idea_episodes():
    """idea code -> [(episode no, stage)] (plan source_idea + production stage of the folder)"""
    k = {}
    for b in catalog.episodes():
        if "plan" not in b:
            continue
        s = catalog.episode_summary(b)
        for code in codes_in(b["plan"].get("source_idea")):
            k.setdefault(code, []).append((s["no"], s["stage"]))
    return k


def used_codes():
    k = {}
    for b in catalog.episodes():
        if "plan" in b:
            for code in codes_in(b["plan"].get("source_idea")):
                k.setdefault(code, []).append(b["folder"][:3])
    return k


def derived():
    from . import canon, publish
    ideas, lines_ = parse()
    ie, pub = idea_episodes(), publish.load()
    published = {no for no, k in pub.items() if any(v.get("status") == "published" for v in k.get("platforms", {}).values())}
    H = _heading_re()
    group, gmap, mini = "", {}, {}
    mini_re = re.compile(r'^\*\*%s:\s*"?(.+?)"?\s*(\(.*?\))?\*\*' % re.escape(L("mini_series")))
    for i, s in enumerate(lines_):
        m = re.match(r"^#{2,3}\s+(.+?)\s*$", s)
        if m and not H.match(s):
            group = m.group(1)
        gmap[i] = group
        m = mini_re.match(s)
        if m:
            for code in codes_in(s):
                mini.setdefault(code, m.group(1))
    out = []
    for o in ideas:
        full = "\n".join(lines_[o["start"]:o["end"]]).strip()
        eps = ie.get(o["code"], [])
        note = re.sub(r"\s+", " ", re.sub(r"`[^`]*`", "", o["status"])).replace("(, ", "(").replace(", )", ")").strip()
        if any(n in published for n, _ in eps):
            st = "published"
        elif eps:
            st = "video" if all(a in ("video", "carousel") for _, a in eps) else "in_production"
        else:
            st = "waiting" if is_ready(o, {}, full) else "used"
        if st == "used" and not note:
            m = re.search(r"([^.()]*%s)" % re.escape(L("used_word")), full)
            note = m.group(1).strip() if m else (L("cover_note") if L("cover") in full else "")
        op = re.search(r"(?:^|[;,)]\s*)([^;]*?)\s+" + L("still_open"), note)
        head = lines_[o["start"]]
        out.append({
            "code": o["code"], "type": type_of(o["code"]), "title": re.sub(r"\s+", " ", o["title"]),
            "star": "⭐" in head, "group": gmap.get(o["start"], ""), "mini_series": mini.get(o["code"]),
            "status": st, "open_version": op.group(1).strip() if op else None,
            "episodes": [{"no": n, "stage": a} for n, a in eps],
            "characters": canon.find_characters(full),
            "related": sorted(set(codes_in(full)) - {o["code"]}, key=order_key),
            "sponsor": bool(re.search(re.escape(L("sponsor")), full)), "note": note, "text": full})
    return out


def row(r):
    eps = r["episodes"]
    if eps:
        d = state_name(r["status"]) + " " + ",".join(e["no"] if e["stage"] in ("video", "carousel") else f"{e['no']}:{catalog.stage_name(e['stage'])}"
                                                     for e in eps)
    elif r["status"] == "used":
        d = state_name("used") + ": " + r["note"][:31]
    else:
        d = state_name(r["status"])
    extra = [x for x in (("⭐" if r["star"] else ""),
                         (T("open: ", "açık: ") + r["open_version"][:30] if r["open_version"] else ""),
                         " ".join(r["characters"]), (T("mini: ", "mini: ") + r["mini_series"] if r["mini_series"] else "")) if x]
    return f"{r['code']:<5} {r['title'][:34]:<35} {d[:44]:<45}{' · '.join(extra)}".rstrip()


def list_arg(valid, aliases=None):
    def f(s):
        v = [(aliases or {}).get(x.strip().lower(), x.strip().lower()) for x in s.split(",") if x.strip()]
        bad = [x for x in v if x not in valid]
        if bad:
            raise argparse.ArgumentTypeError(T(f"invalid: {', '.join(bad)} (choices: {', '.join(valid)})",
                                               f"geçersiz: {', '.join(bad)} (seçenekler: {', '.join(valid)})"))
        return v
    return f


def cmd_list(a):
    want = (a.status or []) + (["waiting"] if a.ready else [])
    sel = []
    for r in derived():
        if a.type and r["type"] not in a.type:
            continue
        if want and r["status"] not in want and not ("waiting" in want and r["open_version"]):
            continue
        if a.character and not all(ascii_upper(k) in r["characters"] for k in a.character):
            continue
        if a.sponsor and not r["sponsor"]:
            continue
        if a.search and nfc(a.search).lower() not in nfc(r["text"]).lower():
            continue
        sel.append(r)
    if a.json:
        print(json.dumps([r if a.full else {k: v for k, v in r.items() if k != "text"} for r in sel], ensure_ascii=False, indent=1))
        return 0
    for r in sel:
        print(row(r))
    cnt = {d: sum(r["status"] == d for r in sel) for d in STATES}
    print(T(f"-- {len(sel)} ideas: ", f"-- {len(sel)} olay: ") + " · ".join(f"{v} {state_name(k)}" for k, v in cnt.items() if v))
    return 0


def cmd_show(a):
    rec = {r["code"]: r for r in derived()}
    for code in a.code:
        r = rec.get(code.upper())
        if not r:
            print(T(f"{code}: missing\n", f"{code}: yok\n"))
            continue
        print(r["text"])
        eps = ",".join(e["no"] + ":" + catalog.stage_name(e["stage"]) for e in r["episodes"])
        print(T("→ derived: ", "→ türetilmiş: ") + state_name(r["status"]) + (" " + eps if eps else "")
              + (T(f" · open version: {r['open_version']}", f" · açık versiyon: {r['open_version']}") if r["open_version"] else "")
              + (T(f" · related: {', '.join(r['related'])}", f" · ilişkili: {', '.join(r['related'])}") if r["related"] else ""))
        print()
    return 0


def find_group(name):
    gs = groups()
    g = next((g for g in gs if g["id"] == name), None)
    if g:
        return g
    s = [g for g in gs if nfc(name).lower() in nfc(g.get("sub") or g["section"]).lower()]
    if len(s) != 1:
        sys.exit(T(f"group '{name}': {len(s)} matches. Groups: ", f"grup '{name}': {len(s)} eşleşme. Gruplar: ") + "; ".join(
            f"{g['id']}={g['section']}" + (f" › {g['sub']}" if g.get("sub") else "") for g in gs))
    return s[0]


def cmd_add(a):
    from . import docs
    if a.file:
        req = json.load(open(a.file, encoding="utf-8"))
    else:
        if not (a.type and a.group and a.title and a.text):
            sys.exit(T("required: --type --group --title --text (or --file list.json)",
                       "gerekli: --type --group --title --text (ya da --file liste.json)"))
        req = [{"type": a.type, "group": a.group, "title": a.title, "text": a.text, "star": a.star}]
    t = types()
    for i in req:
        p = i["type"].upper()
        if p not in t:
            p = next((k for k, v in t.items() if v["name"] == i["type"].lower()), None) or p[0]
        if p not in t:
            sys.exit(T(f"type must be one of {'/'.join(t)}: {i['type']}", f"tip {'/'.join(t)} olmalı: {i['type']}"))
        g = find_group(i["group"])
        have = [int(o["code"].rsplit("-", 1)[1]) for o in records() if o["code"].split("-")[0] == p]
        n = max(have or [0]) + 1
        text = i["text"].strip()
        if f"**{L('status')}:**" not in text:
            text += f" · **{L('status')}:** {L('ready')}"
        if a.dry_run:
            print(f"[{T('dry-run', 'kuru')}] {p}-{n:02d} -> {g['id']}: {i['title']}")
            continue
        order = max([o["order"] for o in records()] or [0]) + 1
        k = store.new_sequential("idea", lambda j: f"{p}-{n + j:02d}", lambda rid: {
            "code": rid, "group": g["id"], "order": order, "form": "item",
            "text": f"- **{rid} · {i['title']}{' ⭐' if i.get('star') else ''}:** {text}"})
        print(T(f"added: {k['code']} · {i['title']} -> {g['id']} ({g.get('sub') or g['section']})",
                f"eklendi: {k['code']} · {i['title']} -> {g['id']} ({g.get('sub') or g['section']})"))
    if not a.dry_run:
        docs.build(quiet=False)
    return 0


def apply_changes(text, a):
    if getattr(a, "text", None) is not None:
        return a.text
    pairs = json.load(open(a.json, encoding="utf-8")) if a.json else [{"old": a.old, "new": a.new}]
    for n, c in enumerate(pairs, 1):
        old, new = c.get("old", c.get("eski")), c.get("new", c.get("yeni"))
        if old is None or new is None:
            sys.exit(T("required: --old and --new (or --json, --text)", "gerekli: --old ve --new (ya da --json, --text)"))
        k = text.count(old)
        if k != 1:
            sys.exit(T(f"change {n}: old text occurs {k} times (must be exactly 1); nothing written",
                       f"değişiklik {n}: eski metin {k} kez geçiyor (tam 1 olmalı); hiçbir şey yazılmadı"))
        text = text.replace(old, new)
    return text


def cmd_edit(a):
    from . import docs
    code = a.code.upper()
    if not store.exists("idea", code):
        sys.exit(T(f"{code}: missing", f"{code}: yok"))
    g = find_group(a.group) if a.group else None

    def f(k):
        if a.old is not None or a.json or a.text is not None:
            k["text"] = apply_changes(k["text"], a)
        if g:
            k["group"] = g["id"]
        return k
    store.update("idea", code, f)
    print(T(f"{code} updated", f"{code} güncellendi"))
    docs.build(quiet=False)
    return 0


def write_status(k, status):
    S = _status_re()
    lines_ = k["text"].split("\n")
    lab = L("status")
    if k["form"] == "item":
        lines_[0] = f"{S.sub('', lines_[0]).rstrip()} · **{lab}:** {status}"
    else:
        for i, s in enumerate(lines_):
            if S.search(s):
                lines_[i] = f"- **{lab}:** {status}"
                break
        else:
            lines_.append(f"- **{lab}:** {status}")
    k["text"] = "\n".join(lines_)
    return k


def set_status(code, status):
    from . import docs
    code = code.upper()
    if not store.exists("idea", code):
        sys.exit(T(f"{code}: missing", f"{code}: yok"))
    store.update("idea", code, lambda k: write_status(k, status))
    print(T(f"{code} status updated", f"{code} durum güncellendi"))
    docs.build(quiet=False)


def cmd_status(a):
    set_status(a.code, a.status)
    return 0


def cmd_group(a):
    from . import docs
    if a.op == "list":
        for g in groups():
            n = sum(o["group"] == g["id"] for o in records())
            print(f"{g['id']}  {g['section']}" + (f" › {g['sub']}" if g.get("sub") else "") + T(f"  ({n} ideas)", f"  ({n} olay)"))
        return 0
    if a.op == "add":
        if not a.section:
            sys.exit(T("required: --section (an existing section name) [--sub] [--description]",
                       "gerekli: --section (varolan bölüm adı) [--sub] [--description]"))
        sec = next((g["section"] for g in groups() if nfc(a.section).lower() in nfc(g["section"]).lower()), a.section)
        order = max([g["order"] for g in groups()] or [0]) + 1
        k = store.new_sequential("idea_group", lambda j: "g%02d" % (order + j), lambda rid: {
            "section": sec, "sub": a.sub, "order": order, "description": a.description or ""})
        print(T("group added: ", "grup eklendi: ") + f"{k['id']} {sec}" + (f" › {a.sub}" if a.sub else ""))
    else:
        g = find_group(a.group)

        def f(k):
            if a.description is not None:
                k["description"] = a.description
            if a.sub:
                k["sub"] = a.sub
            return k
        store.update("idea_group", g["id"], f)
        print(T(f"{g['id']} updated", f"{g['id']} güncellendi"))
    docs.build(quiet=False)
    return 0


# ---------------------------------------------------------------- markdown views
VIEWS = {"ideas": ("waiting",), "in_production": ("in_production",), "done": ("video", "published", "used")}


def summary_sentence(text, n=150):
    s = text.split("\n")
    what = f"- **{L('what')}:**"
    s = next((x for x in s if x.startswith(what)), s[0])
    s = re.sub(r"^-\s+\*\*(?:%s\s*·\s*.+?:|%s:)\*\*\s*" % (code_re(), re.escape(L("what"))), "", s)
    s = re.sub(r"\s*·?\s*\*\*%s:\*\*.*$" % re.escape(L("status")), "", s)
    s = re.sub(r"\s*·\s*\*\*[^*]+:\*\*.*$", "", s)
    s = re.sub(r"[*`]", "", s).strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


def view_texts(names):
    """{file name: md} for the three idea views. names: {"ideas": file, "in_production": file, "done": file}"""
    rec = derived()
    sel = {k: {r["code"] for r in rec if r["status"] in d} for k, d in VIEWS.items()}
    sel["ideas"] = {r["code"] for r in rec if r["status"] == "waiting" or r["open_version"]}
    compact = {}
    for r in rec:
        eps = ", ".join(f"{e['no']} ({catalog.stage_name(e['stage'])})" for e in r["episodes"])
        ex = eps or r["note"] or state_name(r["status"])
        compact[r["code"]] = f"- **{r['code']} · {r['title']}**{' ⭐' if r['star'] else ''} — {ex} · {summary_sentence(r['text'])}"
    legend = " · ".join(f"**{p}-xx** {t.get('label', t['name'])}" for p, t in types().items())
    top = (T("> This file is generated from the idea records with `series docs build`; **do not edit it by hand** "
             "(changes are lost). Add: `series idea-add` · edit: `series idea-edit` · full text: `series idea <code>`.\n"
             "> The status comes from the episode folders: once a script exists an idea moves to the "
             "'in production' file, once its video exists to the 'done' file.\n",
             "> Bu dosya `series docs build` ile olay kayıtlarından üretilir; **elle düzenleme** "
             "(değişiklik kaybolur). Ekle: `series idea-add` · düzelt: `series idea-edit` · tam metin: `series idea <kod>`.\n"
             "> Durum bölüm klasörlerinden türetilir: senaryosu yazılınca olay kendiliğinden 'senaryo' dosyasına, "
             "videosu çıkınca 'tamamlanan' dosyasına geçer.\n")
           + (f"> {legend}\n" if legend else ""))
    titles = {
        "ideas": (T("# Idea pool: ideas (no script yet)", "# Olay Havuzu: Fikirler (senaryosu yazılmamış)"),
                  T(f"> {len(sel['ideas'])} ideas. In production and done: `{names['in_production']}`, `{names['done']}`.\n",
                    f"> {len(sel['ideas'])} olay. Senaryodaki ve tamamlanan olaylar: `{names['in_production']}`, `{names['done']}`.\n")),
        "in_production": (T("# Ideas: scripted (in production)", "# Olaylar: Senaryolaştırılan (üretimde)"),
                          T(f"> {len(sel['in_production'])} ideas. The → line under each idea is the episode no and stage.\n",
                            f"> {len(sel['in_production'])} olay. Her olayın altındaki → satırı bölüm no ve üretim aşamasıdır.\n")),
        "done": (T("# Ideas: done (video ready / published / used elsewhere)",
                   "# Olaylar: Tamamlanan (video hazır / yayında / başka bölümde kullanıldı)"),
                 T(f"> {len(sel['done'])} ideas, one-line summary. Full text and notes: `series idea <code>`.\n",
                   f"> {len(sel['done'])} olay, tek satır özet. Olayın tam metni ve notları: `series idea <kod>`.\n"))}
    prefix = core.cfg().get("docs", {}).get("generated_title_prefix", "")
    by_code = {r["code"]: r for r in rec}
    I = _item_re()
    out = {}
    for k, name in names.items():
        body = pool_md(sel[k], compact if k == "done" else None)
        if k == "in_production":
            rows = []
            for s in body.split("\n"):
                rows.append(s)
                m = I.match(s)
                if m and m.group(1) in by_code:
                    r = by_code[m.group(1)]
                    rows.append("  → " + ", ".join(T(f"episode {e['no']}: ", f"bölüm {e['no']}: ") + catalog.stage_name(e["stage"])
                                                   for e in r["episodes"]))
            body = "\n".join(rows)
        t1, t2 = titles[k]
        if prefix:
            t1 = "# " + prefix + t1[2:]
        out[name] = f"{t1}\n\n{top}{t2}\n---\n\n{body}"
    return out


def add_parser(sp):
    tnames = None

    def tnames_():
        return list(dict.fromkeys([t["name"] for t in types().values()]))
    try:
        tnames = tnames_()
        talias = {p.lower(): t["name"] for p, t in types().items()}
    except SystemExit:
        tnames, talias = [], {}
    p = sp.add_parser("ideas", help=T("list the idea pool (status is derived)", "olay havuzunu listele (durum türetilir)"))
    p.add_argument("--ready", action="store_true"); p.add_argument("--search")
    p.add_argument("--type", type=list_arg(tuple(tnames), talias))
    p.add_argument("--status", type=list_arg(STATES, STATE_ALIASES), help=", ".join(STATES))
    p.add_argument("--character", nargs="+"); p.add_argument("--sponsor", action="store_true")
    p.add_argument("--json", action="store_true"); p.add_argument("--full", action="store_true")
    p.set_defaults(func=cmd_list)
    p = sp.add_parser("idea", help=T("full text of ideas", "olayların tam metni")); p.add_argument("code", nargs="+")
    p.set_defaults(func=cmd_show)
    p = sp.add_parser("idea-status", help=T("set the Status note of an idea", "olayın Durum notunu yaz"))
    p.add_argument("code"); p.add_argument("status"); p.set_defaults(func=cmd_status)
    p = sp.add_parser("idea-add", help=T("add ideas (code is automatic)", "olay ekle (kod otomatik)"))
    p.add_argument("--type"); p.add_argument("--group"); p.add_argument("--title"); p.add_argument("--text")
    p.add_argument("--star", action="store_true"); p.add_argument("--file"); p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_add)
    p = sp.add_parser("idea-edit", help=T("edit an idea's text", "olay metnini düzelt"))
    p.add_argument("code"); p.add_argument("--old"); p.add_argument("--new"); p.add_argument("--json")
    p.add_argument("--text"); p.add_argument("--group"); p.set_defaults(func=cmd_edit)
    p = sp.add_parser("idea-group", help=T("idea groups", "olay grupları"))
    p.add_argument("op", choices=["list", "add", "edit"]); p.add_argument("group", nargs="?")
    p.add_argument("--section"); p.add_argument("--sub"); p.add_argument("--description")
    p.set_defaults(func=cmd_group)
