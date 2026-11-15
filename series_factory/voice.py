"""Voice (ElevenLabs API): narration with word timings, character lines, sound effects, music.

The key lives in <series root>/.env:  ELEVENLABS_API_KEY=...   Voices, model and settings come from series_factory.json.

  series voice episode 002           every missing (or text-changed) audio file of the episode:
        audio/<narration>.mp3 + audio/<words>   narration and word timings
        audio/<line_01>.mp3 ...                 other characters' lines (series.json voices)
        <audio_assets>/sfx/<id>.mp3             plan sfx missing from the library
        <audio_assets>/<id>.mp3                 plan music missing from the library
      options: --redo (regenerate all)  --only narration,line,sfx,music  --scribe (word timings via Scribe)
               --dry-run (characters that would be spent; nothing is called)
  series voice account                plan and remaining character credit
  series voice voices                 voices on the account (name + id)
  series voice try --voice CODE --text "..." [--out try.mp3]
  series voice transcribe audio.mp3 words.json     (Scribe, for audio made elsewhere)
  series voice mark 002               count hand-placed audio as up to date (word timings via Scribe if missing)
  series voice sfx --text "cartoon whoosh" --duration 1 --out sfx/escape.mp3
  series voice music --text "playful sneaky pizzicato" --duration 30 --out music.mp3
"""
import base64, json, os, re, sys, uuid

from . import assets, core
from .core import lines, strip_tags
from .i18n import T

API = "https://api.elevenlabs.io/v1"
SCRIBE_LANG = {"tr": "tur", "en": "eng", "de": "deu", "es": "spa", "fr": "fra"}


def H(json_=True):
    h = {"xi-api-key": core.key("ELEVENLABS_API_KEY")}
    if json_:
        h["Accept"] = "application/json"
    return h


def voice_id(code_or_id):
    """A character code from series_factory.json voices, otherwise a raw voice id."""
    s = core.cfg().get("voices", {}).get(code_or_id)
    return s["id"] if s else code_or_id


def tts(vid, text, out_mp3, settings=None):
    """Save the audio, return character timings (or None).
    settings: the plan's "tts" field or try flags; written over series.json tts."""
    t = {**core.cfg().get("tts", {}), **{k: v for k, v in (settings or {}).items() if not k.startswith("_")}}
    vs = {"stability": t["stability"], "similarity_boost": t["similarity_boost"], "speed": t.get("speed", 1.0)}
    if t.get("style") is not None:
        vs["style"] = t["style"]
    body = {"text": text, "model_id": t["model"], "language_code": t.get("language_code", core.cfg().get("lang", "en")),
            "voice_settings": vs}
    url = f"{API}/text-to-speech/{vid}/with-timestamps?output_format=mp3_44100_128"
    try:
        res = core.http("POST", url, H(), body)
    except RuntimeError as e:
        if "language_code" in str(e) or "language" in str(e).lower() and "400" in str(e):
            body.pop("language_code")
            res = core.http("POST", url, H(), body)
        else:
            raise
    open(out_mp3, "wb").write(base64.b64decode(res["audio_base64"]))
    return res.get("normalized_alignment") or res.get("alignment")


def sentences(words):
    sents, first = [], 0
    for i, w in enumerate(words):
        if re.search(r"[.!?…]+[\"'”]?$", w["text"]) or i == len(words) - 1:
            sents.append({"id": f"s{len(sents)+1}", "start": words[first]["start"], "end": w["end"],
                          "text": " ".join(x["text"] for x in words[first:i + 1]), "wordRange": [first, i]})
            first = i + 1
    return sents


def words_from_alignment(al):
    """Word list from character timings; characters inside [tags] are skipped."""
    words, cur, cs, ce, depth = [], "", None, None, 0
    for ch, s, e in zip(al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]):
        if ch == "[":
            depth += 1
            continue
        if ch == "]":
            depth = max(0, depth - 1)
            continue
        if depth:
            continue
        if ch.isspace():
            if cur:
                words.append({"text": cur, "start": cs, "end": ce, "type": "word"})
            cur, cs = "", None
        else:
            if cs is None:
                cs = s
            cur += ch
            ce = e
    if cur:
        words.append({"text": cur, "start": cs, "end": ce, "type": "word"})
    return {"words": words, "sentences": sentences(words)}


def scribe(mp3):
    c = core.cfg()
    lang = c.get("tts", {}).get("scribe_language") or SCRIBE_LANG.get(c.get("lang", "en"), "eng")
    bnd = uuid.uuid4().hex
    parts = []
    for k, v in (("model_id", "scribe_v1"), ("language_code", lang), ("timestamps_granularity", "word"),
                 ("tag_audio_events", "false")):
        parts.append(f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{bnd}\r\nContent-Disposition: form-data; name="file"; filename="audio.mp3"\r\n'
                 f'Content-Type: audio/mpeg\r\n\r\n'.encode() + open(mp3, "rb").read() + b"\r\n")
    parts.append(f"--{bnd}--\r\n".encode())
    res = core.http("POST", f"{API}/speech-to-text", {**H(), "Content-Type": f"multipart/form-data; boundary={bnd}"},
                    raw=b"".join(parts))
    words = [{"text": w["text"], "start": w["start"], "end": w["end"], "type": "word"}
             for w in res.get("words", []) if w.get("type") == "word"]
    return {"words": words, "sentences": sentences(words), "text": res.get("text", "")}


def write_json(d, p):
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def up_to_date(mp3, text, redo=False):
    """True if the audio exists and was made from the same text (do not regenerate)."""
    txt = mp3[:-4] + ".txt"
    return (not redo and os.path.exists(mp3) and os.path.exists(txt) and open(txt, encoding="utf-8").read() == text)


def mark_text(mp3, text):
    open(mp3[:-4] + ".txt", "w", encoding="utf-8").write(text)


def generate_sfx(prompt, sec, out, influence=0.5):
    body = {"text": prompt, "prompt_influence": influence}
    if sec:
        body["duration_seconds"] = min(float(sec), 22.0)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "wb").write(core.http("POST", f"{API}/sound-generation", H(False), body, raw_response=True))


def generate_music(prompt, sec, out):
    """Music API first; if the plan does not allow it, a 22 s sound-effect loop (the edit loops it)."""
    os.makedirs(os.path.dirname(out), exist_ok=True)
    try:
        b = core.http("POST", f"{API}/music", H(False),
                      {"prompt": prompt, "music_length_ms": int(sec * 1000), "force_instrumental": True},
                      raw_response=True, timeout=600)
        open(out, "wb").write(b)
        return "music"
    except RuntimeError as e:
        print(T("  Music API unavailable, using an sfx loop:", "  Music API kullanılamadı, efekt döngüsüne geçiliyor:"), str(e)[:120])
        generate_sfx(prompt + ", seamless loop", 22, out, influence=0.6)
        return "loop"


def narration_raw(d):
    return " ".join(s["narration"].strip() for s in d["scenes"])


def estimate(e):
    """Characters to be voiced (up-to-date files excluded) and new sfx ids."""
    ep = core.episode_dir(e)
    d = core.load_plan(ep)
    aud = core.ep_path(ep, "audio")
    n = 0
    text = narration_raw(d)
    if not _same_text(os.path.join(aud, core.layout("narration") + ".mp3"), text):
        n += len(text)
    for i, s, r in lines(d):
        if not _same_text(os.path.join(aud, core.layout("line", n=i) + ".mp3"), r["text"]):
            n += len(r["text"])
    new_sfx = [x["id"] for x in d.get("sfx", []) if not os.path.exists(assets.sound_path(x["id"], "sfx"))]
    return n, new_sfx


def _same_text(mp3, text):
    t = mp3[:-4] + ".txt"
    return os.path.exists(mp3) and os.path.exists(t) and open(t, encoding="utf-8").read().strip() == text.strip()


def cmd_episode(a):
    if a.dry_run:
        n, sfx = estimate(a.episode)
        core.emit({"episode": a.episode, "characters": n, "new_sfx": sfx}, a.json,
                  [T(f"[dry-run] {a.episode}: {n} characters", f"[kuru] {a.episode}: {n} karakter")
                   + (T(f", new sfx: {', '.join(sfx)}", f", yeni efekt: {', '.join(sfx)}") if sfx else "")])
        return
    c = core.cfg()
    ep = core.episode_dir(a.episode)
    d = core.load_plan(ep)
    aud = core.ep_path(ep, "audio")
    os.makedirs(aud, exist_ok=True)
    steps = set((a.only or "narration,line,sfx,music").split(","))
    sfx_dir = core.series_path("audio_assets")
    no = core.episode_no(ep)

    if "narration" in steps:
        text = narration_raw(d)
        mp3, wj = os.path.join(aud, core.layout("narration") + ".mp3"), os.path.join(aud, core.layout("words"))
        if up_to_date(mp3, text, a.redo) and os.path.exists(wj):
            print(T("narration: up to date, skipped", "anlatım: güncel, atlandı"))
        else:
            al = tts(voice_id(c.get("narrator")), text, mp3, {**c.get("narration_tts", {}), **(d.get("tts") or {})})
            w = scribe(mp3) if (a.scribe or not al) else words_from_alignment(al)
            expected = len(" ".join(strip_tags(s["narration"]) for s in d["scenes"]).split())
            if not a.scribe and al and len(w["words"]) != expected:
                print(T(f"  alignment word count off ({len(w['words'])}/{expected}), trying Scribe",
                        f"  hizalama kelime sayısı tutmadı ({len(w['words'])}/{expected}), Scribe deneniyor"))
                w = scribe(mp3)
            write_json(w, wj)
            mark_text(mp3, text)
            print(T(f"narration: {core.duration(mp3):.1f} s, {len(w['words'])} words",
                    f"anlatım: {core.duration(mp3):.1f} sn, {len(w['words'])} kelime"))

    if "line" in steps:
        for n, s, r in lines(d):
            mp3 = os.path.join(aud, core.layout("line", n=n) + ".mp3")
            if r["character"] not in c.get("voices", {}):
                print(T(f"line {n:02d}: no voice for '{r['character']}' in series.json, skipped",
                        f"replik {n:02d}: '{r['character']}' için series.json'da ses yok, atlandı"))
                continue
            if up_to_date(mp3, r["text"], a.redo):
                print(T(f"line {n:02d}: up to date", f"replik {n:02d}: güncel"))
                continue
            tts(voice_id(r["character"]), r["text"], mp3)
            mark_text(mp3, r["text"])
            print(T(f"line {n:02d}: {r['character']} '{r['text']}' {core.duration(mp3):.1f} s",
                    f"replik {n:02d}: {r['character']} '{r['text']}' {core.duration(mp3):.1f} sn"))

    if "sfx" in steps:
        for e in d.get("sfx", []):
            f = assets.sound_path(e["id"], "sfx", sfx_dir)
            if os.path.exists(f) and not a.redo:
                continue
            generate_sfx(e["prompt"], e.get("duration"), f)
            assets.register(e["id"], f, "sfx", prompt=e["prompt"], description=e.get("description", ""), used_in=[no])
            print(T("sfx generated:", "efekt üretildi:"), e["id"])

    if "music" in steps and d.get("music"):
        m = d["music"]
        f = assets.sound_path(m["id"], "music", sfx_dir)
        if not os.path.exists(f) or a.redo:
            print(T("music generated:", "müzik üretildi:"), m["id"], generate_music(m["prompt"], m.get("duration", 30), f))
            assets.register(m["id"], f, "music", prompt=m["prompt"], description=m.get("description", ""), used_in=[no])
    print(T("voice step done:", "ses adımı tamam:"), ep)


def cmd(a):
    try:
        if a.op == "episode":
            cmd_episode(a)
        elif a.op == "mark":
            ep = core.episode_dir(a.episode)
            d = core.load_plan(ep)
            aud = core.ep_path(ep, "audio")
            mp3 = os.path.join(aud, core.layout("narration") + ".mp3")
            if os.path.exists(mp3):
                mark_text(mp3, narration_raw(d))
                if not os.path.exists(os.path.join(aud, core.layout("words"))):
                    write_json(scribe(mp3), os.path.join(aud, core.layout("words")))
                print(T("narration marked", "anlatım işaretlendi"))
            for n, s, r in lines(d):
                f = os.path.join(aud, core.layout("line", n=n) + ".mp3")
                if os.path.exists(f):
                    mark_text(f, r["text"])
                    print(T(f"line {n:02d} marked", f"replik {n:02d} işaretlendi"))
        elif a.op == "account":
            s = core.http("GET", f"{API}/user/subscription", H())
            left = s.get("character_limit", 0) - s.get("character_count", 0)
            print(T(f"plan: {s.get('tier')}  used: {s.get('character_count')}/{s.get('character_limit')}  left: {left}",
                    f"plan: {s.get('tier')}  kullanılan: {s.get('character_count')}/{s.get('character_limit')}  kalan: {left}"))
        elif a.op == "voices":
            for v in core.http("GET", f"{API}/voices", H()).get("voices", []):
                lab = v.get("labels") or {}
                print(f"{v['voice_id']}  {v['name']}  {lab.get('language','')} {lab.get('accent','')} {lab.get('gender','')}")
        elif a.op == "try":
            st = {k: v for k, v in (("stability", a.stability), ("style", a.style)) if v is not None}
            tts(voice_id(a.voice), a.text, a.out, st)
            print("ok", a.out, f"{core.duration(a.out):.1f} {T('s', 'sn')}")
        elif a.op == "transcribe":
            write_json(scribe(a.audio), a.out)
            print("ok ->", a.out)
        elif a.op == "sfx":
            generate_sfx(a.text, a.duration, a.out, a.influence)
            print("ok", a.out)
        elif a.op == "music":
            print("ok", a.out, generate_music(a.text, a.duration, a.out))
    except RuntimeError as e:
        sys.exit(T("ElevenLabs error: ", "ElevenLabs hatası: ") + str(e))
    return 0


def add_parser(sp):
    p = sp.add_parser("voice", help=T("narration, lines, sfx and music (ElevenLabs)", "anlatım, replik, efekt ve müzik (ElevenLabs)"))
    s = p.add_subparsers(dest="op", required=True)
    x = s.add_parser("episode"); x.add_argument("episode")
    x.add_argument("--redo", action="store_true"); x.add_argument("--only"); x.add_argument("--scribe", action="store_true")
    x.add_argument("--dry-run", action="store_true"); x.add_argument("--json", action="store_true")
    s.add_parser("account"); s.add_parser("voices")
    x = s.add_parser("mark"); x.add_argument("episode")
    x = s.add_parser("try"); x.add_argument("--voice", required=True); x.add_argument("--text", required=True)
    x.add_argument("--out", default="try.mp3"); x.add_argument("--stability", type=float); x.add_argument("--style", type=float)
    x = s.add_parser("transcribe"); x.add_argument("audio"); x.add_argument("out")
    x = s.add_parser("sfx"); x.add_argument("--text", required=True); x.add_argument("--out", required=True)
    x.add_argument("--duration", type=float); x.add_argument("--influence", type=float, default=0.5)
    x = s.add_parser("music"); x.add_argument("--text", required=True); x.add_argument("--out", required=True)
    x.add_argument("--duration", type=float, default=30)
    p.set_defaults(func=cmd)
