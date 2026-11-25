"""Job queue: series commands that run on the series computer itself, sent from anywhere that can write the folder.

  series jobs add assemble 013            queue a command (no shell: the words after 'add' are a series command)
  series jobs list [--all] [--json]       recent jobs and their state
  series jobs log <id> [--tail 40]        output of a job
  series jobs cancel <id>                 drop a queued job or stop a running one
  series jobs worker                      run queued jobs in the foreground (series ui runs the same worker)

Why: a remote session (a phone chat, a sandbox) can read and write the series folder but cannot keep a long render
running. A job is a small JSON file in <preview>/jobs/; the worker inside 'series ui' (or 'series jobs worker') on
the computer that owns the folder picks it up, runs it with its own Python and full speed, and writes the state and
the output next to it. One job runs at a time; 'batch' parallelises inside itself.

Only series commands run, as an argument list (never through a shell), and a few commands are refused (ui, jobs,
init, migrate).
"""
import argparse, datetime, json, os, secrets, signal, subprocess, sys, threading, time

from . import core
from .i18n import T

DENY = {"ui", "jobs", "init", "migrate"}
POLL = 2.0
STATES = ("queued", "running", "done", "failed", "cancelled", "interrupted")


def jobs_dir():
    d = core.series_path("preview", "jobs")
    os.makedirs(d, exist_ok=True)
    return d


def _p(jid, ext="json"):
    return os.path.join(jobs_dir(), f"{jid}.{ext}")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _write(job):
    tmp = _p(job["id"], "json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _p(job["id"]))


def load(jid):
    try:
        return json.load(open(_p(jid), encoding="utf-8"))
    except (OSError, ValueError):
        return None


def all_jobs():
    out = []
    for f in sorted(os.listdir(jobs_dir()), reverse=True):
        if f.endswith(".json"):
            j = load(f[:-5])
            if j:
                out.append(j)
    return out


def check_argv(argv):
    """The argument list of a series command, or SystemExit with the reason."""
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
        raise SystemExit(T("a job is a series command as a list of words", "iş, kelime listesi olarak bir series komutudur"))
    if any("\0" in x or "\n" in x for x in argv) or sum(map(len, argv)) > 2000:
        raise SystemExit(T("bad characters or too long", "geçersiz karakter ya da çok uzun"))
    if argv[0] in DENY or argv[0].startswith("-"):
        raise SystemExit(T(f"'{argv[0]}' cannot run as a job", f"'{argv[0]}' iş olarak çalıştırılamaz"))
    from . import cli
    names = set()
    for act in cli.build_parser()._actions:
        if isinstance(act, argparse._SubParsersAction):
            names |= set(act.choices)
    if argv[0] not in names:
        raise SystemExit(T(f"unknown command: {argv[0]}", f"bilinmeyen komut: {argv[0]}"))
    return argv


def add(argv, by=""):
    check_argv(argv)
    jid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)
    job = {"id": jid, "argv": argv, "state": "queued", "created": _now(), "by": by}
    _write(job)
    return job


def cancel(jid):
    j = load(jid)
    if not j:
        raise SystemExit(T(f"no job {jid}", f"iş yok: {jid}"))
    if j["state"] not in ("queued", "running"):
        return j
    open(_p(jid, "cancel"), "w").close()          # the worker acts on it (it owns the job file once running)
    return j


def tail(jid, n=40):
    p = _p(jid, "log")
    if not os.path.exists(p):
        return ""
    with open(p, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 64000))
        lines = f.read().decode("utf-8", "replace").splitlines()
    return "\n".join(lines[-n:])


# ---------------------------------------------------------------- worker
def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def recover():
    """Jobs left 'running' by a worker that is gone: interrupted."""
    for j in all_jobs():
        if j["state"] == "running" and not (j.get("host") == _host() and _alive(j.get("pid"))):
            j.update(state="interrupted", ended=_now())
            _write(j)


def _host():
    import socket
    return socket.gethostname()


def run_one(j, stop=None):
    """Run a queued job to its end; returns the final job record."""
    if os.path.exists(_p(j["id"], "cancel")):
        os.remove(_p(j["id"], "cancel"))
        j.update(state="cancelled", ended=_now())
        _write(j)
        return j
    log = open(_p(j["id"], "log"), "a", encoding="utf-8")
    log.write(f"$ series {' '.join(j['argv'])}\n")
    log.flush()
    t0 = time.time()
    proc = subprocess.Popen([sys.executable, "-m", "series_factory", "--series", core.root(), *j["argv"]],
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True,
                            env={**os.environ, "PYTHONUNBUFFERED": "1"})
    j.update(state="running", started=_now(), pid=proc.pid, host=_host())
    _write(j)
    cancelled = False
    while proc.poll() is None:
        if os.path.exists(_p(j["id"], "cancel")) or (stop and stop.is_set()):
            cancelled = True
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                pass
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
            break
        time.sleep(0.5)
    rc = proc.wait()
    log.write(f"\n[exit {rc}, {time.time() - t0:.0f} s]\n")
    log.close()
    if os.path.exists(_p(j["id"], "cancel")):
        os.remove(_p(j["id"], "cancel"))
    state = "cancelled" if cancelled and not (stop and stop.is_set()) else "interrupted" if cancelled else \
        "done" if rc == 0 else "failed"
    j.update(state=state, code=rc, ended=_now(), seconds=int(time.time() - t0))
    j.pop("pid", None)
    _write(j)
    return j


def next_queued():
    q = [j for j in all_jobs() if j["state"] == "queued"]
    return min(q, key=lambda j: j["id"]) if q else None


def work(stop=None, once=False):
    """Run queued jobs, oldest first, one at a time, until stop is set."""
    recover()
    while not (stop and stop.is_set()):
        j = next_queued()
        if j:
            run_one(j, stop)
            if once:
                return
            continue
        if once:
            return
        time.sleep(POLL)


def start_thread():
    stop = threading.Event()
    th = threading.Thread(target=work, args=(stop,), daemon=True, name="series-jobs")
    th.start()
    return stop


# ---------------------------------------------------------------- CLI
def _line(j):
    dur = f" {j['seconds']} s" if j.get("seconds") is not None else ""
    return f"{j['id']}  {j['state']:<11} series {' '.join(j['argv'])}{dur}"


def cmd(a):
    if a.op != "add":                               # options after the operation (REMAINDER keeps them in rest)
        q = argparse.ArgumentParser(prog=f"series jobs {a.op}")
        q.add_argument("id", nargs="?"); q.add_argument("--json", action="store_true")
        q.add_argument("--all", action="store_true"); q.add_argument("--tail", type=int, default=a.tail)
        q.add_argument("--once", action="store_true")
        o = q.parse_args(a.rest)
        a.json, a.all, a.tail, a.once = a.json or o.json, a.all or o.all, o.tail, a.once or o.once
        a.rest = [o.id] if o.id else []
    if a.op == "add":
        argv = a.rest[1:] if a.rest[:1] == ["--"] else a.rest
        j = add(argv, by=a.by or "")
        core.emit(j, a.json, [T(f"queued {j['id']}: series {' '.join(argv)}  (runs on the computer where 'series ui' is open)",
                                f"sıraya alındı {j['id']}: series {' '.join(argv)}  ('series ui' açık olan bilgisayarda çalışır)")])
        return 0
    if a.op == "list":
        js = all_jobs()
        js = js if a.all else js[:15]
        core.emit(js, a.json, [_line(j) for j in js] or [T("no jobs", "iş yok")])
        return 0
    if a.op == "log":
        if not a.rest:
            raise SystemExit(T("give a job id", "iş kimliği ver"))
        j = load(a.rest[0])
        if not j:
            raise SystemExit(T(f"no job {a.rest[0]}", f"iş yok: {a.rest[0]}"))
        core.emit({**j, "log": tail(j["id"], a.tail)}, a.json, [_line(j), tail(j["id"], a.tail)])
        return 0
    if a.op == "cancel":
        if not a.rest:
            raise SystemExit(T("give a job id", "iş kimliği ver"))
        j = cancel(a.rest[0])
        print(T(f"cancel requested: {j['id']} ({j['state']})", f"iptal istendi: {j['id']} ({j['state']})"))
        return 0
    if a.op == "worker":
        print(T(f"job worker: {core.rel(jobs_dir())} (Ctrl+C to stop)", f"iş çalıştırıcı: {core.rel(jobs_dir())} (durdurmak için Ctrl+C)"))
        try:
            work(once=a.once)
        except KeyboardInterrupt:
            pass
        return 0
    return 1


def add_parser(sp):
    p = sp.add_parser("jobs", help=T("job queue: run series commands on the series computer from anywhere",
                                     "iş kuyruğu: series komutlarını her yerden seri bilgisayarında çalıştır"))
    p.add_argument("op", choices=["add", "list", "log", "cancel", "worker"])
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.add_argument("--json", action="store_true"); p.add_argument("--all", action="store_true")
    p.add_argument("--tail", type=int, default=40); p.add_argument("--by")
    p.add_argument("--once", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd)
