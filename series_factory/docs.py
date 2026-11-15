"""Series documents: generated views and sync tracking with a Claude project.

series.json "docs":
  "canon": "characters.md"                       the character file (`series canon`, cards, context)
  "script_context": ["01_", "02_"]               docs given to the script writer (default: every .md)
  "generated": {"ideas": "...", "in_production": "...", "done": "...", "todo": "TODO.md"}
  "project_paths": {"01_": "", "06_": "claude/"} doc name prefix -> path in the Claude project; docs matching no
                                                 prefix are not tracked (default: every .md, at the project root)

  series docs diff                 refresh generated docs; list docs that changed since the last upload
  series docs build                only refresh the generated docs
  series docs mark [file ...]      mark as uploaded to the project (all if none given)
  series docs edit <file> --old "..." --new "..."   |   --json changes.json ([{"old": "...", "new": "..."}])
  series docs insert <file> --after "<line that occurs once>" --text "<new line>"
"""
import hashlib, json, os, sys

from . import core
from .catalog import nfc
from .i18n import T

DEFAULT_GENERATED = {"ideas": "ideas_pool.md", "in_production": "ideas_in_production.md", "done": "ideas_done.md",
                     "todo": "TODO.md"}


def dcfg():
    return core.cfg().get("docs", {})


def folder():
    return core.series_path("docs")


def generated_names():
    return {**DEFAULT_GENERATED, **dcfg().get("generated", {})}


def generated_set():
    return set(generated_names().values())


def doc_path(name):
    d = folder()
    for f in os.listdir(d):
        if nfc(f) == nfc(name) or nfc(f).startswith(nfc(name)):
            return os.path.join(d, f)
    sys.exit(T(f"No such document: {name}", f"Doküman yok: {name}"))


def read(name):
    return open(doc_path(name), encoding="utf-8").read()


def generated_texts():
    from . import ideas, todo
    g = generated_names()
    out = {}
    try:
        out.update(ideas.view_texts({k: g[k] for k in ("ideas", "in_production", "done")}))
    except FileNotFoundError:
        pass
    out[g["todo"]] = todo.md()
    return out


def build(quiet=True):
    if not os.path.isdir(folder()):
        os.makedirs(folder(), exist_ok=True)
    changed = []
    for name, text in generated_texts().items():
        p = os.path.join(folder(), name)
        old = open(p, encoding="utf-8").read() if os.path.exists(p) else None
        if old != text:
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            changed.append(name)
    if not quiet:
        print(T("generated: ", "üretildi: ") + (", ".join(changed) if changed else T("no change", "değişiklik yok"))
              + (T(" -> upload to the project (series docs diff)", " -> projeye yükle (series docs diff)") if changed else ""))
    return changed


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]


def project_path(name):
    pp = dcfg().get("project_paths", {"": ""})
    for pre, f in sorted(pp.items(), key=lambda x: -len(x[0])):
        if nfc(name).startswith(pre):
            return f + nfc(name)
    return None


def sync_file():
    return os.path.join(folder(), core.layout("docs_sync"))


def synced():
    return json.load(open(sync_file())) if os.path.exists(sync_file()) else {}


def doc_list():
    return sorted(f for f in os.listdir(folder()) if f.endswith(".md") and project_path(f))


def diff():
    build()
    s = synced()
    return [(nfc(f), project_path(f)) for f in doc_list() if s.get(nfc(f)) != sha(os.path.join(folder(), f))]


def cmd(a):
    if a.op == "diff":
        f = diff()
        if a.json:
            print(json.dumps([{"doc": d, "project_path": p} for d, p in f], ensure_ascii=False, indent=1))
            return 0
        if not f:
            print(T("✓ docs/ and the project match (as of the last mark)", "✓ Dokümanlar ile proje aynı (son işaretlemeye göre)"))
        for name, pp in f:
            print(T(f"to upload: {core.rel(folder())}/{name} -> project: {pp}",
                    f"yüklenecek: {core.rel(folder())}/{name} -> proje: {pp}"))
    elif a.op == "build":
        build(quiet=False)
    elif a.op == "mark":
        s = synced()
        fresh = generated_texts()
        for f in (a.files or doc_list()):
            p = doc_path(f)
            name = nfc(os.path.basename(p))
            if name in fresh and open(p, encoding="utf-8").read() != fresh[name]:
                print(T(f"NOT MARKED: {name} changed meanwhile (another session or an episode moved on). "
                        "Run 'series docs diff', upload again, then mark.",
                        f"İŞARETLENMEDİ: {name} bu arada değişti (başka oturum ya da bölüm ilerledi). "
                        f"'series docs diff' çalıştır, yeniden yükle, sonra işaretle."))
                continue
            s[name] = sha(p)
        json.dump(s, open(sync_file(), "w"), indent=1, ensure_ascii=False)
        print(T("marked:", "işaretlendi:"), len(a.files or doc_list()), T("files", "dosya"))
    elif a.op in ("edit", "insert"):
        if not a.files:
            sys.exit(T("file name needed", "dosya adı gerekli"))
        p = doc_path(a.files[0])
        if nfc(os.path.basename(p)) in generated_set():
            sys.exit(T(f"{os.path.basename(p)} is generated from records, not edited by hand. Ideas: series idea-add / "
                       "idea-edit / idea-status / idea-group · TODO: series todo add / done / edit / clean",
                       f"{os.path.basename(p)} kayıtlardan üretilir, elle düzenlenmez. Olay: series idea-add / idea-edit / "
                       "idea-status / idea-group · TODO: series todo add / done / edit / clean"))
        t = t0 = open(p, encoding="utf-8").read()
        if a.op == "insert":
            if t.count(a.after) != 1:
                sys.exit(T(f"--after text occurs {t.count(a.after)} times (must be exactly 1)",
                           f"--after metni {t.count(a.after)} kez geçiyor (tam 1 olmalı)"))
            i = t.index(a.after) + len(a.after)
            i = t.find("\n", i) if t.find("\n", i) != -1 else len(t)
            t = t[:i] + "\n" + a.text + t[i:]
        else:
            pairs = json.load(open(a.json, encoding="utf-8")) if a.json else [{"old": a.old, "new": a.new}]
            for n, c in enumerate(pairs, 1):
                old, new = c.get("old", c.get("eski")), c.get("new", c.get("yeni"))
                k = t.count(old)
                if k != 1:
                    sys.exit(T(f"change {n}: old text occurs {k} times (must be exactly 1); nothing written",
                               f"değişiklik {n}: eski metin {k} kez geçiyor (tam 1 olmalı); hiçbir şey yazılmadı"))
                t = t.replace(old, new)
        if open(p, encoding="utf-8").read() != t0:
            sys.exit(T(f"{os.path.basename(p)} changed in another session meanwhile; nothing written, run again",
                       f"{os.path.basename(p)} bu arada başka bir oturumda değişti; hiçbir şey yazılmadı, komutu yeniden çalıştır"))
        open(p, "w", encoding="utf-8").write(t)
        print(T(f"updated: {os.path.basename(p)} -> to upload: {project_path(os.path.basename(p))}",
                f"güncellendi: {os.path.basename(p)} -> projeye yüklenecek: {project_path(os.path.basename(p))}"))
    return 0


def add_parser(sp):
    p = sp.add_parser("docs", help=T("generated docs and project sync", "üretilen dokümanlar ve proje senkronu"))
    p.add_argument("op", choices=["diff", "build", "mark", "edit", "insert"])
    p.add_argument("files", nargs="*"); p.add_argument("--old"); p.add_argument("--new"); p.add_argument("--json", nargs="?", const=True)
    p.add_argument("--after"); p.add_argument("--text")
    p.set_defaults(func=cmd)
