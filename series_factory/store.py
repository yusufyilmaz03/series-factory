"""Record store: <records>/<kind>/<id>/<rev>.json — one folder per record, one new file per update.

Why: parallel sessions that read a markdown file and write it back whole were erasing each other's changes.
Here every idea / todo item is its own record; the markdown views are generated from the records.

- New record: the folder is created with os.mkdir (atomic); two sessions cannot take the same id.
- Update: read the last revision N, apply the change, create N+1 with O_EXCL. If another session wrote N+1
  first, creation fails and the change is re-applied on top of the newer revision. No update is lost.
- No deletion: a record is hidden with "archived": true; old revisions stay as history.
"""
import copy, datetime, hashlib, json, os, time

from . import core
from .migrate import record_to_v2


class Conflict(Exception):
    pass


def _now():
    tz = core.cfg().get("timezone")
    if tz:
        try:
            from zoneinfo import ZoneInfo
            return datetime.datetime.now(ZoneInfo(tz)).isoformat(timespec="seconds")
        except Exception:
            pass
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def folder(kind):
    p = core.series_path("records", core.layout("records").get(kind, kind))
    os.makedirs(p, exist_ok=True)
    return p


def _dir(kind, rid):
    return os.path.join(folder(kind), rid)


def _revisions(d):
    try:
        return sorted(int(f[:-5]) for f in os.listdir(d) if f.endswith(".json") and f[:-5].isdigit())
    except FileNotFoundError:
        return []


def _read_file(p, kind):
    for _ in range(40):              # another session may be writing this very moment
        try:
            with open(p, encoding="utf-8") as f:
                return record_to_v2(kind, json.load(f))
        except json.JSONDecodeError:
            time.sleep(0.05)
    raise Conflict(f"unreadable (corrupt or being written): {p}")


def _create(p, rec):
    """Create the file only if it does not exist (O_EXCL); FileExistsError otherwise."""
    fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, indent=1) + "\n")


def exists(kind, rid):
    return bool(_revisions(_dir(kind, rid)))


def read(kind, rid):
    d = _dir(kind, rid)
    s = _revisions(d)
    if not s:
        raise KeyError(f"{kind}/{rid} missing")
    return _read_file(os.path.join(d, "%05d.json" % s[-1]), kind)


def all(kind):  # noqa: A001 - mirrors the store vocabulary
    out = []
    for rid in sorted(os.listdir(folder(kind))):
        if rid.startswith((".", "_")) or not os.path.isdir(_dir(kind, rid)):
            continue
        if exists(kind, rid):          # folder created but first revision not written yet
            out.append(read(kind, rid))
    return out


def new(kind, rid, rec):
    """Create the record; FileExistsError if the id is taken."""
    d = _dir(kind, rid)
    os.mkdir(d)
    r = dict(rec, id=rid, rev=1, created=_now(), updated=_now())
    _create(os.path.join(d, "00001.json"), r)
    return r


def new_sequential(kind, candidate, make, tries=50):
    """candidate(i) -> id; taken ids are skipped. make(id) -> record."""
    for i in range(tries):
        rid = candidate(i)
        if os.path.exists(_dir(kind, rid)):
            continue
        try:
            return new(kind, rid, make(rid))
        except FileExistsError:
            continue
    raise Conflict(f"{kind}: no free id")


def update(kind, rid, change, tries=200):
    """change(copy) -> new record (None = no change). Re-applied on the newest revision after a conflict."""
    d = _dir(kind, rid)
    for _ in range(tries):
        s = _revisions(d)
        if not s:
            raise KeyError(f"{kind}/{rid} missing")
        old = _read_file(os.path.join(d, "%05d.json" % s[-1]), kind)
        new_r = change(copy.deepcopy(old))
        if new_r is None or new_r == old:
            return old
        new_r["rev"] = s[-1] + 1
        new_r["updated"] = _now()
        try:
            _create(os.path.join(d, "%05d.json" % (s[-1] + 1)), new_r)
            return new_r
        except FileExistsError:
            time.sleep(0.01)
    raise Conflict(f"{kind}/{rid}: repeated conflicts; try again shortly")


def version(*kinds):
    """Short hash of (id, rev) of all records."""
    h = hashlib.sha1()
    for kind in kinds:
        for r in all(kind):
            h.update(f"{kind}/{r['id']}:{r.get('rev')};".encode())
    return h.hexdigest()[:10]
