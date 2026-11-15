"""Script: writes a new episode plan (script.json, format 3) with the Claude API, validates plans.

The system prompt is assembled from:
  - the series' own writer brief (series.json script_writer.system_prompt or .system_prompt_file),
  - the series documents (series.json docs.script_context: file name prefixes; default: every .md in docs/),
  - the plan format rules (series_factory/templates/script_format.<lang>.md, or script_writer.format_file),
  - the approved character / location codes and the sound library.
The API key lives in <series root>/.env:  ANTHROPIC_API_KEY=...

  series script new [--idea G-05] [--note "..."] [--example 001]     -> episodes/NNN_<slug>/script.json + script md
  series script new ... --manual      no API call: writes the prompt to paste into a Claude chat
  series script new ... --dry-run     show what would be sent (size, token estimate), call nothing
  series script validate 002 [--strict] [--json]
  series script save answer.json      save a plan returned by a chat (manual flow)
"""
import glob, json, os, re, sys

from . import assets, core
from .core import (HOLD_MAX, MOTIONS, READ_SEC, TRANSITIONS, frame_list, narration_text, strip_tags, transition)
from .i18n import T, lang

TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


def _template(name):
    for n in (f"{name}.{lang()}.md", f"{name}.en.md"):
        p = os.path.join(TEMPLATES, n)
        if os.path.exists(p):
            return open(p, encoding="utf-8").read()
    return ""


def format_rules():
    f = core.cfg().get("script_writer", {}).get("format_file")
    if f:
        return open(core.path(f), encoding="utf-8").read()
    return _template("script_format")


def writer_brief():
    sw = core.cfg().get("script_writer", {})
    if sw.get("system_prompt_file"):
        return open(core.path(sw["system_prompt_file"]), encoding="utf-8").read().strip()
    if sw.get("system_prompt"):
        return sw["system_prompt"].strip()
    c = core.cfg()
    return _template("script_system").replace("{series}", c.get("name", "")).replace("{narrator}", c.get("narrator") or "")


def documents():
    d = core.series_path("docs")
    prefixes = core.cfg().get("docs", {}).get("script_context")
    out = []
    files = []
    if prefixes:
        for p in prefixes:
            files += sorted(glob.glob(os.path.join(d, p + "*.md")))
    else:
        files = sorted(glob.glob(os.path.join(d, "*.md")))
    for f in files:
        out.append(f"<document name=\"{os.path.basename(f)}\">\n{open(f, encoding='utf-8').read()}\n</document>")
    return "\n\n".join(out)


def sound_library():
    """Shared sfx and music library: 'id: description' lines."""
    def row(i, k):
        return f"{i}: {k['description']}" if k.get("description") else i
    return [row(i, k) for i, k in assets.listing("sfx")], [row(i, k) for i, k in assets.listing("music")]


def previous_episodes():
    out = []
    base = core.episodes_dir()
    os.makedirs(base, exist_ok=True)
    for d in sorted(os.listdir(base)):
        p = os.path.join(base, d, core.layout("plan"))
        if os.path.exists(p):
            j = core.load_plan(os.path.join(base, d))
            out.append((j.get("episode_no"), j.get("title"), j.get("source_idea"), d))
    return out


def code_library():
    c = core.cfg()
    k = "\n".join(f"- {code}: {t}" for code, t in c.get("character_descriptions", {}).items())
    m = "\n".join(f"- {code}: {t}" for code, t in c.get("location_descriptions", {}).items())
    return (T("## Approved character codes\n", "## Onaylı karakter kodları\n") + k + "\n\n"
            + T("## Location library\n", "## Mekân kütüphanesi\n") + m + "\n")


def build_prompt(a):
    sfx, mz = sound_library()
    prev = previous_episodes()
    example = core.load_plan(core.episode_dir(a.example)) if a.example else None
    if example:
        example.pop("audio_notes", None)
    system = (writer_brief() + "\n\n" + T("The series documents follow:\n\n", "Aşağıda serinin dokümanları var:\n\n")
              + documents() + "\n\n" + format_rules() + "\n" + code_library())
    req = [T("Write a new episode plan and send it with the save_episode tool.",
             "Yeni bir bölüm planı yaz ve save_episode aracıyla gönder.")]
    req.append(T(f"Episode no: {a.episode_no}.", f"Bölüm no: {a.episode_no}."))
    if a.idea:
        req.append(T(f"Source idea: {a.idea} (stay true to its description in the idea pool).",
                     f"Kaynak olay: {a.idea} (olay havuzundaki tanımına sadık kal)."))
    else:
        used = ", ".join(o[2] for o in prev if o[2]) or T("none", "yok")
        req.append(T(f"Pick the source idea from the idea pool yourself; already used: {used}.",
                     f"Kaynak olayı olay havuzundan sen seç; daha önce kullanılanlar: {used}."))
    if a.note:
        req.append(T("Note from the author: ", "Yazarın notu: ") + a.note)
    req.append(T("Previous episodes: ", "Önceki bölümler: ")
               + ("; ".join(f"{o[0]} {o[1]} ({o[2]})" for o in prev) or T("none", "yok")))
    req.append(T("Library sound effects (write only the id in sfx[].id; do not generate a new one if one fits): ",
                 "Kütüphanedeki efektler (sfx[].id alanına yalnızca id yaz; uygun olan varsa yenisini üretme): ")
               + ("; ".join(sfx) or T("none", "yok")))
    req.append(T("Library music: ", "Kütüphanedeki müzikler: ") + ("; ".join(mz) or T("none", "yok")))
    if example:
        req.append(T("Example episode (for format and tone; do not repeat its content):\n```json\n",
                     "Örnek bölüm (biçim ve ton için; içeriğini tekrar etme):\n```json\n")
                   + json.dumps(example, ensure_ascii=False, indent=1) + "\n```")
    return system, "\n".join(req)


def word_limits(d):
    """(min, max, target text) for this plan: idea type override (series.json ideas.types.<P>.words) or profile."""
    p = core.profile()["words"]
    src = str(d.get("source_idea") or "")
    for prefix, t in core.cfg().get("ideas", {}).get("types", {}).items():
        if isinstance(t, dict) and t.get("words") and src.startswith(prefix + "-"):
            w = t["words"]
            return w["min"], w["max"], w.get("target", "")
    return p["min"], p["max"], p["target"]


def validate(d, reads_required=False):
    """List plan problems (empty list = fine). reads_required: every frame needs reads (new plans)."""
    c = core.cfg()
    h = []
    codes = set(c.get("references", {})) | {"SET"}
    narr = " ".join(strip_tags(s["narration"]) for s in d.get("scenes", []))
    words = narr.split()
    if any(ch.isdigit() for ch in narr):
        h.append(T("narration contains digits (write numbers as words)", "seslendirmede rakam var (yazıyla yaz)"))
    lo, hi, target = word_limits(d)
    if not lo <= len(words) <= hi:
        h.append(T(f"narration {len(words)} words (target {target})", f"anlatım {len(words)} kelime (hedef {target})"))
    sf = (d.get("set_frame") or {}).get("file")
    all_refs = [r for s in d.get("scenes", []) for k in s.get("frames", []) for r in k.get("refs", [])]
    if "SET" in all_refs and not sf:
        h.append(T("SET used but there is no set_frame", "SET kullanılmış ama set_frame yok"))
    if not any(r in c.get("location_descriptions", {}) or r == "SET" for r in all_refs):
        h.append(T("no frame references a location (library code or SET)",
                   "hiçbir karede mekân referansı yok (kütüphane kodu ya da SET)"))
    seen = {sf}
    line_n = 0
    for s in d.get("scenes", []):
        sk = strip_tags(s["narration"]).split()
        if not s.get("frames"):
            h.append(T(f"scene {s.get('no')}: no frames", f"sahne {s.get('no')}: kare yok"))
        for i, k in enumerate(s.get("frames", [])):
            if k.get("motion", "in") not in MOTIONS:
                h.append(T(f"{k['file']}: unknown motion {k.get('motion')}", f"{k['file']}: bilinmeyen hareket {k.get('motion')}"))
            for r in k.get("refs", []):
                if r not in codes and r not in seen:
                    h.append(T(f"{k['file']}: reference '{r}' undefined or comes later",
                               f"{k['file']}: referans '{r}' tanımsız ya da sonra geliyor"))
            if i > 0 and k.get("start_word") not in sk:
                h.append(T(f"{k['file']}: start_word '{k.get('start_word')}' not in scene {s['no']} narration",
                           f"{k['file']}: start_word '{k.get('start_word')}' sahne {s['no']} seslendirmesinde yok"))
            if k["file"] in seen:
                h.append(T(f"{k['file']}: file name repeats", f"{k['file']}: dosya adı tekrar ediyor"))
            seen.add(k["file"])
        for r in s.get("dialogue", []):
            line_n += 1
            y = r.get("at") or {}
            if r.get("character") not in c.get("voices", {}):
                h.append(T(f"line {line_n}: no voice defined for '{r.get('character')}'",
                           f"replik {line_n}: '{r.get('character')}' için ses tanımlı değil"))
            if "frame_start" in y and y["frame_start"] not in [k["file"] for k in s["frames"]]:
                h.append(T(f"line {line_n}: frame_start '{y['frame_start']}' is not in this scene",
                           f"replik {line_n}: frame_start '{y['frame_start']}' bu sahnede yok"))
            if "after_word" in y and y["after_word"] not in sk[:-1]:
                h.append(T(f"line {line_n}: after_word '{y['after_word']}' missing in scene {s['no']} or is the last word",
                           f"replik {line_n}: after_word '{y['after_word']}' sahne {s['no']}'de yok ya da son kelime"))
    try:
        fl = frame_list(d)
    except Exception:
        fl = []
    for k in fl:
        fr, f = k["frame"], k["file"]
        typ, sec = transition(fr, k["scene_start"], k["first"])
        if typ not in TRANSITIONS:
            h.append(T(f"{f}: unknown transition '{typ}'", f"{f}: bilinmeyen geçiş '{typ}'"))
        elif typ != "cut" and not 0.15 <= sec <= 0.8:
            h.append(T(f"{f}: transition duration {sec} (0.15–0.8)", f"{f}: geçiş süresi {sec} (0.15–0.8)"))
        if not 0 <= k["hold"] <= HOLD_MAX:
            h.append(T(f"{f}: hold {k['hold']} (0–{HOLD_MAX})", f"{f}: bekle {k['hold']} (0–{HOLD_MAX})"))
        if reads_required and not k["reads"]:
            h.append(T(f"{f}: no reads", f"{f}: okumalar yok"))
        if k["reads"] and len(k["reads"]) * READ_SEC > k["est_sec"] + 0.05:
            h.append(T(f"{f}: {len(k['reads'])} reads do not fit in ~{k['est_sec']:.1f} s "
                       f"({READ_SEC} s per read; split the frame, drop a read or add hold)",
                       f"{f}: {len(k['reads'])} okuma ~{k['est_sec']:.1f} sn'ye sığmıyor "
                       f"(okuma başına {READ_SEC} sn; kareyi böl, okuma at ya da bekle ekle)"))
        if fr.get("motion") == "static" and k["est_sec"] > 2.0:
            h.append(T(f"{f}: 'static' frame ~{k['est_sec']:.1f} s (frames longer than 2 s must move)",
                       f"{f}: 'static' kare ~{k['est_sec']:.1f} sn (2 sn'den uzun kare hareket etmeli)"))
    if reads_required and fl and fl[-1]["hold"] < 0.8:
        h.append(T(f"{fl[-1]['file']}: the last frame needs hold ≥ 0.8 (let the ending land)",
                   f"{fl[-1]['file']}: son karede bekle ≥ 0.8 olmalı (kapanış otursun)"))
    scene_nos = {s["no"] for s in d.get("scenes", [])}

    def check_anchor(a_, what):
        if "scene" in a_ and a_["scene"] not in scene_nos:
            h.append(T(f"{what}: scene {a_['scene']} missing", f"{what}: sahne {a_['scene']} yok"))
        if "word" in a_ and a_["word"] not in words:
            h.append(T(f"{what}: word '{a_['word']}' not in narration", f"{what}: kelime '{a_['word']}' anlatımda yok"))
        if "line" in a_ and not 1 <= a_["line"] <= line_n:
            h.append(T(f"{what}: line {a_['line']} missing", f"{what}: replik {a_['line']} yok"))
    for e in d.get("sfx", []):
        if not re.fullmatch(r"[a-z0-9_]+", e.get("id", "")):
            h.append(T(f"sfx id '{e.get('id')}' is not snake_case", f"efekt adı '{e.get('id')}' snake_case değil"))
        check_anchor(e.get("anchor", {}), T(f"sfx {e.get('id')}", f"efekt {e.get('id')}"))
    for s in d.get("scenes", []):
        for x in s.get("title_steps") or []:
            if x.get("anchor"):
                check_anchor(x["anchor"], T(f"scene {s['no']} title '{x.get('text')}'",
                                            f"sahne {s['no']} ekran yazısı '{x.get('text')}'"))
    for i, s in enumerate((d.get("music") or {}).get("mute", [])):
        check_anchor(s.get("anchor", {}), T(f"music mute {i+1}", f"müzik sus {i+1}"))
    return h


def tool_schema():
    return {"name": "save_episode", "description": "Saves the new episode plan (script.json format 3).",
            "input_schema": {"type": "object", "required": ["slug", "summary", "script"], "properties": {
                "slug": {"type": "string"}, "summary": {"type": "string"},
                "script": {"type": "object", "description": "format 3 episode plan"}}}}


def claude(system, request, extra=()):
    s = core.cfg().get("script_writer", {})
    body = {"model": s.get("model", "claude-sonnet-5-5"), "max_tokens": s.get("max_tokens", 16000),
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "tools": [tool_schema()], "tool_choice": {"type": "tool", "name": "save_episode"},
            "messages": [{"role": "user", "content": request}, *extra]}
    res = core.http("POST", "https://api.anthropic.com/v1/messages",
                    {"x-api-key": core.key("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"}, body, timeout=600)
    block = next(b for b in res["content"] if b["type"] == "tool_use")
    u = res.get("usage", {})
    print(T("  model: ", "  model: ") + f"{res.get('model')}  in/out tokens: {u.get('input_tokens')}+"
          f"{u.get('cache_read_input_tokens', 0)}(cache)/{u.get('output_tokens')}")
    return block


def script_md(d, summary):
    st = [T(f"# Episode {d['episode_no']:03d} — {d['title']}\n", f"# Bölüm {d['episode_no']:03d} — {d['title']}\n"),
          T(f"**Source:** {d.get('source_idea')} · **Genre:** {d.get('genre')} · **Target length:** ~{d.get('target_sec')} s\n",
            f"**Kaynak:** {d.get('source_idea')} · **Tür:** {d.get('genre')} · **Hedef süre:** ~{d.get('target_sec')} sn\n"),
          T("## Summary", "## Özet"), summary, "", T("## Narration", "## Seslendirme")]
    for s in d["scenes"]:
        row = f"{s['no']}. {s['narration']}"
        for r in s.get("dialogue", []):
            row += f"  *({r['character']}: \"{r['text']}\")*"
        st.append(row)
    st += ["", T("## Frames and reads", "## Kareler ve okumalar")]
    for k in frame_list(d):
        fr = k["frame"]
        typ, sec = transition(fr, k["scene_start"], k["first"])
        ex = (T(f", in: {typ}", f", giriş: {typ}") if typ != "cut" else "") + \
             (T(f", hold {k['hold']} s", f", bekle {k['hold']} sn") if k["hold"] else "")
        st.append(f"- `{k['file']}` ({fr.get('motion')}, ~{k['est_sec']:.1f} {T('s', 'sn')}{ex}) — {fr['prompt'][:140]}…")
        st += [f"    {i}. {o}" for i, o in enumerate(k["reads"], 1)]
    if d.get("canon_updates"):
        st += ["", T("## Proposed canon updates", "## Kanon güncellemesi önerisi")] + [f"- {x}" for x in d["canon_updates"]]
    st += ["", T("## Sharing", "## Paylaşım"), d.get("caption", ""), " ".join(d.get("hashtags", []))]
    return "\n".join(st) + "\n"


def save(result, episode_no=None):
    from .migrate import plan_to_v3
    d = plan_to_v3(result["script"])
    d["format"] = 3
    d["episode_no"] = episode_no or d.get("episode_no")
    slug = re.sub(r"[^a-z0-9_]+", "_", result.get("slug", "episode").lower()).strip("_")
    ep = os.path.join(core.episodes_dir(), f"{d['episode_no']:03d}_{slug}")
    os.makedirs(core.ep_path(ep, "frames"), exist_ok=True)
    core.save_plan(ep, d)
    open(os.path.join(ep, core.layout("script_md")), "w", encoding="utf-8").write(script_md(d, result.get("summary", "")))
    errors = validate(d, reads_required=True)
    print(T("saved:", "kaydedildi:"), ep)
    nwords = len(narration_text(d).split())
    nframes = sum(len(s["frames"]) for s in d["scenes"])
    print(T(f"  {d['title']} — {nwords} words, {nframes} frames", f"  {d['title']} — {nwords} kelime, {nframes} kare"))
    for x in errors:
        print(T("  WARNING:", "  UYARI:"), x)
    return ep


def cmd_new(a):
    prev = previous_episodes()
    a.episode_no = a.episode_no or (max([o[0] or 0 for o in prev] or [0]) + 1)
    if a.example is None and prev:
        a.example = prev[0][3]
    system, request = build_prompt(a)
    if a.dry_run:
        chars = len(system) + len(request)
        print(T(f"[dry-run] episode {a.episode_no}: prompt {chars} characters (~{chars // 4} tokens); nothing sent",
                f"[kuru] bölüm {a.episode_no}: istem {chars} karakter (~{chars // 4} token); hiçbir şey gönderilmedi"))
        return
    if a.manual or not core.key("ANTHROPIC_API_KEY", required=False):
        p = os.path.join(core.episodes_dir(), core.layout("prompt_file"))
        open(p, "w", encoding="utf-8").write(system + "\n\n---\n\n" + request.replace(
            "send it with the save_episode tool", "return it as one JSON object with slug, summary and script fields").replace(
            "save_episode aracıyla gönder", "slug, summary ve script alanlarını içeren tek bir JSON olarak ver") + "\n")
        print(T("no ANTHROPIC_API_KEY or --manual: prompt written ->", "ANTHROPIC_API_KEY yok ya da --manual: istem yazıldı ->"), p)
        print(T("Give it to Claude and save the returned JSON with 'series script save answer.json'.",
                "Claude'a verip dönen JSON'u 'series script save cevap.json' ile kaydet."))
        return
    print(T(f"writing episode {a.episode_no}...", f"senaryo yazılıyor (bölüm {a.episode_no})..."))
    block = claude(system, request)
    result = block["input"]
    errors = validate(result["script"], reads_required=True)
    if errors:
        print(T("  asking for fixes:", "  düzeltme isteniyor:"), "; ".join(errors))
        block = claude(system, request, [
            {"role": "assistant", "content": [block]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": block["id"], "is_error": True,
                                          "content": "The plan has these problems; fix them and send again:\n- "
                                                     + "\n- ".join(errors)}]}])
        result = block["input"]
    save(result, a.episode_no)


def cmd(a):
    try:
        if a.op == "new":
            cmd_new(a)
        elif a.op == "validate":
            h = validate(core.load_plan(core.episode_dir(a.episode)), reads_required=a.strict)
            if a.json:
                print(json.dumps({"ok": not h, "problems": h}, ensure_ascii=False, indent=1))
            else:
                print("\n".join("- " + x for x in h) if h else T("plan is valid", "plan geçerli"))
            return 1 if h else 0
        else:
            txt = open(a.file, encoding="utf-8").read()
            m = re.search(r"\{.*\}", txt, re.S)
            save(json.loads(m.group(0)), a.episode_no)
    except RuntimeError as e:
        sys.exit(T("API error: ", "API hatası: ") + str(e))
    return 0


def add_parser(sp):
    p = sp.add_parser("script", help=T("write / validate / save episode plans", "bölüm planı yaz / doğrula / kaydet"))
    s = p.add_subparsers(dest="op", required=True)
    x = s.add_parser("new"); x.add_argument("--idea"); x.add_argument("--note"); x.add_argument("--example")
    x.add_argument("--episode-no", type=int); x.add_argument("--manual", action="store_true")
    x.add_argument("--dry-run", action="store_true")
    x = s.add_parser("validate"); x.add_argument("episode"); x.add_argument("--strict", action="store_true")
    x.add_argument("--json", action="store_true")
    x = s.add_parser("save"); x.add_argument("file"); x.add_argument("--episode-no", type=int)
    p.set_defaults(func=cmd)
