"""Publish log (single source): episode -> final video + sha + per-platform status. And Drive staging.

  series publish list [001]
  series publish add 001 --video f.mp4 --platform instagram --status scheduled --date 2026-11-15 [--dry-run]
        the first "published" also sets the idea status to "published (episode NNN)"
  series drive prepare 005 008 | 005-008     copy video + cover into the Drive sync folder (paths.drive_sync)
  series drive list                          what is in the folder, per episode
  series drive clean                         move files published on every platform to the trash
series.json: "publish": {"platforms": ["instagram", "tiktok", "youtube"]}; Drive folder id: DRIVE_FOLDER_ID in .env
(only printed as a hint for the Drive tools; never committed).
"""
import datetime, glob, hashlib, json, os, re, shutil, sys

from . import catalog, core
from .i18n import T
from .migrate import publish_to_v2

SHORT = {"instagram": "ig", "tiktok": "tt", "youtube": "yt"}
STATUS_ALIASES = {"planlandi": "scheduled", "yayinda": "published"}


def platforms():
    return tuple(core.cfg().get("publish", {}).get("platforms", ["instagram", "tiktok", "youtube"]))


def log_path():
    return os.environ.get("SERIES_PUBLISH_LOG") or core.series_path("publish_log")


def load():
    p = log_path()
    return publish_to_v2(json.load(open(p, encoding="utf-8"))).get("episodes", {}) if os.path.exists(p) else {}


def save(d):
    p = log_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"_note": "Publish log (single source). Written with 'series publish add', not by hand.",
                   "episodes": dict(sorted(d.items()))}, f, ensure_ascii=False, indent=2)
        f.write("\n")


def video_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()[:16]


def find_video(ep, v):
    for p in (v, core.path(v), core.ep_path(ep, "output", v)):
        if os.path.isfile(p):
            return os.path.abspath(p)
    sys.exit(T(f"video not found: {v}", f"video bulunamadı: {v}"))


def final_video(ep):
    """Final video: output/<folder>.mp4; else the newest output (…_vN.mp4 versions are only backups)."""
    main = core.ep_path(ep, "output", os.path.basename(ep) + ".mp4")
    if os.path.isfile(main):
        return main
    c = sorted(glob.glob(core.ep_path(ep, "output", "*.mp4")), key=os.path.getmtime)
    return c[-1] if c else None


def cell(k):
    """short cell for the status table: 'ig:P tt:S' (P published, S scheduled)"""
    pl = (k or {}).get("platforms", {})
    return " ".join(f"{SHORT.get(p, p[:2])}:{T('P', 'Y') if pl[p].get('status') == 'published' else T('S', 'P')}"
                    for p in platforms() if p in pl) or "-"


def counts(d):
    y = sum(any(v.get("status") == "published" for v in k.get("platforms", {}).values()) for k in d.values())
    return y, len(d) - y


def today():
    tz = core.cfg().get("timezone")
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo(tz)).date().isoformat() if tz else datetime.date.today().isoformat()
    except Exception:
        return datetime.date.today().isoformat()


def idea_published(no, ep, dry):
    from . import ideas
    codes = ideas.codes_in(core.load_plan(ep).get("source_idea"))
    if not codes:
        print(T("(no source_idea in the plan; idea status unchanged)", "(planda source_idea yok; olay durumu değişmedi)"))
        return
    pool, _ = ideas.parse()
    for code in codes:
        o = next((x for x in pool if x["code"] == code), None)
        m = re.match(ideas.L("published_re"), o["status"]) if o else None
        eps = ", ".join(dict.fromkeys((m.group(1).split(", ") if m else []) + [no]))
        status = ideas.L("published_fmt").format(eps=eps)
        if dry:
            print(f"[{T('dry-run', 'kuru')}] idea-status {code} \"{status}\"")
            continue
        try:
            ideas.set_status(code, status)
        except SystemExit as e:
            print(T(f"WARNING: could not write the status of {code}: {e}", f"UYARI: {code} olay durumu yazılamadı: {e}"))


def cmd_publish(a):
    d = load()
    P = platforms()
    if a.op == "list":
        if a.episode:
            no = catalog.episode_no(os.path.basename(core.episode_dir(a.episode)))
            k = d.get(no)
            if not k:
                sys.exit(T(f"{no}: no publish record", f"{no}: yayın kaydı yok"))
            print(f"{no} video: {k['video']} (sha {k['sha']})")
            for p in P:
                v = k.get("platforms", {}).get(p)
                if v:
                    print(f"  {p}: {v.get('status')} {v.get('date') or ''} · metricool_id {v.get('metricool_id') or '—'} · link {v.get('link') or '—'}")
            return 0
        print(f"{'no':<6}{'video':<36}{'sha':<18}" + "".join(f"{p:<14}" for p in P) + T("note", "not"))
        for no, k in sorted(d.items()):
            pl = k.get("platforms", {})
            h = [(f"{T('P', 'Y') if pl[p].get('status') == 'published' else T('S', 'P')} {(pl[p].get('date') or '')[:10]}".strip()
                  if p in pl else "-") for p in P]
            vp = core.path(k["video"])
            nt = T("no video", "video yok") if not os.path.isfile(vp) else (T("video CHANGED", "video DEĞİŞMİŞ") if video_sha(vp) != k["sha"] else "")
            print(f"{no:<6}{os.path.basename(k['video'])[:34]:<36}{k['sha']:<18}" + "".join(f"{x:<14}" for x in h) + nt)
        y, p_ = counts(d)
        print(T(f"\nrecords: {len(d)} episodes — {y} published, {p_} only scheduled",
                f"\nkayıt: {len(d)} bölüm — {y} yayında, {p_} yalnız planlı"))
        ready = [catalog.episode_no(b["folder"]) for b in catalog.episodes() if "plan" in b
                 and catalog.episode_no(b["folder"]) not in d and glob.glob(core.ep_path(b["path"], "output", "*.mp4"))]
        if ready:
            print(T("video ready, not recorded: ", "videosu hazır, kayıtsız: ") + catalog.ranges(ready))
        return 0
    # add
    if not a.episode:
        sys.exit(T("episode needed: publish add 001 --platform instagram --status scheduled --date 2026-11-15",
                   "bölüm no gerekli: publish add 001 --platform instagram --status scheduled --date 2026-11-15"))
    if not a.platform:
        sys.exit(T(f"--platform needed ({' '.join(P)} | all)", f"--platform gerekli ({' '.join(P)} | all)"))
    status = STATUS_ALIASES.get(a.status, a.status)
    ep = core.episode_dir(a.episode)
    no = catalog.episode_no(os.path.basename(ep))
    pl = list(P) if "all" in a.platform else a.platform
    k = d.get(no, {})
    if a.video:
        v = find_video(ep, a.video)
    elif k.get("video") and os.path.isfile(core.path(k["video"])):
        v = core.path(k["video"])
    else:
        v = final_video(ep) or sys.exit(T(f"{no}: no video in output/; give --video <file>", f"{no}: çıktı klasöründe video yok; --video <dosya> ver"))
    new_sha, rel_ = video_sha(v), core.rel(v)
    old = k.get("platforms", {})
    was_published = any(x.get("status") == "published" for x in old.values())
    if k.get("sha") and k["sha"] != new_sha and was_published and not a.force:
        sys.exit(T(f"{no}: this file differs from the recorded (published) video (sha {k['sha']} → {new_sha}); use --force on purpose",
                   f"{no}: kayıtlı (yayınlanmış) videodan farklı bir dosya veriyorsun (sha {k['sha']} → {new_sha}); bilerek güncelleyeceksen --force"))
    date = a.date or (today() if status == "published" else None)
    if not date:
        sys.exit(T("--date needed (for scheduled), e.g. 2026-11-15 or '2026-11-15 18:00'",
                   "--date gerekli (planlandı için), ör. 2026-11-15 ya da '2026-11-15 18:00'"))
    if not re.match(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2})?$", date):
        sys.exit(T("--date format: YYYY-MM-DD or 'YYYY-MM-DD HH:MM'", "--date biçimi: YYYY-AA-GG ya da 'YYYY-AA-GG SS:DD'"))
    new = {p: dict(v_) for p, v_ in old.items()}
    for p in pl:
        e = new.get(p, {})
        if e.get("status") == "published" and status == "scheduled" and not a.force:
            sys.exit(T(f"{no} {p}: already published; --force to roll back", f"{no} {p}: zaten yayında; geri almak için --force"))
        new[p] = {"status": status, "date": date, "metricool_id": a.metricool_id or e.get("metricool_id"), "link": a.link or e.get("link")}
    d[no] = {"video": rel_, "sha": new_sha, "platforms": {p: new[p] for p in P if p in new}}
    summ = f"{no}: " + ", ".join(f"{p} {status} {date}" for p in pl) + f" · video {rel_} · sha {new_sha}"
    if a.dry_run:
        print(f"[{T('dry-run', 'kuru')}] " + summ)
    else:
        save(d)
        print(summ)
    if status == "published" and not was_published:
        idea_published(no, ep, a.dry_run)
    return 0


# ---------------------------------------------------------------- Drive staging
def drive_folder():
    return core.series_path("drive_sync")


def numbers(args):
    out = []
    for a in args:
        m = re.fullmatch(r"(\d{1,3})-(\d{1,3})", a)
        if m:
            out += [f"{i:03d}" for i in range(int(m[1]), int(m[2]) + 1)]
        elif re.fullmatch(r"\d{1,3}[a-z]?", a):
            out.append(a.zfill(3) if a.isdigit() else a.zfill(4))
        else:
            sys.exit(T(f"episode number not understood: {a}", f"bölüm no anlaşılmadı: {a}"))
    return out


def _copy(src):
    dst = os.path.join(drive_folder(), os.path.basename(src))
    if os.path.isfile(dst) and os.path.getsize(dst) == os.path.getsize(src):
        return T("already there", "zaten var")
    shutil.copy2(src, dst)
    return T("copied", "kopyalandı")


def cmd_drive(a):
    rec = load()
    D = drive_folder()
    if a.op == "list":
        for f in sorted(os.listdir(D)) if os.path.isdir(D) else []:
            if f.startswith("."):
                continue
            pl = rec.get(f.split("_")[0], {}).get("platforms", {})
            st = " ".join(f"{p[:2]}:{v.get('status', '-')[0].upper()}" for p, v in pl.items()) or T("no record", "kayıt yok")
            print(f"{f:<40} {os.path.getsize(os.path.join(D, f))/1e6:6.1f} MB  {st}")
        return 0
    if a.op == "clean":
        n = 0
        for f in sorted(os.listdir(D)):
            if f.startswith("."):
                continue
            pl = rec.get(f.split("_")[0], {}).get("platforms", {})
            if len(pl) == len(platforms()) and all(v.get("status") == "published" for v in pl.values()):
                dst = core.series_path("trash", os.path.basename(D))
                os.makedirs(dst, exist_ok=True)
                shutil.move(os.path.join(D, f), os.path.join(dst, f))
                n += 1
                print(T("moved:", "taşındı:"), f)
        print(T(f"{n} files moved to the trash (they leave Drive too; the scheduler keeps its own copy)",
                f"{n} dosya çöp klasörüne taşındı (Drive'dan da kalkar; zamanlayıcı kendi kopyasını tutar)"))
        return 0
    os.makedirs(D, exist_ok=True)
    missing = []
    for no in numbers(a.episodes):
        k = [d for d in glob.glob(os.path.join(core.episodes_dir(), f"{no}_*")) if os.path.isdir(d)]
        if len(k) != 1:
            print(T(f"{no}: episode folder not found", f"{no}: bölüm klasörü bulunamadı"))
            missing.append(no)
            continue
        ep = k[0]
        v = rec.get(no, {}).get("video")
        v = core.path(v) if v and os.path.isfile(core.path(v)) else (final_video(ep) if os.path.isfile(core.ep_path(ep, "output", os.path.basename(ep) + ".mp4")) else None)
        cover = core.ep_path(ep, "cover", core.cfg().get("publish", {}).get("cover_file", "{no}_cover.jpg").format(no=no))
        if v:
            print(f"{no}: video {os.path.basename(v)} ({os.path.getsize(v)/1e6:.1f} MB) → {_copy(v)}")
        else:
            print(T(f"{no}: NO VIDEO", f"{no}: VİDEO YOK"))
            missing.append(no)
        if os.path.isfile(cover):
            print(T(f"{no}: cover {os.path.basename(cover)} → ", f"{no}: kapak {os.path.basename(cover)} → ") + _copy(cover))
        else:
            print(T(f"{no}: NO COVER ({core.rel(cover)})", f"{no}: KAPAK YOK ({core.rel(cover)})"))
            missing.append(no)
    fid = core.key("DRIVE_FOLDER_ID", required=False)
    print(T(f"\nDrive folder: {os.path.basename(D)}", f"\nDrive klasörü: {os.path.basename(D)}")
          + (f" (id {fid}). " + T(f"In ~1 min: search_files parentId = '{fid}'", f"~1 dk sonra search_files parentId = '{fid}'") if fid else ""))
    if missing:
        print(T("missing: ", "eksik olanlar: ") + ", ".join(sorted(set(missing))))
    return 0


def add_parser(sp):
    p = sp.add_parser("publish", help=T("publish log", "yayın kaydı"))
    p.add_argument("op", choices=["list", "add"]); p.add_argument("episode", nargs="?")
    p.add_argument("--video"); p.add_argument("--platform", nargs="+")
    p.add_argument("--status", choices=["scheduled", "published", "planlandi", "yayinda"], default="scheduled")
    p.add_argument("--date"); p.add_argument("--metricool-id"); p.add_argument("--link")
    p.add_argument("--dry-run", action="store_true"); p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_publish)
    p = sp.add_parser("drive", help=T("stage videos + covers for Drive", "videoları + kapakları Drive için hazırla"))
    p.add_argument("op", choices=["prepare", "list", "clean"]); p.add_argument("episodes", nargs="*")
    p.set_defaults(func=cmd_drive)
