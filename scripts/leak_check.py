#!/usr/bin/env python3
"""Leak check: run before every commit (the pre-commit hook does it with --staged).

Fails on:
  - secret files: .env (except .env.example), *.onnx model weights, legacy private files (ayarlar.json, hf_medya.json,
    yayin.json), record/reference folders of a real series, backups, media files, anything over 5 MB
  - secret-looking text: API keys (Anthropic, Google, ElevenLabs), private keys, key/token assignments,
    Higgsfield CDN user paths, Google Drive folder links
  - names from the source series' canon
  - private values of real series folders, read at run time (never stored here):
      --series PATH (repeatable) and/or SERIES_LEAK_SERIES=path1:path2
      -> voice ids, .env values, Higgsfield media ids, private ids/CDN constants in a legacy pipeline/
    and extra strings, one per line, in ~/.config/series-factory/leak_list.txt (optional)
Known, deliberate mentions are listed in .leakallow ("<path glob> :: <regex>").

  python3 scripts/leak_check.py              every file git would commit (or every file if this is not a git repo)
  python3 scripts/leak_check.py --staged     only staged files (pre-commit)
  python3 scripts/leak_check.py --series "../My Series"
Exit code 1 when something is found. Values are never printed, only where they are.
"""
import argparse, fnmatch, glob, json, os, re, subprocess, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "build", "dist", ".claude"}
MEDIA = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif", ".mp3", ".wav", ".m4a", ".mp4", ".mov", ".onnx", ".pt")
MAX_BYTES = 5 * 1024 * 1024

FORBIDDEN_FILES = [
    (r"(^|/)\.env(\.[^/]*)?$", "secret file (.env)"),
    (r"\.onnx$|\.pt$", "model weights (download on first use, never commit)"),
    (r"(^|/)ayarlar\.json$", "legacy series settings (voice ids)"),
    (r"(^|/)hf_medya\.json$", "Higgsfield media ids"),
    (r"(^|/)yayin\.json$", "publish log of a real series"),
    (r"(^|/)(kayit|Referans|GoogleDrive|_to_delete|_tmp_onizleme)/", "folder of a real series"),
    (r"(^|/)_yedek_", "backup folder"),
]
ALLOWED_FILES = [r"(^|/)\.env\.example$"]

PATTERNS = [
    (r"sk-ant-[A-Za-z0-9_\-]{20,}", "Anthropic API key"),
    (r"AIza[0-9A-Za-z_\-]{35}", "Google API key"),
    (r"\bsk_[0-9a-f]{32,}\b", "ElevenLabs API key"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key"),
    (r"(?i)\b(api[_-]?key|secret|token|password)\b[\"']?\s*[:=]\s*[\"'][A-Za-z0-9_\-/+]{20,}[\"']", "key/token assignment"),
    (r"cloudfront\.net/user_[A-Za-z0-9]+", "Higgsfield CDN user path"),
    (r"drive\.google\.com/(?:drive/(?:u/\d/)?folders/|[^\s\"']*[?&]id=)[A-Za-z0-9_\-]{20,}", "Google Drive link with id"),
    # canon of the source series (the engine must stay series-independent)
    (r"Kapıyı Aç İnsan|Kapiyi Ac Insan|\bDuman\b|\bSultan\b|Karabaş|Şaşkın|Şarlo|Nermin Hanım", "source series name"),
]
PLACEHOLDER = re.compile(r"PUT_|YOUR_|your_|_HERE|example|buraya", re.I)


def git_files(staged):
    try:
        if staged:
            out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"], cwd=REPO,
                                 capture_output=True, text=True, check=True).stdout
        else:
            out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=REPO,
                                 capture_output=True, text=True, check=True).stdout
        return [f for f in out.split("\0") if f]
    except (OSError, subprocess.CalledProcessError):
        return None


def gitignore_rules():
    p = os.path.join(REPO, ".gitignore")
    rules = []
    for line in open(p, encoding="utf-8") if os.path.exists(p) else []:
        line = line.strip()
        if line and not line.startswith("#"):
            rules.append((line.startswith("!"), line.lstrip("!")))
    return rules


def ignored(rel_path, rules):
    """Minimal .gitignore matching (enough for this repo) for when there is no git repository yet."""
    parts = rel_path.split("/")
    result = False
    for neg, pat in rules:
        dir_only = pat.endswith("/")
        pat = pat.rstrip("/")
        anchored = "/" in pat
        hit = False
        for i in range(len(parts)):
            prefix, is_dir = "/".join(parts[:i + 1]), i < len(parts) - 1
            if dir_only and not is_dir:
                continue
            if (anchored and fnmatch.fnmatch(prefix, pat.lstrip("/"))) or (not anchored and fnmatch.fnmatch(parts[i], pat)):
                hit = True
                break
        if hit:
            result = not neg
    return result


def walk_files():
    out, rules = [], gitignore_rules()
    for d, dirs, files in os.walk(REPO):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.endswith(".egg-info")]
        for f in files:
            r = os.path.relpath(os.path.join(d, f), REPO).replace(os.sep, "/")
            if not ignored(r, rules):
                out.append(r)
    return out


def load_allow():
    p = os.path.join(REPO, ".leakallow")
    rules = []
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "::" in line:
                g, rx = (x.strip() for x in line.split("::", 1))
                rules.append((g, re.compile(rx)))
    return rules


def allowed(path, text, allow):
    return any(fnmatch.fnmatch(path, g) and rx.search(text) for g, rx in allow)


def _vals(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _vals(v)
    elif isinstance(x, list):
        for v in x:
            yield from _vals(v)
    elif isinstance(x, str):
        yield x


def private_values(series):
    """Private strings of a real series folder: voice ids, .env values, media ids, legacy constants."""
    vals = set()

    def add(v):
        v = (v or "").strip().strip("'\"")
        if len(v) >= 8 and not PLACEHOLDER.search(v):
            vals.add(v)

    for cfg in (os.path.join(series, "series.json"), os.path.join(series, "seri.json"), os.path.join(series, "pipeline", "ayarlar.json")):
        if os.path.exists(cfg):
            c = json.load(open(cfg, encoding="utf-8"))
            for v in (c.get("voices") or c.get("sesler") or {}).values():
                if isinstance(v, dict):
                    add(v.get("id"))
            hf = (c.get("paths") or {}).get("hf_media")
            if hf and os.path.exists(os.path.join(series, hf)):
                for v in _vals(json.load(open(os.path.join(series, hf), encoding="utf-8"))):
                    add(v)
    for env in (os.path.join(series, ".env"), os.path.join(series, "pipeline", ".env")):
        if os.path.exists(env):
            for line in open(env, encoding="utf-8"):
                if "=" in line and not line.strip().startswith("#"):
                    add(line.split("=", 1)[1])
    hf = os.path.join(series, "pipeline", "hf_medya.json")
    if os.path.exists(hf):
        for v in _vals(json.load(open(hf, encoding="utf-8"))):
            add(v)
    for py in glob.glob(os.path.join(series, "pipeline", "*.py")):
        for m in re.finditer(r"^[A-Z_]*(?:ID|CDN|KEY)[A-Z_]*\s*=\s*\"([^\"]{12,})\"", open(py, encoding="utf-8").read(), re.M):
            v = m.group(1)
            add(re.sub(r"^https?://[^/]+/", "", v).strip("/") or v)
    return vals


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--series", action="append", default=[])
    a = ap.parse_args()
    files = git_files(a.staged)
    if files is None:
        files = walk_files()
    series = a.series + [p for p in os.environ.get("SERIES_LEAK_SERIES", "").split(os.pathsep) if p]
    private = set()
    for s in series:
        if os.path.isdir(s):
            private |= private_values(s)
        else:
            print(f"warning: series folder not found: {s}")
    extra = os.path.expanduser("~/.config/series-factory/leak_list.txt")
    if os.path.exists(extra):
        private |= {line.strip() for line in open(extra, encoding="utf-8") if len(line.strip()) >= 6}
    allow = load_allow()
    me = os.path.relpath(os.path.abspath(__file__), REPO)
    found = []
    for f in sorted(files):
        p = os.path.join(REPO, f)
        if not os.path.isfile(p):
            continue
        rf = f.replace(os.sep, "/")
        if not any(re.search(x, rf) for x in ALLOWED_FILES):
            for rx, why in FORBIDDEN_FILES:
                if re.search(rx, rf):
                    found.append(f"{rf}: {why}")
        if rf.lower().endswith(MEDIA):
            found.append(f"{rf}: media file (series media never goes into the repo)")
            continue
        if os.path.getsize(p) > MAX_BYTES:
            found.append(f"{rf}: larger than 5 MB")
            continue
        try:
            text = open(p, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for rx, why in PATTERNS:
                m = re.search(rx, line)
                if m and rf not in (me, ".leakallow") and not allowed(rf, m.group(0), allow):
                    found.append(f"{rf}:{n}: {why}")
            for i, v in enumerate(sorted(private)):
                if v in line:
                    found.append(f"{rf}:{n}: private value of a series (#{i + 1}, not shown)")
    scope = "staged" if a.staged else "repository"
    if found:
        print(f"LEAK CHECK FAILED ({scope}, {len(files)} files, {len(private)} private values):")
        print("\n".join("  " + x for x in found))
        return 1
    print(f"leak check ok ({scope}: {len(files)} files, {len(private)} private values checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
