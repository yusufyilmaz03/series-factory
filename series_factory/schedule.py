"""Publishing calendar: what went out when, what is scheduled, what is only planned, and where the gaps are.

Everything is read from the series folder; nothing here needs an AI model.

  series calendar [--from 2026-11-16] [--to 2026-12-31 | --weeks 4] [--slot noon] [--json] [--html file.html]
  series calendar --stock [--json]          per slot: ready stock, pipeline, and the date the stock runs out
  series schedule list                      planned (not yet sent to the scheduler) entries
  series schedule add 094 --date 2026-12-01 [--slot noon | --time 12:00] [--note ..] [--dry-run]
  series schedule move 094 --date 2026-12-03 [--slot ..]    · series schedule remove 094
  series schedule auto [--until 2026-12-31] [--slot noon] [--dry-run]   fill empty slots with ready episodes
  series views [--dry-run]                  views/<status>/<date>_<time>_<format>_<episode> shortcuts

Sources:
  publish log (publish add / publish sync)  -> published / scheduled, per platform
  schedule file (paths.schedule)            -> planned: an episode put on a date but not yet in the scheduler
  series.json "schedule"                    -> slots (time, days, formats), see docs/<lang>/series-config.md
  series.json "formats"                     -> label, counter, platforms, outputs of each episode format
"""
import datetime, json, os, re, sys

from . import catalog, core, publish
from .i18n import T, lang

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_NAMES = {"en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"), "tr": ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")}
MONTHS_TR = ("", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")


# ---------------------------------------------------------------- config
def sched_cfg():
    return core.cfg().get("schedule", {})


def slots():
    """{key: {label, time, days: [mon..], formats: [...], weekday_formats: {mon: [...]}}} sorted by time."""
    s = sched_cfg().get("slots") or {"main": {"label": T("daily", "günlük"), "time": "18:00", "days": "daily",
                                             "formats": list(core.formats())}}
    out = {}
    for k, v in sorted(s.items(), key=lambda x: x[1].get("time", "")):
        d = v.get("days", "daily")
        days = list(DAYS) if d in ("daily", "*", None) else [x.lower()[:3] for x in d]
        out[k] = {**v, "days": days, "formats": v.get("formats") or list(core.formats())}
    return out


def fmt_label(k):
    return core.formats().get(k, {}).get("label", k)


def fmt_platforms(k):
    return core.formats().get(k, {}).get("platforms") or list(publish.platforms())


def now():
    tz = core.cfg().get("timezone")
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo(tz)).replace(tzinfo=None) if tz else datetime.datetime.now()
    except Exception:
        return datetime.datetime.now()


def parse_dt(s):
    s = (s or "").replace("T", " ")
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s[:len(datetime.datetime(2000, 1, 1).strftime(f))], f)
        except ValueError:
            continue
    return None


def parse_date(s):
    if s in ("today", "bugun", "bugün"):
        return now().date()
    try:
        return datetime.date.fromisoformat(s)
    except (TypeError, ValueError):
        sys.exit(T(f"date not understood: {s} (YYYY-MM-DD)", f"tarih anlaşılmadı: {s} (YYYY-AA-GG)"))


# ---------------------------------------------------------------- schedule file (planned entries)
def sched_path():
    return core.series_path("schedule")


def load_sched():
    d = core.read_json(sched_path(), {}) or {}
    return d.get("entries", [])


def save_sched(entries):
    p = sched_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    entries = sorted(entries, key=lambda e: (e["date"], e.get("time", ""), e["episode"]))
    core.write_json(p, {"_note": T("Planned publishing (not yet in the scheduler). Written with 'series schedule'.",
                                   "Planlanan yayınlar (henüz zamanlayıcıda değil). 'series schedule' ile yazılır."),
                        "entries": entries})


# ---------------------------------------------------------------- the merged picture
def episode_index():
    """{no: {no, folder, path, title, format, stage, ready, ...}} for every episode."""
    out = {}
    for b in catalog.episodes():
        if "plan" not in b:
            continue
        o = catalog.episode_summary(b)
        o.update(folder=b["folder"], path=b["path"])
        out[o["no"]] = o
    return out


def slot_for(time_, fmt):
    """Slot key for a time; a time that matches no slot goes to the slot that carries the format (or None)."""
    S = slots()
    for k, v in S.items():
        if v.get("time") == time_:
            return k
    return next((k for k, v in S.items() if fmt in v["formats"]), None)


def entries(eps=None):
    """Every dated entry: published and scheduled ones from the publish log, planned ones from the schedule file.
    [{episode, date, time, slot, format, status, platforms: {p: status}, source}]"""
    eps = eps if eps is not None else episode_index()
    log = publish.load()
    assume = sched_cfg().get("assume_published", True)
    t_now = now()
    out = []
    for no, k in log.items():
        pl = k.get("platforms", {})
        dts = [parse_dt(v.get("date")) for v in pl.values() if v.get("date")]
        dts = [x for x in dts if x]
        if not dts:
            continue
        dt = min(dts)
        fmt = eps.get(no, {}).get("format") or core.default_format()
        pst = {}
        for p, v in pl.items():
            st = v.get("status")
            if st == "scheduled" and assume and (parse_dt(v.get("date")) or dt) <= t_now:
                st = "published"
            pst[p] = st
        status = "published" if any(x == "published" for x in pst.values()) else "scheduled"
        out.append({"episode": no, "date": dt.date().isoformat(), "time": dt.strftime("%H:%M"),
                    "slot": slot_for(dt.strftime("%H:%M"), fmt), "format": fmt, "status": status,
                    "platforms": pst, "missing_platforms": [p for p in fmt_platforms(fmt) if p not in pl],
                    "source": "log"})
    logged = set(log)
    for e in load_sched():
        if e["episode"] in logged:
            continue
        fmt = eps.get(e["episode"], {}).get("format") or core.default_format()
        S = slots()
        time_ = e.get("time") or S.get(e.get("slot"), {}).get("time", "")
        out.append({"episode": e["episode"], "date": e["date"], "time": time_, "slot": e.get("slot") or slot_for(time_, fmt),
                    "format": fmt, "status": "planned", "platforms": {}, "missing_platforms": fmt_platforms(fmt),
                    "note": e.get("note", ""), "source": "schedule"})
    out.sort(key=lambda e: (e["date"], e["time"], e["episode"]))
    # per-format counter (Episode 1, Theory 7 ...): order of appearance on the calendar
    seen = {}
    for e in out:
        f = core.formats().get(e["format"], {})
        c = f.get("counter") or {}
        n = seen.get(e["format"], int(c.get("start", 1)))
        seen[e["format"]] = n + 1
        e["number"] = n
        e["label"] = (c.get("label") or (fmt_label(e["format"]) + " {n}")).format(n=n)
    for e in out:
        ep = eps.get(e["episode"], {})
        e["title"] = ep.get("title", "")
        e["ready"] = ep.get("ready", False)
        e["stage"] = ep.get("stage", "")
        e["folder"] = ep.get("folder", "")
    return out


def slot_days(slot, d0, d1):
    """Dates in [d0, d1] on which the slot runs."""
    S = slots()[slot]
    d = d0
    while d <= d1:
        if DAYS[d.weekday()] in S["days"]:
            yield d
        d += datetime.timedelta(days=1)


def calendar_data(d0, d1, only_slot=None):
    eps = episode_index()
    ents = entries(eps)
    S = slots()
    days = []
    by_day = {}
    for e in ents:
        by_day.setdefault(e["date"], []).append(e)
    d = d0
    today = now().date()
    while d <= d1:
        iso = d.isoformat()
        rows, used = [], set()
        for k, s in S.items():
            if only_slot and k != only_slot:
                continue
            if DAYS[d.weekday()] not in s["days"]:
                continue
            here = [e for e in by_day.get(iso, []) if e["slot"] == k]
            used.update(id(e) for e in here)
            if here:
                rows += [{"slot": k, "time": e["time"] or s["time"], **e} for e in here]
            else:
                rows.append({"slot": k, "time": s["time"], "status": "past_gap" if d < today else "gap", "episode": None,
                             "formats": allowed_formats(k, d)})
        for e in by_day.get(iso, []):
            if id(e) not in used and (not only_slot or e["slot"] == only_slot):
                rows.append({**e, "slot": e["slot"] or "other"})
        rows.sort(key=lambda r: r.get("time") or "")
        days.append({"date": iso, "weekday": DAY_NAMES.get(lang(), DAY_NAMES["en"])[d.weekday()], "rows": rows})
        d += datetime.timedelta(days=1)
    return {"from": d0.isoformat(), "to": d1.isoformat(), "today": today.isoformat(),
            "slots": {k: {"label": v.get("label", k), "time": v.get("time"), "formats": v["formats"]} for k, v in S.items()},
            "formats": {k: {"label": fmt_label(k)} for k in core.formats()},
            "days": days, "stock": stock_data(eps, ents)}


def allowed_formats(slot, d):
    s = slots()[slot]
    wf = s.get("weekday_formats", {}).get(DAYS[d.weekday()])
    return wf or s["formats"]


# ---------------------------------------------------------------- stock
def unassigned_ready(eps, ents, fmt):
    taken = {e["episode"] for e in ents}
    return sorted((o for o in eps.values() if o["format"] == fmt and o["ready"] and o["no"] not in taken),
                  key=lambda o: o["no"])


def stock_data(eps=None, ents=None):
    eps = eps if eps is not None else episode_index()
    ents = ents if ents is not None else entries(eps)
    from . import ideas as ideas_mod
    try:
        waiting = [r["code"] for r in ideas_mod.derived() if r["status"] == "waiting"]
    except Exception:
        waiting = []
    today = now().date()
    out = {}
    for k, s in slots().items():
        taken = {e["episode"] for e in ents}
        per_fmt = {}
        for f in s["formats"]:
            mine = [o for o in eps.values() if o["format"] == f and o["no"] not in taken]
            per_fmt[f] = {
                "ready": [o["no"] for o in mine if o["ready"]],
                "in_production": [o["no"] for o in mine if not o["ready"]],
                "by_stage": {st: sum(1 for o in mine if not o["ready"] and o["stage"] == st) for st in catalog.STAGES},
                "ideas_waiting": [c for c in waiting if core.format_for_idea(c) == f],
            }
        future = [e for e in ents if e["slot"] == k and e["date"] >= today.isoformat()]
        last = max([e["date"] for e in future] or [None], key=lambda x: x or "")
        ready_n = sum(len(v["ready"]) for v in per_fmt.values())
        # continuous coverage from today: each slot day is filled by its calendar entry, else by one ready episode
        dates = {e["date"] for e in ents if e["slot"] == k}
        left, covered, first_gap = ready_n, None, None
        for g in slot_days(k, today, today + datetime.timedelta(days=730)):
            if g.isoformat() in dates:
                covered = g
                continue
            if first_gap is None:
                first_gap = g.isoformat()
            if left > 0:
                left -= 1
                covered = g
                continue
            if g.isoformat() > (last or ""):
                break
        per_week = len(s["days"])
        runs_out = None
        for g in slot_days(k, today, today + datetime.timedelta(days=730)):
            if g.isoformat() not in dates:
                if ready_n == 0:
                    runs_out = g.isoformat()
                    break
                ready_n -= 1
        filled_until = covered or today - datetime.timedelta(days=1)
        out[k] = {"label": s.get("label", k), "time": s.get("time"), "per_week": per_week,
                  "scheduled_until": last, "scheduled_count": len(future),
                  "ready": sum(len(v["ready"]) for v in per_fmt.values()),
                  "runs_out": runs_out, "covered_until": filled_until.isoformat(),
                  "days_covered": (parse_date(runs_out) - today).days if runs_out else None,
                  "first_gap": first_gap, "formats": per_fmt}
    return out


# ---------------------------------------------------------------- printing
def _date_title(d):
    if lang() == "tr":
        return f"{d.day} {MONTHS_TR[d.month]} {d.year}"
    return d.strftime("%d %b %Y")


def status_mark(st):
    return {"published": T("published", "yayında"), "scheduled": T("scheduled", "planlı"),
            "planned": T("planned", "taslak"), "gap": T("EMPTY", "BOŞ"), "past_gap": T("(empty)", "(boş)")}.get(st, st)


def print_calendar(data):
    S = data["slots"]
    week = None
    for day in data["days"]:
        d = parse_date(day["date"])
        w = d.isocalendar()[1]
        if w != week:
            week = w
            end = min(d + datetime.timedelta(days=6 - d.weekday()), parse_date(data["to"]))
            print(f"\n== {T('Week', 'Hafta')} {w} · {_date_title(d)} – {_date_title(end)}")
        today = "▶" if day["date"] == data["today"] else " "
        first = True
        for r in day["rows"]:
            head = f"{today}{day['weekday']} {d.strftime('%d.%m')}" if first else " " * 10
            first = False
            sl = S.get(r["slot"], {}).get("label", r["slot"] or "")
            if not r.get("episode"):
                opts = "/".join(r.get("formats", []))
                print(f"{head}  {r['time']:<5} {sl[:8]:<8}  {status_mark(r['status'])}" + (f"  ({opts})" if r["status"] == "gap" else ""))
                continue
            pl = " ".join(f"{publish.SHORT.get(p, p[:2])}{'✓' if v == 'published' else '·'}" for p, v in r["platforms"].items())
            miss = (" " + T("missing: ", "eksik: ") + ",".join(publish.SHORT.get(p, p) for p in r["missing_platforms"])
                    if r["missing_platforms"] and r["status"] != "planned" else "")
            warn = "" if r.get("ready") or r["status"] == "published" else "  ⚠ " + T("not ready", "hazır değil") + f" ({catalog.stage_name(r.get('stage'))})"
            print(f"{head}  {r['time']:<5} {sl[:8]:<8}  {r['episode']:<4} {r['title'][:30]:<30} {r['label'][:18]:<18} "
                  f"{status_mark(r['status']):<8} {pl}{miss}{warn}")


def print_stock(st):
    for k, s in st.items():
        print(f"\n{s['label']} ({s['time']}, {T('per week', 'haftada')} {s['per_week']})")
        print("  " + T(f"scheduled/planned ahead: {s['scheduled_count']}", f"ileriye planlı: {s['scheduled_count']}")
              + (T(f" (until {s['scheduled_until']})", f" ({s['scheduled_until']} tarihine kadar)") if s["scheduled_until"] else ""))
        print("  " + T(f"ready, not on the calendar: {s['ready']}", f"hazır, takvimde değil: {s['ready']}"))
        if s["runs_out"]:
            print("  " + T(f"if the ready stock fills the gaps, the first empty day is {s['runs_out']} ({s['days_covered']} days from today)",
                           f"hazır stok boşlukları doldurursa ilk boş gün {s['runs_out']} (bugünden {s['days_covered']} gün)"))
        if s["first_gap"]:
            print("  " + T("first unplanned slot day: ", "ilk plansız kuşak günü: ") + s["first_gap"])
        for f, v in s["formats"].items():
            stages = ", ".join(f"{n} {catalog.stage_name(x)}" for x, n in v["by_stage"].items() if n)
            print(f"    {fmt_label(f)[:26]:<26} {T('ready', 'hazır')} {len(v['ready']):>3}  · {T('in production', 'üretimde')} "
                  f"{len(v['in_production']):>3}" + (f" ({stages})" if stages else "") + f"  · {T('ideas', 'olay')} {len(v['ideas_waiting'])}")


# ---------------------------------------------------------------- commands
def cmd_calendar(a):
    today = now().date()
    if a.stock:
        st = stock_data()
        if a.json:
            print(json.dumps(st, ensure_ascii=False, indent=1))
        else:
            print_stock(st)
        return 0
    d0 = parse_date(a.from_) if a.from_ else today - datetime.timedelta(days=today.weekday())
    d1 = parse_date(a.to) if a.to else d0 + datetime.timedelta(days=7 * (a.weeks or 4) - 1)
    data = calendar_data(d0, d1, a.slot)
    if a.html:
        from . import ui
        ui.write_static(a.html, data)
        print(T("written:", "yazıldı:"), a.html)
        return 0
    if a.json:
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0
    print_calendar(data)
    print()
    gaps = [(day["date"], r["slot"]) for day in data["days"] for r in day["rows"] if r["status"] == "gap"]
    if gaps:
        print(T(f"empty slots: {len(gaps)} (fill: series schedule auto)", f"boş kuşak: {len(gaps)} (doldurmak için: series schedule auto)"))
    return 0


def _episode_no(e):
    return catalog.episode_no(os.path.basename(core.episode_dir(e)))


def cmd_schedule(a):
    ents = load_sched()
    if a.op == "list":
        if not ents:
            print(T("no planned entries", "taslak plan yok"))
        eps = episode_index()
        for e in ents:
            o = eps.get(e["episode"], {})
            print(f"{e['date']} {e.get('time', ''):<5} {e.get('slot', ''):<8} {e['episode']:<4} {o.get('title', '?')[:34]:<34} "
                  f"{fmt_label(o.get('format', ''))}" + (f" · {e['note']}" if e.get("note") else ""))
        return 0
    if a.op == "auto":
        return auto(a)
    if not a.episode:
        sys.exit(T("episode needed", "bölüm no gerekli"))
    no = _episode_no(a.episode)
    if a.op == "remove":
        new = [e for e in ents if e["episode"] != no]
        if len(new) == len(ents):
            sys.exit(T(f"{no} is not in the schedule file", f"{no} taslak planda yok"))
        if not a.dry_run:
            save_sched(new)
        print(("[dry-run] " if a.dry_run else "") + T(f"{no} removed from the plan", f"{no} plandan çıkarıldı"))
        return 0
    if not a.date:
        sys.exit(T("--date needed", "--date gerekli"))
    d = parse_date(a.date).isoformat()
    fmt = core.episode_format(core.episode_dir(a.episode))
    S = slots()
    slot = a.slot or (slot_for(a.time, fmt) if a.time else next((k for k, v in S.items() if fmt in v["formats"]), None))
    if slot and slot not in S:
        sys.exit(T(f"unknown slot: {slot} ({', '.join(S)})", f"bilinmeyen kuşak: {slot} ({', '.join(S)})"))
    time_ = a.time or S.get(slot, {}).get("time", "")
    if no in publish.load():
        sys.exit(T(f"{no} is already in the publish log (scheduled/published); change it there",
                   f"{no} zaten yayın kaydında (planlı/yayında); oradan değiştir"))
    clash = [e for e in entries() if e["date"] == d and e["slot"] == slot and e["episode"] != no]
    if clash and not a.force:
        sys.exit(T(f"{d} {slot} is taken by {clash[0]['episode']}; --force to add anyway",
                   f"{d} {slot} kuşağında {clash[0]['episode']} var; yine de eklemek için --force"))
    new = [e for e in ents if e["episode"] != no] + [{"episode": no, "date": d, "time": time_, "slot": slot,
                                                      **({"note": a.note} if a.note else {})}]
    if not a.dry_run:
        save_sched(new)
    print(("[dry-run] " if a.dry_run else "") + f"{no} → {d} {time_} {S.get(slot, {}).get('label', slot or '')}")
    return 0


def auto(a):
    """Fill empty slot days from today (or --from) to --until with ready episodes, lowest number first.
    Slot with several formats: weekday_formats fixes each day (first format with stock; later ones are fallbacks);
    otherwise the format used longest ago."""
    today = now().date()
    d0 = parse_date(a.from_) if a.from_ else today
    d1 = parse_date(a.until) if a.until else today + datetime.timedelta(days=int(sched_cfg().get("horizon_days", 28)))
    eps = episode_index()
    ents = entries(eps)
    taken = {e["episode"] for e in ents}
    filled = {(e["date"], e["slot"]) for e in ents}
    last_used = {}
    for e in ents:
        last_used[(e["slot"], e["format"])] = max(last_used.get((e["slot"], e["format"]), ""), e["date"])
    new, S = [], slots()
    pool = {f: [o["no"] for o in unassigned_ready(eps, ents, f)] for f in core.formats()}
    for k in S:
        if a.slot and k != a.slot:
            continue
        for d in slot_days(k, d0, d1):
            if (d.isoformat(), k) in filled:
                continue
            wf = S[k].get("weekday_formats", {}).get(DAYS[d.weekday()])
            if wf:      # fixed day: the first format of the day's list that has stock (the rest are fallbacks)
                f = next((x for x in wf if pool.get(x)), None)
                if not f:
                    continue
            else:       # rotation: the format used longest ago in this slot
                cand = [x for x in S[k]["formats"] if pool.get(x)]
                if not cand:
                    continue
                f = min(cand, key=lambda x: last_used.get((k, x), ""))
            no = pool[f].pop(0)
            taken.add(no)
            last_used[(k, f)] = d.isoformat()
            new.append({"episode": no, "date": d.isoformat(), "time": S[k]["time"], "slot": k})
    for e in sorted(new, key=lambda e: (e["date"], e["time"])):
        print(f"{'[dry-run] ' if a.dry_run else ''}{e['date']} {e['time']} {S[e['slot']].get('label', e['slot'])}: "
              f"{e['episode']} {eps[e['episode']]['title'][:40]} ({fmt_label(eps[e['episode']]['format'])})")
    if not new:
        print(T("nothing to add (no empty slot with ready stock)", "eklenecek bir şey yok (boş kuşak ya da hazır stok yok)"))
    elif not a.dry_run:
        save_sched(load_sched() + new)
        print(T(f"{len(new)} entries planned → {core.rel(sched_path())}", f"{len(new)} kayıt planlandı → {core.rel(sched_path())}"))
    return 0


# ---------------------------------------------------------------- views (folder shortcuts)
def cmd_views(a):
    """views/{published,scheduled,planned}/<date>_<time>_<format>_<episode folder> and views/ready/<format>/<folder>:
    relative symlinks to the episode folders, rebuilt from scratch (only symlinks are removed)."""
    base = core.series_path("views")
    eps = episode_index()
    ents = entries(eps)
    want = {}
    for e in ents:
        o = eps.get(e["episode"])
        if not o:
            continue
        name = f"{e['date']}_{e['time'].replace(':', '')}_{e['format']}_{o['folder']}"
        want[os.path.join(base, e["status"], name)] = o["path"]
    for f in core.formats():
        for o in unassigned_ready(eps, ents, f):
            want[os.path.join(base, "ready", f, o["folder"])] = o["path"]
    if a.dry_run:
        for p in sorted(want):
            print(core.rel(p))
        return 0
    removed = 0
    for d, _, files in os.walk(base) if os.path.isdir(base) else []:
        for x in files + [y for y in os.listdir(d) if os.path.islink(os.path.join(d, y))]:
            p = os.path.join(d, x)
            if os.path.islink(p) and p not in want:
                os.unlink(p)
                removed += 1
    made = 0
    for p, target in want.items():
        os.makedirs(os.path.dirname(p), exist_ok=True)
        rel_ = os.path.relpath(target, os.path.dirname(p))
        if os.path.islink(p) and os.readlink(p) == rel_:
            continue
        if os.path.islink(p):
            os.unlink(p)
        os.symlink(rel_, p)
        made += 1
    print(T(f"views: {len(want)} shortcuts ({made} new, {removed} removed) → {core.rel(base)}",
            f"görünümler: {len(want)} kısayol ({made} yeni, {removed} kaldırıldı) → {core.rel(base)}"))
    return 0


def add_parser(sp):
    p = sp.add_parser("calendar", help=T("publishing calendar: published / scheduled / planned / gaps",
                                         "yayın takvimi: yayında / planlı / taslak / boş"))
    p.add_argument("--from", dest="from_"); p.add_argument("--to"); p.add_argument("--weeks", type=int)
    p.add_argument("--slot"); p.add_argument("--stock", action="store_true")
    p.add_argument("--json", action="store_true"); p.add_argument("--html")
    p.set_defaults(func=cmd_calendar)
    p = sp.add_parser("schedule", help=T("plan episodes onto dates (before the scheduler)", "bölümleri tarihlere planla (zamanlayıcıdan önce)"))
    p.add_argument("op", choices=["list", "add", "move", "remove", "auto"]); p.add_argument("episode", nargs="?")
    p.add_argument("--date"); p.add_argument("--slot"); p.add_argument("--time"); p.add_argument("--note")
    p.add_argument("--from", dest="from_"); p.add_argument("--until")
    p.add_argument("--dry-run", action="store_true"); p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_schedule)
    p = sp.add_parser("views", help=T("rebuild views/ shortcuts (published / scheduled / planned / ready)",
                                      "views/ kısayollarını yenile (yayında / planlı / taslak / hazır)"))
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_views)
