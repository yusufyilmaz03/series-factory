"""Voice + assemble + check several episodes with one command; one summary line per episode.

  series batch 013-017                 voice + assemble + check
  series batch 013 015 018 --only voice
  series batch 013-017 --only assemble
  series batch 013-017 --dry-run       nothing is produced: what would run, how many ElevenLabs characters it costs
  series batch 013-017 --background    run detached; progress: series batch --status

Order: (1) new sfx/music episode by episode (the same effect is never generated twice), (2) narration + lines for
--parallel episodes at once (default 3 = the ElevenLabs Starter concurrency limit for eleven_v4), (3) assemble 2 in
parallel, (4) `series check` warnings. Full output: <preview>/batch.log
"""
import json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

from . import core, voice
from .i18n import T


def _log():
    return core.series_path("preview", "batch.log")


def _state_file():
    return core.series_path("preview", "batch_state.json")


def episodes(args):
    out = []
    for a in args:
        if "-" in a and a.replace("-", "").isdigit():
            x, y = a.split("-")
            out += [f"{i:03d}" for i in range(int(x), int(y) + 1)]
        else:
            out.append(a)
    return out


def run_seri(*args):
    t0 = time.time()
    r = subprocess.run([sys.executable, "-m", "series_factory", "--series", core.root(), *args], capture_output=True, text=True)
    with open(_log(), "a", encoding="utf-8") as f:
        f.write(f"\n$ series {' '.join(args)}  ({time.time() - t0:.0f} s, code {r.returncode})\n{r.stdout}{r.stderr}")
    return r


def write_state(d):
    json.dump(d, open(_state_file(), "w"), ensure_ascii=False, indent=1)


def voice_ep(b):
    r = run_seri("voice", "episode", b, "--only", "narration,line")
    return b, r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()[-1:] if r.returncode else []


def assemble_ep(b):
    r = run_seri("assemble", b)
    return b, r.returncode == 0, (r.stderr or r.stdout).strip().splitlines()[-1:] if r.returncode else []


def summary(b):
    r = run_seri("check", b)
    rows = r.stdout.strip().splitlines()
    warn = [s.strip() for s in rows[1:] if "[timing]" in s or "[plan]" in s or "[zamanlama]" in s]
    return (rows[0] if rows else b), warn


def cmd(a):
    os.makedirs(os.path.dirname(_log()), exist_ok=True)
    if a.status:
        print(open(_state_file()).read() if os.path.exists(_state_file()) else T("no batch record", "toplu iş kaydı yok"))
        return 0
    bl = episodes(a.episodes)
    if not bl:
        sys.exit(T("give episodes: 013-017", "bölüm ver: 013-017"))
    if a.dry_run:
        total, rows = 0, []
        for b in bl:
            n, sfx = voice.estimate(b)
            total += n
            rows.append({"episode": b, "characters": n, "new_sfx": sfx})
        core.emit({"episodes": rows, "total_characters": total}, a.json,
                  [f"{r['episode']}: {r['characters']} {T('characters', 'karakter')}"
                   + (T(f", new sfx: {', '.join(r['new_sfx'])}", f", yeni efekt: {', '.join(r['new_sfx'])}") if r["new_sfx"] else "")
                   for r in rows]
                  + [T(f"total ≈ {total} characters (narration + lines; sfx/music use credit separately)",
                       f"toplam ≈ {total} karakter (anlatım + replik; efekt/müzik ayrıca kredi harcar)")])
        return 0
    if a.only != "voice":
        core.check_media_tools()
    if a.background:
        args = [sys.executable, "-m", "series_factory", "--series", core.root(), "batch", *bl] + \
               (["--only", a.only] if a.only else []) + ["--parallel", str(a.parallel)]
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        print(T("started in the background; progress: series batch --status",
                "arka planda başladı; ilerleme: series batch --status"))
        return 0

    t0 = time.time()
    st = {"started": time.strftime("%H:%M:%S"), "episodes": {b: "waiting" for b in bl}, "done": False}
    write_state(st)
    open(_log(), "a").write(f"\n===== batch {' '.join(bl)} {st['started']} =====\n")
    err = {}
    if a.only in (None, "voice"):
        for b in bl:                                  # sfx + music: in order (shared library)
            st["episodes"][b] = "sfx/music"
            write_state(st)
            r = run_seri("voice", "episode", b, "--only", "sfx,music")
            if r.returncode:
                err[b] = "sfx/music: " + (r.stderr.strip().splitlines() or ["?"])[-1]
        with ThreadPoolExecutor(a.parallel) as ex:
            for b, ok, last in ex.map(voice_ep, [b for b in bl if b not in err]):
                st["episodes"][b] = "voice ok" if ok else "voice ERROR"
                write_state(st)
                if not ok:
                    err[b] = "voice: " + " ".join(last)
    if a.only in (None, "assemble"):
        with ThreadPoolExecutor(2) as ex:
            for b, ok, last in ex.map(assemble_ep, [b for b in bl if b not in err]):
                st["episodes"][b] = "assemble ok" if ok else "assemble ERROR"
                write_state(st)
                if not ok:
                    err[b] = "assemble: " + " ".join(last)
    result = []
    for b in bl:
        if b in err:
            result.append(f"✗ {b}  {err[b][:160]}")
            continue
        head, warn = summary(b)
        result.append(f"✓ {head}" + ((f"\n    {T('warning', 'uyarı')}: " + f"\n    {T('warning', 'uyarı')}: ".join(u[:120] for u in warn)) if warn else ""))
    st["done"] = True
    st["result"] = result
    st["seconds"] = int(time.time() - t0)
    write_state(st)
    print("\n".join(result))
    print(T(f"time {int(time.time() - t0)} s · details: {core.rel(_log())}", f"süre {int(time.time() - t0)} sn · ayrıntı: {core.rel(_log())}"))
    return 0


def add_parser(sp):
    p = sp.add_parser("batch", help=T("voice + assemble + check several episodes", "birden fazla bölümü seslendir + montajla + kontrol et"))
    p.add_argument("episodes", nargs="*"); p.add_argument("--only", choices=["voice", "assemble"])
    p.add_argument("--parallel", type=int, default=3); p.add_argument("--dry-run", action="store_true")
    p.add_argument("--background", action="store_true"); p.add_argument("--status", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd)
