"""Sound design helpers.

  series sfx make <id> "<prompt>" --duration 3 [--influence 0.5] [--peak -3] [--loop 3] [--redo]
  series sfx make --list file.json        [{id, prompt, duration, influence?, peak?, loop?}, ...]
        ElevenLabs sound generation; leading silence trimmed (so anchoring to a word is exact), peak levelled,
        short fades; ambience with --loop N: the file is joined to itself N times with crossfades.
        -> <audio_assets>/sfx/<id>.mp3 (+ .txt with the prompt), registered in the asset map
  series sfx dump 000 001 ...             narration per scene, current sfx anchors, ambience and music (for planning)
  series sfx duck 008 [--threshold 0.015 --ratio 6 --attack 25 --release 450] [--off] [--render] [--dry-run]
        review step after the edit: turn music ducking (music lower under speech) on/off in the plan; --render
        rebuilds only the audio of the existing video (series assemble --audio-only)
"""
import json, os, re, subprocess, tempfile

from . import assets, core, voice
from .core import strip_tags
from .i18n import T


def ff(*a):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-y", *a], capture_output=True, text=True)


def peak_db(f):
    m = re.search(r"max_volume:\s*(-?[\d.]+) dB", ff("-i", f, "-af", "volumedetect", "-f", "null", "-").stderr)
    return float(m.group(1)) if m else 0.0


def finish(raw, out, peak=-3.0, loop=1, trim=True):
    tmp = tempfile.mkdtemp()
    a = os.path.join(tmp, "a.wav")
    ff("-i", raw, "-ar", "48000", "-ac", "2", a)
    b = os.path.join(tmp, "b.wav")
    ff("-i", a, "-af", f"volume={peak - peak_db(a):.2f}dB", "-ar", "48000", b)
    if trim:      # drop leading silence below -45 dB, keep 15 ms
        c = os.path.join(tmp, "k.wav")
        ff("-i", b, "-af", "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.015,afade=t=in:d=0.008", c)
        if os.path.getsize(c) > 2000:
            b = c
    if loop > 1:
        cur = b
        for i in range(loop - 1):
            nxt = os.path.join(tmp, f"c{i}.wav")
            ff("-i", cur, "-i", b, "-filter_complex", "acrossfade=d=2:c1=tri:c2=tri", nxt)
            cur = nxt
        b = cur
    else:
        d = core.duration(b)
        c = os.path.join(tmp, "f.wav")
        ff("-i", b, "-af", f"afade=t=out:st={max(0, d - 0.06):.3f}:d=0.06", c)
        b = c
    os.makedirs(os.path.dirname(out), exist_ok=True)
    ff("-i", b, "-codec:a", "libmp3lame", "-q:a", "2", out)


def make(id_, prompt, duration, influence=0.5, peak=-3.0, loop=1, redo=False, dry=False):
    out = assets.sound_path(id_, "sfx", core.series_path("audio_assets"))
    if os.path.exists(out) and not redo:
        print(T("exists, skipped:", "var, atlandı:"), id_)
        return out
    if dry:
        print(f"[{T('dry-run', 'kuru')}] {id_}: {prompt} ({duration} s{', loop x' + str(loop) if loop > 1 else ''})")
        return out
    raw = os.path.join(tempfile.mkdtemp(), "raw.mp3")
    voice.generate_sfx(prompt, duration, raw, influence)
    finish(raw, out, peak, loop, trim=(loop == 1))
    open(out[:-4] + ".txt", "w", encoding="utf-8").write(prompt)
    assets.register(id_, out, "sfx", prompt=prompt, description="", used_in=[])
    print(T("made:", "üretildi:"), id_, core.rel(out))
    return out


def dump(nos):
    for no in nos:
        ep = core.episode_dir(no)
        d = core.load_plan(ep)
        m = d.get("music") or {}
        print(f"\n### {core.episode_no(ep)} {d.get('title')} | {d.get('genre', '')} | {T('music', 'müzik')} {m.get('id')} "
              f"mute={'yes' if m.get('mute') else '-'} duck={'yes' if m.get('duck') else '-'}")
        for s in d["scenes"]:
            dl = " / ".join(f"{x['character']}: {x['text']}" for x in s.get("dialogue", []) or [])
            print(f"S{s['no']}: {strip_tags(s['narration'])}" + (f"  ||{dl}" if dl else ""))
        def anc(a):
            return a.get("word") or (f"S{a['scene']}" if "scene" in a else json.dumps(a, ensure_ascii=False))
        print(T("AMBIENCE: ", "ORTAM: ") + "; ".join(f"{o['id']}@{o.get('volume')} {anc(o['start']) if o.get('start') else '^'}→"
                                                    f"{anc(o['end']) if o.get('end') else '$'}" for o in d.get("ambience", [])))
        print("SFX: " + "; ".join(f"{e['id']}@{anc(e.get('anchor', {}))}{e.get('offset') or ''}" for e in d.get("sfx", [])))


def duck(a):
    for no in a.args:
        ep = core.episode_dir(no)
        d = core.load_plan(ep)
        m = d.get("music")
        if not m:
            print(T(f"{no}: the plan has no music", f"{no}: planda müzik yok"))
            continue
        if a.off:
            m.pop("duck", None)
        else:
            k = {x: getattr(a, x) for x in ("threshold", "ratio", "attack", "release") if getattr(a, x) is not None}
            m["duck"] = k or True
        print(f"{'[dry-run] ' if a.dry_run else ''}{core.episode_no(ep)}: duck = {json.dumps(m.get('duck', False))}")
        if a.dry_run:
            continue
        core.save_plan(ep, d)
        if a.render:
            from . import assemble, publish
            v = publish.final_video(ep)
            if not v:
                print(T(f"{no}: no video yet; the setting applies at the next assemble", f"{no}: henüz video yok; ayar sonraki montajda uygulanır"))
                continue
            assemble.assemble(no, out=v, audio_only=True, video=v)


def cmd(a):
    if a.op == "duck":
        duck(a)
        return 0
    if a.op == "dump":
        dump(a.args)
        return 0
    if a.list:
        for e in json.load(open(a.list, encoding="utf-8")):
            make(e["id"], e["prompt"], e.get("duration"), e.get("influence", 0.5), e.get("peak", -3.0), e.get("loop", 1), a.redo, a.dry_run)
        return 0
    if len(a.args) < 2:
        raise SystemExit(T('usage: series sfx make <id> "<prompt>" --duration 3', 'kullanım: series sfx make <ad> "<prompt>" --duration 3'))
    make(a.args[0], a.args[1], a.duration, a.influence, a.peak, a.loop, a.redo, a.dry_run)
    return 0


def add_parser(sp):
    p = sp.add_parser("sfx", help=T("make sound effects / dump an episode's sound design", "efekt üret / bölümün ses tasarımı dökümü"))
    p.add_argument("op", choices=["make", "dump", "duck"]); p.add_argument("args", nargs="*")
    p.add_argument("--threshold", type=float); p.add_argument("--ratio", type=float)
    p.add_argument("--attack", type=float); p.add_argument("--release", type=float)
    p.add_argument("--off", action="store_true"); p.add_argument("--render", action="store_true")
    p.add_argument("--duration", type=float); p.add_argument("--influence", type=float, default=0.5)
    p.add_argument("--peak", type=float, default=-3.0); p.add_argument("--loop", type=int, default=1)
    p.add_argument("--list"); p.add_argument("--redo", action="store_true"); p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd)
