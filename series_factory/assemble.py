"""Assemble (ffmpeg): turns an episode plan plus its frames and audio into the final video.

Reads the plan (script.json) and combines:
  frames/   -> each frame stays on screen for its sentences (Ken Burns motion)
  audio/<narration>.mp3 + audio/<words>.json -> narration and word timings
  audio/<line_NN>.mp3 -> other characters' lines (inserted where the plan puts them)
  sfx + music (audio assets) -> mixed at the plan's anchors
Output: output/<episode>.mp4 (profile size, subtitles burned in, loudness normalised) and
        output/<episode><timing_suffix> (used by `series strips` and `series check`).

  series assemble <episode> [--out file.mp4] [--no-sfx] [--audio-assets folder]

Subtitle position: "subtitle_pos" on the frame (or scene): "top" | "middle" | "bottom" (default bottom; when missing
and the optional subtitle extra is installed, it is decided from the picture). With a title on screen, top moves down.
On-screen title (scene title_text) stays until the scene ends; "title_sec" shortens it.
Step titles: scene "title_steps": [{text, anchor: {word|line|frame}, offset}].
Timing: frame "hold": s -> the frame stays silent after its words (music/sfx continue).
Transition: frame "transition" (core.transition); default fade 0.35 s at scene starts, cut inside. First frame: cut.
"""
import json, os, shutil, subprocess, tempfile

from . import assets, core, profiles
from .core import strip_tags, transition
from .i18n import T


CUT_FADE = 0.012     # s; anti-click fade where narration is cut next to a line or silence
# mix inputs and the limiter share one format (loudnorm outputs 192 kHz; the limiter should run at 48 kHz)
STEREO = "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"


def run(cmd):
    subprocess.run(cmd, check=True)


def zoompan(motion, frames, W, H, FPS):
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    n = max(1, frames - 1)
    e = f"(0.5-0.5*cos(PI*on/{n}))"          # slow in, slow out
    if motion == "in":
        z, x, y = f"1+0.12*{e}", cx, cy
    elif motion == "out":
        z, x, y = f"1.12-0.12*{e}", cx, cy
    elif motion == "fast":                   # action: accelerate in (ease in)
        z, x, y = f"1+0.3*(on/{n})*(on/{n})", cx, cy
    elif motion == "panL":
        z, x, y = "1.12", f"(iw-iw/zoom)*(1-{e})", cy
    elif motion == "static":
        z, x, y = "1.0", cx, cy
    else:  # panR
        z, x, y = "1.12", f"(iw-iw/zoom)*{e}", cy
    return f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS}"


def render_shot(img, frames, motion, out, W, H, FPS):
    frames = max(1, frames)
    vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
          f"{zoompan(motion, frames, W, H, FPS)},format=yuv420p")
    run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", img, "-vf", vf, "-frames:v", str(frames),
         "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out])


def align_words(trans, script_text):
    """Match transcript word timings to the script's spelling (e.g. '9.40' -> 'nine forty')."""
    ws = [w for w in trans["words"] if w.get("type", "word") == "word"]
    sw = script_text.split()
    out, i, j = [], 0, 0
    while i < len(ws) and j < len(sw):
        w = ws[i]
        if any(c.isdigit() for c in w["text"]) and not any(c.isdigit() for c in sw[j]) and j + 1 < len(sw):
            m = (w["start"] + w["end"]) / 2
            out.append({"text": sw[j], "start": w["start"], "end": m, "i": i})
            out.append({"text": sw[j + 1], "start": m, "end": w["end"], "i": i})
            i += 1
            j += 2
        else:
            out.append({"text": sw[j], "start": w["start"], "end": w["end"], "i": i})
            i += 1
            j += 1
    if j < len(sw):
        print(T(f"WARNING: {len(sw) - j} words could not be timed (transcript and text may differ).",
                f"UYARI: {len(sw) - j} kelime zamanlanamadı (transkript ile metin farklı olabilir)."))
    return out


def ts(t):
    t = max(0, t)
    return f"{int(t//3600)}:{int(t%3600//60):02d}:{t%60:05.2f}"


def auto_position(ep, fr, s):
    """No subtitle position in the plan: decide from the picture (optional extra); otherwise 'bottom'."""
    try:
        from . import subplace
        k = subplace.decide(core.ep_path(ep, "frames", fr["file"]), fr.get("motion", "in"), bool(s.get("dialogue")))[0]
        print(T(f"  subtitle (auto): {fr['file']} -> {k}", f"  altyazı (oto): {fr['file']} -> {k}"))
        return k
    except Exception as e:
        print(T(f"  subtitle (auto) not possible, bottom: {fr['file']} ({e})",
                f"  altyazı (oto) yapılamadı, alt: {fr['file']} ({e})"))
        return "bottom"


def line_styles():
    """Per-character line colours (series.json characters.<CODE>.line_colour) -> {style name: colour}."""
    out = {}
    for code, ch in core.cfg().get("characters", {}).items():
        if ch.get("line_colour"):
            out["Line_" + code] = ch["line_colour"]
    return out


def assemble(episode, out=None, no_sfx=False, audio_assets=None, plan_file=None, audio_only=False, video=None):
    """audio_only: keep the picture of an existing video (video, default: out) and only rebuild the mix;
    stops when the plan's length no longer matches the video. plan_file: use this plan instead (A/B tests)."""
    core.check_media_tools()
    c = core.cfg()
    ep = core.episode_dir(episode)
    P = core.profile(core.episode_format(ep))
    W, H, FPS = P["width"], P["height"], P["fps"]
    FONT = c.get("video", {}).get("font", "DejaVu Sans")
    END_PAD, TITLE_MIN, LINE_GAP = P["end_pad"], P["title_min"], P["default_line_gap"]
    END_FADE = c.get("video", {}).get("end_fade", 0.4)
    MAXW = P["subtitles"]["max_words"]
    lstyles = line_styles()

    if plan_file:
        from .migrate import plan_to_v3
        d = plan_to_v3(json.load(open(plan_file, encoding="utf-8")))
    else:
        d = core.load_plan(ep)
    aud = core.ep_path(ep, "audio")
    audio = os.path.join(aud, core.layout("narration") + ".mp3")
    trans = json.load(open(os.path.join(aud, core.layout("words")), encoding="utf-8"))
    sfx_dir = audio_assets or core.series_path("audio_assets")
    out = out or core.ep_path(ep, "output", os.path.basename(ep) + ".mp4")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    total_audio = core.duration(audio)

    words = align_words(trans, " ".join(strip_tags(s["narration"]) for s in d["scenes"]))
    sent_of_word = {}
    for k, s in enumerate(trans.get("sentences", []), start=1):
        for wi in range(s["wordRange"][0], s["wordRange"][1] + 1):
            sent_of_word[wi] = k

    # shot list (the plan's frames) and word ranges
    shots, pos = [], 0
    for s in d["scenes"]:
        n_ = len(strip_tags(s["narration"]).split())
        lo, hi = pos, pos + n_ - 1
        pos += n_
        for k_i, fr in enumerate(s["frames"]):
            start = lo
            if k_i > 0:
                start = next(k for k in range(lo, hi + 1) if words[k]["text"] == fr["start_word"])
                shots[-1]["rng"] = (shots[-1]["rng"][0], start - 1)
            g_type, g_sec = transition(fr, k_i == 0, not shots)
            shots.append({"scene": s["no"], "frame": fr["file"], "motion": fr.get("motion", "in"),
                          "pos": fr.get("subtitle_pos") or s.get("subtitle_pos") or auto_position(ep, fr, s),
                          "hold": float(fr.get("hold", 0) or 0), "transition": (g_type, g_sec),
                          "reads": fr.get("reads") or [], "rng": (start, hi)})

    # where the lines go
    line_n = 0
    for s in d["scenes"]:
        for r in s.get("dialogue", []):
            line_n += 1
            y = r.get("at") or {}
            item = {"n": line_n, "text": r["text"], "character": r["character"]}
            if "frame_start" in y:
                next(sh for sh in shots if sh["frame"] == y["frame_start"]).setdefault("before", []).append(item)
            elif "after_word" in y:
                sh = next(sh for sh in shots if sh["scene"] == s["no"]
                          and any(words[k]["text"] == y["after_word"] for k in range(sh["rng"][0], sh["rng"][1] + 1)))
                item["word"] = y["after_word"]
                sh.setdefault("inside", []).append(item)
            else:  # default: start of the scene's first frame
                next(sh for sh in shots if sh["scene"] == s["no"]).setdefault("before", []).append(item)

    mid = lambda k: (words[k]["end"] + words[k + 1]["start"]) / 2  # noqa: E731
    for n, sh in enumerate(shots):
        lo, hi = sh["rng"]
        sh["a"] = 0.0 if n == 0 else mid(lo - 1)
        sh["b"] = total_audio if n == len(shots) - 1 else mid(hi)

    tmp = tempfile.mkdtemp()
    # decode the narration once; pieces are cut from it sample-accurately
    audio_wav = os.path.join(tmp, "narration.wav")
    run(["ffmpeg", "-v", "error", "-y", "-i", audio, "-ac", "2", "-ar", "48000", audio_wav])
    pieces, clips, ev, remap = [], [], [], []
    kinds = []        # per piece: ("narration", seconds) or ("other", 0)
    t = [0.0]
    line_start, scene_start, frame_start = {}, {}, {}

    def piece(args_, kind="other", dd=0.0):
        p = os.path.join(tmp, f"a{len(pieces):03d}.wav")
        run(["ffmpeg", "-v", "error", "-y", *args_, "-ac", "2", "-ar", "48000", p])
        pieces.append(p)
        kinds.append((kind, dd))

    def add_audio(a, b):
        if b - a < 0.01:   # a line at the very end of a frame: do not cut an empty piece
            return
        piece(["-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", audio_wav], "narration", b - a)
        remap.append((a, b, t[0]))
        t[0] += b - a

    def add_silence(dd):
        piece(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{dd:.3f}"])
        t[0] += dd

    def add_line(item):
        f = os.path.join(aud, core.layout("line", n=item["n"]) + ".mp3")
        line_start[item["n"]] = t[0]
        if os.path.exists(f):
            dd = core.duration(f) + 0.35
            piece(["-i", f, "-af", f"apad=whole_dur={dd:.3f}"])
        else:
            print(T(f"WARNING: {os.path.basename(f)} missing, left a gap.", f"UYARI: {os.path.basename(f)} yok, boşluk bırakıldı."))
            dd = LINE_GAP
            piece(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{dd:.3f}"])
        style = "Line_" + item["character"] if ("Line_" + item["character"]) in lstyles else "Line"
        ev.append((style, t[0] + 0.1, t[0] + dd - 0.05, f"{core.display_name(item['character'])}: {item['text']}"))
        t[0] += dd

    scene = {s["no"]: s for s in d["scenes"]}
    for n, sh in enumerate(shots):
        start = t[0]
        if sh["scene"] not in scene_start:
            scene_start[sh["scene"]] = start
            if scene[sh["scene"]].get("title_text"):
                ev.append(("Title", start + 0.15, -sh["scene"], scene[sh["scene"]]["title_text"]))
        frame_start[sh["frame"]] = start
        for item in sh.get("before", []):
            add_line(item)
        a = sh["a"]
        for item in sh.get("inside", []):
            lo, hi = sh["rng"]
            cut = mid(next(k for k in range(lo, hi + 1) if words[k]["text"] == item["word"]))
            add_audio(a, cut)
            add_line(item)
            a = cut
        add_audio(a, sh["b"])
        sh["speech_end"] = t[0]
        if n == len(shots) - 1:
            add_silence(max(END_PAD, sh["hold"]))
        elif sh["hold"] > 0:
            add_silence(sh["hold"])
        sh["dur"] = t[0] - start
        sh["t0"], sh["t1"] = start, t[0]
    total = t[0]

    def new_time(x):
        for oa, ob, ns in remap:
            if oa <= x <= ob:
                return ns + (x - oa)
        # outside every piece (e.g. the last word ends a few ms after the audio file): use the closest earlier piece
        before = [r for r in remap if r[0] <= x]
        oa, ob, ns = before[-1] if before else remap[0]
        return ns + (x - oa)

    # subtitles: break at sentence ends, at most MAXW words;
    # allow MAXW+1 when a single word would be left at the end of a sentence (so an address is not left alone)
    chunks, cur = [], []
    sent = lambda w: sent_of_word.get(w["i"])  # noqa: E731
    for j, w in enumerate(words):
        new_sentence = cur and sent(w) != sent(cur[-1])
        last_word = j + 1 == len(words) or sent(words[j + 1]) != sent(w)
        if cur and (new_sentence or len(cur) >= MAXW + 1 or (len(cur) == MAXW and not last_word)):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    for ch, nxt in zip(chunks, chunks[1:] + [None]):
        s_, e_ = new_time(ch[0]["start"]), new_time(ch[-1]["end"]) + 0.25
        if nxt:
            e_ = min(e_, new_time(nxt[0]["start"]) - 0.02)
        ev.append(("Default", s_, max(e_, s_ + 0.6), " ".join(w["text"] for w in ch)))

    # video: frame counts from cut times (no accumulated rounding drift); transitions sit on the middle of the cut
    for sh in shots:
        sh["f0"], sh["f1"] = round(sh["t0"] * FPS), round(sh["t1"] * FPS)
    ovl = [0] * len(shots)                      # ovl[n]: overlap (frames) entering shot n
    for n in range(1, len(shots)):
        typ, sec = shots[n]["transition"]
        o = round(sec * FPS) if typ != "cut" else 0
        o = min(o, int(0.4 * min(shots[n - 1]["f1"] - shots[n - 1]["f0"], shots[n]["f1"] - shots[n]["f0"])))
        if o < 3:
            o, shots[n]["transition"] = 0, ("cut", 0.0)
        ovl[n] = o
    vj, aj = os.path.join(tmp, "v.mp4"), os.path.join(tmp, "a.wav")
    if not audio_only:
        for n, sh in enumerate(shots):
            cpath = os.path.join(tmp, f"v{n:02d}.mp4")
            img = core.ep_path(ep, "frames", sh["frame"])
            if not os.path.exists(img):
                raise SystemExit(T(f"Missing frame: {core.layout('frames')}/{sh['frame']} (run 'series frames' first)",
                                   f"Kare eksik: {core.layout('frames')}/{sh['frame']} (önce 'series frames' çalıştır)"))
            before = ovl[n] // 2
            after = (ovl[n + 1] - ovl[n + 1] // 2) if n + 1 < len(shots) else 0
            render_shot(img, sh["f1"] - sh["f0"] + before + after, sh["motion"], cpath, W, H, FPS)
            clips.append((cpath, sh["f1"] - sh["f0"] + before + after))
        fg, ins_v = [], []
        for n, (cp, fr) in enumerate(clips):
            ins_v += ["-i", cp]
            fg.append(f"[{n}:v]fps={FPS},settb=1/{FPS},format=yuv420p[c{n}]")
        cur = "[c0]"
        length = clips[0][1]
        for n in range(1, len(clips)):
            o = ovl[n]
            if o:
                fg.append(f"{cur}[c{n}]xfade=transition={shots[n]['transition'][0]}:duration={o / FPS:.4f}:"
                          f"offset={(length - o) / FPS:.4f},settb=1/{FPS}[x{n}]")
            else:
                fg.append(f"{cur}[c{n}]concat=n=2:v=1:a=0,settb=1/{FPS}[x{n}]")
            cur = f"[x{n}]"
            length += clips[n][1] - o
        graph = ";\n".join(fg) + (f";\n{cur}null[vo]" if len(clips) > 1 else ";\n[c0]null[vo]")
        run(["ffmpeg", "-v", "error", "-y", *ins_v, "-filter_complex", graph, "-map", "[vo]",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", vj])
    # narration next to a line/silence is cut at a word tail: short fades so it does not click
    for i, (kind, dd) in enumerate(kinds):
        if kind != "narration" or dd < 0.05:
            continue
        af = []
        if i > 0 and kinds[i - 1][0] != "narration":
            af.append(f"afade=t=in:d={CUT_FADE}")
        if i + 1 < len(kinds) and kinds[i + 1][0] != "narration":
            af.append(f"afade=t=out:st={dd - CUT_FADE:.4f}:d={CUT_FADE}")
        if af:
            q = pieces[i][:-4] + "_f.wav"
            run(["ffmpeg", "-v", "error", "-y", "-i", pieces[i], "-af", ",".join(af), q])
            pieces[i] = q
    al = os.path.join(tmp, "a.txt")
    open(al, "w").write("".join(f"file '{p}'\n" for p in pieces))
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", al, "-c", "copy", aj])

    # sfx + music mix
    def anchor(cp, offset=0.0):
        if "scene" in cp:
            x = scene_start[cp["scene"]]
        elif "line" in cp:
            x = line_start[cp["line"]]
        elif "frame" in cp:
            x = frame_start[cp["frame"]]
        else:
            es = [w for w in words if w["text"] == cp["word"]]
            if not es:
                raise SystemExit(T(f"anchor word not found: {cp['word']!r}", f"çapa kelimesi bulunamadı: {cp['word']!r}"))
            x = new_time(es[min(cp.get("n", 1), len(es)) - 1]["start"])   # "n": the n-th occurrence
        return max(0.0, x + offset)

    ins, fl, k = ["-i", aj], [], 1
    duck_on = False
    if not no_sfx:
        # ambience: a continuous bed over the whole video (or between anchors), faded in/out, looped
        for o in d.get("ambience", []):
            f = assets.sound_path(o["id"], "sfx", sfx_dir)
            if not os.path.exists(f):
                print(T("ambience file missing, skipped:", "ortam dosyası yok, atlandı:"), o["id"])
                continue
            t0 = anchor(o["start"], o.get("start_offset", 0)) if o.get("start") else 0.0
            t1 = anchor(o["end"], o.get("end_offset", 0)) if o.get("end") else total
            fd = float(o.get("fade", 1.2))
            ms = int(t0 * 1000)
            ins += ["-stream_loop", "-1", "-i", f]
            fl.append(f"[{k}:a]aresample=48000,{STEREO},atrim=0:{max(0.1, t1 - t0):.3f},volume={o.get('volume', 0.3)},"
                      f"afade=t=in:d={fd},afade=t=out:st={max(0, t1 - t0 - fd):.2f}:d={fd},adelay={ms}|{ms}[e{k}]")
            k += 1
        for e in d.get("sfx", []):
            f = assets.sound_path(e["id"], "sfx", sfx_dir)
            if not os.path.exists(f):
                print(T("sfx file missing, skipped:", "efekt dosyası yok, atlandı:"), e["id"])
                continue
            ms = int(anchor(e["anchor"], e.get("offset", 0)) * 1000)
            ins += ["-i", f]
            fl.append(f"[{k}:a]aresample=48000,{STEREO},volume={e.get('volume', 0.5)},adelay={ms}|{ms}[e{k}]")
            k += 1
        mz = d.get("music")
        if mz and os.path.exists(assets.sound_path(mz["id"], "music", sfx_dir)):
            mute = ""
            if mz.get("mute"):
                a0 = anchor(mz["mute"][0]["anchor"], mz["mute"][0].get("offset", 0))
                b0 = anchor(mz["mute"][1]["anchor"], mz["mute"][1].get("offset", 0))
                mute = f",volume=0:enable='between(t,{a0:.2f},{b0:.2f})'"
            ins += ["-stream_loop", "-1", "-i", assets.sound_path(mz["id"], "music", sfx_dir)]
            # lower the music under narration/lines (sidechain); replaces "mute". On with true or a non-empty dict
            # {threshold, ratio, attack, release}; an empty {} is off (same as the source pipeline).
            duck = mz.get("duck")
            fl.append(f"[{k}:a]aresample=48000,{STEREO},atrim=0:{total:.3f},volume={mz.get('volume', 0.12)}{mute},"
                      f"afade=t=out:st={max(0, total-1.5):.2f}:d=1.5[{'m' if duck else 'e'}{k}]")
            if duck:
                dk = duck if isinstance(duck, dict) else {}
                fl.append(f"[m{k}][sc]sidechaincompress=threshold={dk.get('threshold', 0.015)}:ratio={dk.get('ratio', 6)}:"
                          f"attack={dk.get('attack', 25)}:release={dk.get('release', 450)}:makeup=1[e{k}]")
                duck_on = True
            k += 1
        elif mz:
            print(T("music file missing, skipped:", "müzik dosyası yok, atlandı:"), mz["id"])
    tags = "".join(f"[e{i}]" for i in range(1, k))
    lufs = c.get("video", {}).get("target_lufs", -14)
    fl.append(f"[0:a]{STEREO}" + (",asplit=2[a0][sc]" if duck_on else "[a0]"))
    tags = "[a0]" + tags
    fl.append(f"{tags}amix=inputs={k}:normalize=0:duration=first,"
              f"loudnorm=I={lufs}:TP=-3:LRA=11,aresample=48000,{STEREO},alimiter=limit=0.63:level=disabled[m]")
    # The old setting (TP -1.5, limit 0.95, auto level) let the final file reach +5 dBFS true peak. AAC overshoots
    # sharp sfx hits by 2-3 dB, so the limit leaves room (-4 dBFS) and auto level is off.
    mixed = os.path.join(tmp, "mix.wav")
    run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(fl), "-map", "[m]", "-ar", "48000", mixed])

    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
            "MarginR, MarginV, Encoding\n"
            + "\n".join(profiles.ass_styles(P, FONT, lstyles))
            + "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    ass = os.path.join(tmp, "subs.ass")

    def position(x):
        for sh in shots:
            if sh["t0"] - 0.01 <= x < sh["t1"]:
                return sh["pos"]
        return "bottom"

    # on-screen title: stays until the scene ends (at least TITLE_MIN); "title_sec" on the scene overrides
    sb = sorted(scene_start.items(), key=lambda x: x[1])

    def scene_end(no):
        i = [n for n, _ in sb].index(no)
        return sb[i + 1][1] if i + 1 < len(sb) else total
    ev2 = []
    for st, a, b, tx in ev:
        if st == "Title" and b < 0:
            no = -b
            fixed = scene[no].get("title_sec")
            b = a + float(fixed) if fixed else max(a + TITLE_MIN, scene_end(no) - 0.25)
        ev2.append((st, a, b, tx))
    ev = ev2
    # step titles: each step until the next, the last until the scene ends; no anchor = scene start
    for s_ in d["scenes"]:
        steps = s_.get("title_steps")
        if not steps:
            continue
        zs = [anchor(x["anchor"], x.get("offset", 0)) if x.get("anchor") else scene_start[s_["no"]] + 0.15 for x in steps]
        last = scene_end(s_["no"]) - 0.25
        for i, x in enumerate(steps):
            b_ = zs[i + 1] if i + 1 < len(zs) else max(last, zs[i] + TITLE_MIN)
            ev.append(("Title", zs[i], b_, x["text"]))
    titles = [(a, b) for st, a, b, _ in ev if st == "Title"]

    def style(st, a, b):
        if st != "Default" and not st.startswith("Line"):
            return st
        k_ = position(a)
        if k_ == "middle":
            return st + profiles.POSITION_SUFFIX["middle"]
        if k_ == "top":
            return st + (profiles.POSITION_SUFFIX["top2"] if any(a < y and b > x for x, y in titles)
                         else profiles.POSITION_SUFFIX["top"])
        return st
    ev = [(style(st, a, b), a, b, tx) for st, a, b, tx in ev]
    open(ass, "w", encoding="utf-8").write(head + "\n".join(
        f"Dialogue: 0,{ts(a)},{ts(b)},{st},,0,0,0,,{tx}" for st, a, b, tx in ev) + "\n")
    if audio_only:
        src = video or out
        if not os.path.exists(src):
            raise SystemExit(T(f"--audio-only: source video missing: {src}", f"--audio-only: kaynak video yok: {src}"))
        old = os.path.join(tmp, "old.mp4")
        shutil.copy(src, old)
        dv = core.duration(old)
        if abs(dv - total) > 0.15:
            raise SystemExit(T(f"--audio-only: length mismatch (video {dv:.2f} s, plan {total:.2f} s); the plan changed "
                               "after the video, a full render is needed",
                               f"--audio-only: süre uyuşmuyor (video {dv:.2f} sn, plan {total:.2f} sn); plan videodan sonra "
                               "değişmiş, tam render gerek"))
        run(["ffmpeg", "-v", "error", "-y", "-i", old, "-i", mixed, "-map", "0:v", "-map", "1:a", "-shortest",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out])
        print(T("ok (audio rebuilt)", "ok (ses yenilendi)"), out, round(total, 2), T("s", "sn"))
        return out, None
    fade = f"fade=t=out:st={max(0, total - END_FADE):.3f}:d={END_FADE}," if END_FADE > 0 else ""
    run(["ffmpeg", "-v", "error", "-y", "-i", vj, "-i", mixed, "-vf", f"{fade}ass={ass}", "-map", "0:v", "-map", "1:a",
         "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-movflags", "+faststart", out])
    timing = {"video": os.path.basename(out), "duration": round(total, 3), "fps": FPS, "end_fade": END_FADE,
              "frames": [{"scene": sh["scene"], "frame": sh["frame"], "motion": sh["motion"],
                          "t0": round(sh["t0"], 3), "t1": round(sh["t1"], 3), "speech_end": round(sh["speech_end"], 3),
                          "hold": sh["hold"], "transition": {"type": sh["transition"][0], "duration": round(ovl[n] / FPS, 3)},
                          "lines": len(sh.get("before", [])) + len(sh.get("inside", [])), "reads": sh["reads"]}
                         for n, sh in enumerate(shots)]}
    tf = os.path.splitext(out)[0] + core.layout("timing_suffix")
    json.dump(timing, open(tf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("ok", out, round(total, 2), T("s", "sn"))
    return out, timing


def cmd(a):
    assemble(a.episode, a.out, a.no_sfx, a.audio_assets, plan_file=a.plan, audio_only=a.audio_only, video=a.video)
    return 0


def add_parser(sp):
    p = sp.add_parser("assemble", help=T("build the video from frames + audio", "kareler + seslerden videoyu kur"))
    p.add_argument("episode"); p.add_argument("--out"); p.add_argument("--audio-assets")
    p.add_argument("--no-sfx", action="store_true")
    p.add_argument("--plan", help=T("use this plan file instead of the episode plan (A/B tests)",
                                    "bölüm planı yerine bu plan dosyası (A/B denemeleri)"))
    p.add_argument("--audio-only", action="store_true",
                   help=T("keep the picture of the existing video, rebuild only the mix", "mevcut videonun görüntüsünü koru, yalnız karışımı yenile"))
    p.add_argument("--video", help=T("source video for --audio-only (default: --out / output/<episode>.mp4)",
                                     "--audio-only için kaynak video (varsayılan: --out / output/<bölüm>.mp4)"))
    p.set_defaults(func=cmd)
