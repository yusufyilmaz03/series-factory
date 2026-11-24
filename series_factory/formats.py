"""Episode formats: the kinds of episodes a series makes (normal episode, short theory, carousel guide, ...).

Each format is set in series.json "formats" (nothing about formats is fixed in code):
  label, folder (episodes/<folder>/), output ["video"] | ["carousel"] | both, ready "all" | "any",
  profile / profile_overrides (size, subtitles), words {min, max, target}, idea_types ["T"], counter
  {"label": "Theory {n}", "start": 1}, platforms [...], default: true (the format of an unfiled episode)
Which slot a format airs in is set in series.json "schedule" -> "slots" (see `series calendar`).

  series formats [--json]               formats with episode counts per stage
  series formats organize [--dry-run]   move episodes into episodes/<format folder>/ (publish log paths follow)
  series formats set 087 short [--dry-run]   move one episode to another format
"""
import json, os, sys

from . import catalog, core, publish
from .i18n import T


def summary():
    eps = [catalog.episode_summary(b) | {"path": b["path"]} for b in catalog.episodes() if "plan" in b]
    out = {}
    for k, f in core.formats().items():
        mine = [o for o in eps if o["format"] == k]
        out[k] = {"label": f.get("label", k), "folder": core.format_folder(k), "output": core.format_outputs(k),
                  "ready_rule": f.get("ready", "all"), "idea_types": f.get("idea_types", []),
                  "episodes": len(mine), "ready": sum(o["ready"] for o in mine),
                  "by_stage": {s: sum(o["stage"] == s for o in mine) for s in catalog.STAGES}}
    return out


def move(path, fmt, dry):
    """Move one episode folder into the format folder; fix the publish log video path. Returns the new path."""
    sub = core.format_folder(fmt)
    dst = os.path.join(core.episodes_dir(), sub, os.path.basename(path)) if sub else os.path.join(core.episodes_dir(), os.path.basename(path))
    if os.path.abspath(dst) == os.path.abspath(path):
        return path
    if os.path.exists(dst):
        sys.exit(T(f"already exists: {core.rel(dst)}", f"zaten var: {core.rel(dst)}"))
    print(f"{'[dry-run] ' if dry else ''}{core.rel(path)} → {core.rel(dst)}")
    if dry:
        return dst
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.rename(path, dst)
    log = publish.load()
    old_rel, new_rel = core.rel(path), core.rel(dst)
    changed = False
    for k in log.values():
        v = k.get("video", "")
        if v == old_rel or v.startswith(old_rel + os.sep):
            k["video"] = new_rel + v[len(old_rel):]
            changed = True
    if changed:
        publish.save(log)
    return dst


def cmd(a):
    if a.op == "list":
        d = summary()
        if a.json:
            print(json.dumps(d, ensure_ascii=False, indent=1))
            return 0
        print(f"{'format':<12}{T('label', 'ad'):<28}{T('folder', 'klasör'):<12}{T('output', 'çıktı'):<18}"
              f"{T('ideas', 'olay'):<8}{T('episodes', 'bölüm'):>7}{T('ready', 'hazır'):>7}  {T('stages', 'aşamalar')}")
        for k, o in d.items():
            st = ", ".join(f"{n} {catalog.stage_name(s)}" for s, n in o["by_stage"].items() if n)
            print(f"{k:<12}{o['label'][:27]:<28}{(o['folder'] or '.')[:11]:<12}{'+'.join(o['output']) + (' (any)' if o['ready_rule'] == 'any' else ''):<18}"
                  f"{','.join(o['idea_types'])[:7]:<8}{o['episodes']:>7}{o['ready']:>7}  {st}")
        unfiled = [p for p, f in core.episode_folders() if f is None]
        if unfiled and any(core.format_folder(k) for k in core.formats()):
            print(T(f"\n{len(unfiled)} episodes are not in a format folder yet: series formats organize",
                    f"\n{len(unfiled)} bölüm henüz format klasöründe değil: series formats organize"))
        return 0
    if a.op == "organize":
        n = 0
        for path, fmt in core.episode_folders():
            if fmt is not None:
                continue
            k = core.episode_format(path)
            if core.format_folder(k):
                move(path, k, a.dry_run)
                n += 1
        print(T(f"{n} episodes {'would be ' if a.dry_run else ''}moved", f"{n} bölüm {'taşınacaktı' if a.dry_run else 'taşındı'}"))
        return 0
    # set
    if not a.episode or not a.format:
        sys.exit(T("usage: series formats set <episode> <format>", "kullanım: series formats set <bölüm> <format>"))
    if a.format not in core.formats():
        sys.exit(T(f"unknown format: {a.format} ({', '.join(core.formats())})", f"bilinmeyen format: {a.format} ({', '.join(core.formats())})"))
    ep = core.episode_dir(a.episode)
    if not a.dry_run:
        d = core.load_plan(ep)
        d["episode_format"] = a.format
        core.save_plan(ep, d)
    move(ep, a.format, a.dry_run)
    return 0


def add_parser(sp):
    p = sp.add_parser("formats", help=T("episode formats (list / organize folders / set one)", "bölüm formatları (liste / klasörlere yerleştir / tek bölüm)"))
    p.add_argument("op", nargs="?", default="list", choices=["list", "organize", "set"])
    p.add_argument("episode", nargs="?"); p.add_argument("format", nargs="?")
    p.add_argument("--json", action="store_true"); p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd)
