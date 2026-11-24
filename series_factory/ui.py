"""Local screen for a series: calendar, episodes, stock, ideas, TODO.

  series ui [--port 8765] [--no-open]      serve on http://127.0.0.1:<port> (only this computer can reach it)
  series calendar --html file.html         the same screen as one read-only file (no server)

There is no database: every request reads the series folder, and the few writes (planning an episode onto a date)
go through the same functions as the CLI, so the folder stays the single source of truth.
"""
import argparse, contextlib, datetime, io, json, mimetypes, os, sys, threading, urllib.parse, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import catalog, core, publish, schedule
from .i18n import T, lang

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
MEDIA_KINDS = ("frames", "carousel", "output", "cover")


# ---------------------------------------------------------------- data
def episodes():
    log = publish.load()
    out = []
    for b in catalog.episodes():
        if "plan" not in b:
            out.append({"no": b["folder"][:4], "error": b["error"]})
            continue
        o = catalog.episode_summary(b)
        ep, j = b["path"], b["plan"]
        frames = core.all_frame_files(j)
        have = [f for f in frames if os.path.exists(core.ep_path(ep, "frames", f))]
        slides = sorted(f for f in os.listdir(core.ep_path(ep, "carousel")) if f.endswith(".jpg") and not f.startswith("_")) \
            if os.path.isdir(core.ep_path(ep, "carousel")) else []
        k = log.get(o["no"], {})
        o.update(folder=b["folder"], frame_files=have, frames_total=len(frames), slides=slides,
                 thumb=have[0] if have else None, hook=j.get("hook", ""), summary=j.get("summary", ""),
                 publish={p: {"status": v.get("status"), "date": v.get("date"), "link": v.get("link")}
                          for p, v in k.get("platforms", {}).items()})
        out.append(o)
    return out


def snapshot(d0=None, d1=None):
    today = schedule.now().date()
    d0 = d0 or today - datetime.timedelta(days=today.weekday() + 7)
    d1 = d1 or d0 + datetime.timedelta(days=7 * 6 - 1)
    from . import ideas, todo
    try:
        idea_list = [{k: r[k] for k in ("code", "type", "title", "status", "group", "star", "episodes", "note")}
                     | {"format": core.format_for_idea(r["code"])} for r in ideas.derived()]
    except Exception:
        idea_list = []
    try:
        todos = [t for t in todo.items() if not t.get("archived")]
    except Exception:
        todos = []
    return {"series": core.cfg().get("name", ""), "lang": lang(), "generated": schedule.now().isoformat(timespec="minutes"),
            "calendar": schedule.calendar_data(d0, d1), "episodes": episodes(), "ideas": idea_list, "todo": todos,
            "platforms": list(publish.platforms())}


# ---------------------------------------------------------------- static file
def page():
    return open(os.path.join(HERE, "index.html"), encoding="utf-8").read()


def write_static(path, cal=None):
    data = snapshot()
    if cal:
        data["calendar"] = cal
    data["static"] = True
    html = page().replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    open(path, "w", encoding="utf-8").write(html)


# ---------------------------------------------------------------- server
def run_cli(argv):
    """Run a series command in-process; returns (ok, output)."""
    from . import cli
    buf = io.StringIO()
    ok = True
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            a = cli.build_parser().parse_args(argv)
            rc = a.func(a)
            ok = not rc
        except SystemExit as e:
            ok = e.code in (0, None)
            if e.code not in (0, None) and not isinstance(e.code, int):
                print(e.code)
    return ok, buf.getvalue().strip()


class Handler(BaseHTTPRequestHandler):
    lock = threading.Lock()

    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        b = body if isinstance(body, bytes) else (json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            if u.path == "/":
                return self.send(200, page(), "text/html; charset=utf-8")
            if u.path == "/api/all":
                d0 = schedule.parse_date(q["from"]) if q.get("from") else None
                d1 = schedule.parse_date(q["to"]) if q.get("to") else None
                with self.lock:
                    return self.send(200, snapshot(d0, d1))
            if u.path.startswith("/media/"):
                return self.media(u.path)
            return self.send(404, {"error": "not found"})
        except SystemExit as e:
            return self.send(400, {"error": str(e.code)})
        except Exception as e:
            return self.send(500, {"error": repr(e)})

    def media(self, p):
        # /media/<episode no>/<kind>/<file>
        parts = [urllib.parse.unquote(x) for x in p.split("/")[2:]]
        if len(parts) != 3 or parts[1] not in MEDIA_KINDS or "/" in parts[2] or parts[2].startswith("."):
            return self.send(400, {"error": "bad path"})
        ep = core.episode_dir(parts[0])
        f = core.ep_path(ep, parts[1], parts[2])
        if not os.path.isfile(f):
            return self.send(404, {"error": "no file"})
        size = os.path.getsize(f)
        ctype = mimetypes.guess_type(f)[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):        # video seeking
            a_, b_ = rng[6:].split("-")
            a_ = int(a_ or 0)
            b_ = min(int(b_) if b_ else size - 1, size - 1)
            with open(f, "rb") as fh:
                fh.seek(a_)
                data = fh.read(b_ - a_ + 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {a_}-{b_}/{size}")
        else:
            data = open(f, "rb").read()
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if self.headers.get("Origin") and not self.headers["Origin"].startswith(("http://127.0.0.1", "http://localhost")):
            return self.send(403, {"error": "origin"})
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if u.path != "/api/schedule":
            return self.send(404, {"error": "not found"})
        op = body.get("op")
        argv = ["schedule", op]
        if op in ("add", "move", "remove"):
            argv.append(str(body["episode"]))
        for k in ("date", "slot", "time", "note", "until"):
            if body.get(k):
                argv += [f"--{k}", str(body[k])]
        if body.get("force"):
            argv.append("--force")
        if body.get("dry_run"):
            argv.append("--dry-run")
        if op not in ("add", "move", "remove", "auto"):
            return self.send(400, {"error": "op"})
        with self.lock:
            ok, out = run_cli(argv)
        return self.send(200 if ok else 400, {"ok": ok, "output": out})


def serve(port=8765, open_browser=True):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(T(f"series ui: {url}  (Ctrl+C to stop)", f"series ui: {url}  (durdurmak için Ctrl+C)"))
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def cmd(a):
    serve(a.port, not a.no_open)
    return 0


def add_parser(sp):
    p = sp.add_parser("ui", help=T("local screen: calendar, episodes, stock, ideas", "yerel ekran: takvim, bölümler, stok, olaylar"))
    p.add_argument("--port", type=int, default=8765); p.add_argument("--no-open", action="store_true")
    p.set_defaults(func=cmd)
