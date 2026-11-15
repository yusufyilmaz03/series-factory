"""Shared helpers: series root, settings, API keys, paths, HTTP, plan access, timing rules.

Series root resolution (first match wins):
  1. --series <path> on the command line (set_root)
  2. SERIES_ROOT environment variable
  3. the nearest folder at or above the current directory that contains series.json
The engine code never assumes where a series lives; everything series-specific comes from series_factory.json.
"""
import json, os, re, shutil, subprocess, sys, urllib.error, urllib.request

from . import i18n, profiles
from .i18n import T

CONFIG_NAME = "series.json"
LEGACY_CONFIG_NAMES = ("seri.json",)     # name used before the project was renamed; still read
_root = None
_cfg = None

# Folder / file names inside a series. A migrated legacy series keeps its Turkish names through series.json "layout".
DEFAULT_LAYOUT = {
    "plan": "script.json", "script_md": "script.md",
    "frames": "frames", "audio": "audio", "output": "output", "cover": "cover",
    "narration": "narration", "words": "words.json", "line": "line_{n:02d}",
    "timing_suffix": "_timing.json", "prompt_dir": "_prompt", "prompts_md": "_prompts.md", "guide": "_guide.md",
    "contact": "_contact.jpg", "hf_log": "_higgsfield.json", "old_frames": "_old", "prompt_file": "_prompt.md",
    "records": {"idea": "idea", "idea_group": "idea_group", "todo": "todo", "todo_section": "todo_section"},
    "docs_sync": ".project_sync.json",
}
DEFAULT_PATHS = {
    "episodes": "episodes", "docs": "docs", "records": "records", "audio_assets": "assets/audio",
    "asset_map": "assets/assets.json", "library": "assets/library.json", "references": "references",
    "incoming": "references/_incoming", "upload_staging": "references/_upload", "trash": "_trash",
    "preview": "_preview", "publish_log": "publish/publish.json", "drive_sync": "drive_sync",
    "hf_media": "hf_media.json", "image_usage_log": "assets/_image_usage.jsonl",
}


class Missing(SystemExit):
    pass


# ---------------------------------------------------------------- root and settings
def set_root(p):
    global _root, _cfg
    _root, _cfg = os.path.abspath(p), None


def config_file(folder):
    """The settings file of a series folder (series.json, or a legacy name), or None."""
    for n in (CONFIG_NAME,) + LEGACY_CONFIG_NAMES:
        p = os.path.join(folder, n)
        if os.path.exists(p):
            return p
    return None


def find_root(start=None, required=True):
    if _root:
        return _root
    env = os.environ.get("SERIES_ROOT")
    if env:
        return os.path.abspath(env)
    d = os.path.abspath(start or os.getcwd())
    while True:
        if config_file(d):
            return d
        up = os.path.dirname(d)
        if up == d:
            break
        d = up
    if required:
        raise Missing(T(f"No {CONFIG_NAME} found. Run inside a series folder, pass --series <path>, set SERIES_ROOT, "
                        "or create one with 'series init <folder>'.",
                        f"{CONFIG_NAME} bulunamadı. Bir seri klasöründe çalıştır, --series <yol> ver, SERIES_ROOT ayarla "
                        "ya da 'series init <klasör>' ile oluştur."))
    return None


def root():
    return find_root()


def cfg():
    """series.json (cached)."""
    global _cfg
    if _cfg is None:
        p = config_file(root()) or os.path.join(root(), CONFIG_NAME)
        _cfg = json.load(open(p, encoding="utf-8"))
        i18n.set_lang(_cfg.get("lang", "en"))
    return _cfg


def save_cfg(c):
    global _cfg
    p = config_file(root()) or os.path.join(root(), CONFIG_NAME)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, p)
    _cfg = c


def path(*p):
    """Path relative to the series root."""
    return os.path.join(root(), *p)


def rel(p):
    return os.path.relpath(p, root())


def series_path(key, *more):
    """A configured series folder/file (series.json -> paths), relative to the root."""
    return path(cfg().get("paths", {}).get(key, DEFAULT_PATHS[key]), *more)


def layout(key, **fmt):
    v = cfg().get("layout", {}).get(key, DEFAULT_LAYOUT[key])
    if isinstance(v, dict):
        return {**DEFAULT_LAYOUT[key], **v}
    return v.format(**fmt) if fmt else v


def profile():
    c = cfg()
    return profiles.get(c.get("profile", "vertical_short"), c.get("profile_overrides"))


def narrator():
    return cfg().get("narrator")


def display_name(code):
    """How a character code is written on screen (series.json characters.<CODE>.display_name)."""
    ch = cfg().get("characters", {}).get(code, {})
    return ch.get("display_name") or code.capitalize()


# ---------------------------------------------------------------- secrets
def key(name, required=True):
    """API key or private id: environment first, then <series root>/.env. Never written to code or output."""
    k = os.environ.get(name)
    env = path(".env")
    if not k and os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            if line.strip().startswith(name + "="):
                k = line.split("=", 1)[1].strip().strip('"').strip("'")
    if k and ("buraya" in k or "your_" in k.lower() or not k.strip()):
        k = None
    if not k and required:
        sys.exit(T(f"{name} not found. Add a '{name}=...' line to {env}.",
                   f"{name} bulunamadı. {env} dosyasına '{name}=...' satırını ekle."))
    return k


# ---------------------------------------------------------------- network / tools
def offline():
    return os.environ.get("SERIES_OFFLINE") == "1"


def http(method, url, headers=None, body=None, raw=None, timeout=300, raw_response=False):
    if offline():
        raise RuntimeError(T(f"network disabled (SERIES_OFFLINE=1): {url.split('?')[0]}",
                             f"ağ kapalı (SERIES_OFFLINE=1): {url.split('?')[0]}"))
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    h = {"Content-Type": "application/json"} if body is not None else {}
    h.update(headers or {})
    r = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            b = resp.read()
            return b if raw_response else json.loads(b)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {url.split('?')[0]}: {e.read().decode(errors='ignore')[:600]}")


def check_media_tools(*tools):
    missing = [t for t in (tools or ("ffmpeg", "ffprobe")) if not shutil.which(t)]
    if missing:
        sys.exit(T(f"Required tool not found: {', '.join(missing)}. On macOS (with subtitle support): "
                   "brew install ffmpeg-full, then add /opt/homebrew/opt/ffmpeg-full/bin to PATH "
                   "(Intel Mac: /usr/local/opt/ffmpeg-full/bin). If installed, add the ffmpeg/ffprobe folder to PATH.",
                   f"Gerekli araç bulunamadı: {', '.join(missing)}. macOS'ta altyazı destekli kurulum: "
                   "brew install ffmpeg-full; ardından /opt/homebrew/opt/ffmpeg-full/bin dizinini PATH'e ekle "
                   "(Intel Mac: /usr/local/opt/ffmpeg-full/bin). Kuruluysa ffmpeg ve ffprobe dizinini PATH'e ekle."))


def duration(p):
    check_media_tools("ffprobe")
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(T(f"Could not read duration ({p}): {r.stderr.strip()}",
                             f"Ses/video süresi okunamadı ({p}): {r.stderr.strip()}"))
    return float(r.stdout)


def write_json(p, d, indent=2):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=indent)
    os.replace(tmp, p)


def read_json(p, default=None):
    if not os.path.exists(p):
        return default
    return json.load(open(p, encoding="utf-8"))


# ---------------------------------------------------------------- episodes and plans
def episodes_dir():
    return series_path("episodes")


def episode_dir(e):
    """'001', '001_slug' or a full path -> episode folder."""
    if os.path.isdir(e):
        return os.path.abspath(e)
    base = episodes_dir()
    for d in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        if d == e or d.startswith(e + "_"):
            return os.path.join(base, d)
    sys.exit(T(f"Episode not found: {e}", f"Bölüm bulunamadı: {e}"))


def episode_no(folder):
    m = re.match(r"\d{3}[a-z]?", os.path.basename(folder))
    return m.group(0) if m else os.path.basename(folder)[:3]


def ep_path(ep, kind, *more):
    """Path inside an episode: kind = frames | audio | output | cover."""
    return os.path.join(ep, layout(kind), *more)


def plan_path(ep):
    return os.path.join(ep, layout("plan"))


def load_plan(ep):
    """Episode plan in the current (English, format 3) shape; legacy format-2 plans are converted in memory."""
    from .migrate import plan_to_v3
    return plan_to_v3(json.load(open(plan_path(ep), encoding="utf-8")))


def save_plan(ep, d):
    write_json(plan_path(ep), d)


def strip_tags(text):
    """Drop [emotion tags] from narration text."""
    return re.sub(r"\[[^\]]*\]\s*", "", text).strip()


def narration_text(d):
    return " ".join(strip_tags(s["narration"]) for s in d["scenes"])


def lines(d):
    """Spoken lines of characters other than the narrator, in order: [(n, scene, line)]"""
    out, n = [], 0
    for s in d["scenes"]:
        for r in s.get("dialogue", []):
            n += 1
            out.append((n, s, r))
    return out


def all_frame_files(d):
    k = [d["set_frame"]["file"]] if d.get("set_frame") else []
    return k + [x["file"] for s in d.get("scenes", []) for x in s.get("frames", [])]


# ---------------------------------------------------------------- timing rules (script, assemble, strips)
SPEECH_RATE = 2.0       # narration words per second (measured 1.94–2.16)
READ_SEC = 1.2          # minimum time for the viewer to find and understand one read
LINE_SEC = 1.2          # average duration of a short spoken line (gap included)
HOLD_MAX = 2.0
DEFAULT_TRANSITION = ("fade", 0.35)   # at scene starts; inside a scene "cut"
TRANSITIONS = {"cut", "fade", "fadeblack", "fadewhite", "dissolve", "slideleft", "slideright", "slideup", "slidedown",
               "smoothleft", "smoothright", "smoothup", "smoothdown", "wipeleft", "wiperight", "circleopen",
               "circleclose", "radial", "hblur"}
MOTIONS = {"in", "out", "panR", "panL", "fast", "static"}


def transition(frame, scene_start, first):
    """Entry transition into this frame -> (type, seconds). frame['transition']: "fade" or {"type", "duration"}."""
    if first:
        return ("cut", 0.0)          # the hook is the first frame: never open from black
    g = frame.get("transition")
    if g is None:
        return DEFAULT_TRANSITION if scene_start else ("cut", 0.0)
    if isinstance(g, str):
        return (g, 0.0 if g == "cut" else DEFAULT_TRANSITION[1])
    t = g.get("type", "fade")
    return (t, 0.0 if t == "cut" else float(g.get("duration", DEFAULT_TRANSITION[1])))


def frame_list(d):
    """Plan frames in order with estimated durations:
    [{scene, file, frame, words, lines, hold, est_sec, reads, scene_start, first}]"""
    out = []
    for s in d["scenes"]:
        sk = strip_tags(s["narration"]).split()
        frames = s["frames"]
        bounds = [0]
        for k in frames[1:]:
            bounds.append(sk.index(k["start_word"]) if k.get("start_word") in sk else len(sk))
        bounds.append(len(sk))
        rep = [0] * len(frames)
        for r in s.get("dialogue", []):
            y = r.get("at") or {}
            i = 0
            if "frame_start" in y:
                i = next((j for j, k in enumerate(frames) if k["file"] == y["frame_start"]), 0)
            elif "after_word" in y and y["after_word"] in sk:
                w = sk.index(y["after_word"])
                i = max(j for j in range(len(frames)) if bounds[j] <= w)
            rep[i] += 1
        for j, k in enumerate(frames):
            n = max(0, bounds[j + 1] - bounds[j])
            b = float(k.get("hold", 0) or 0)
            out.append({"scene": s["no"], "file": k["file"], "frame": k, "words": n, "lines": rep[j], "hold": b,
                        "est_sec": n / SPEECH_RATE + rep[j] * LINE_SEC + b,
                        "reads": k.get("reads") or [], "scene_start": j == 0, "first": not out})
    return out


# ---------------------------------------------------------------- output
def emit(data, as_json, text_lines=()):
    """Print either the JSON payload or the human summary."""
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=1))
    else:
        for line in text_lines:
            print(line)
