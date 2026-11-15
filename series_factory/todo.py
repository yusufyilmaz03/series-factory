"""TODO list: every item is a record (<records>/<todo>/<no>/), sections in <records>/<todo_section>/.

The TODO markdown (series.json docs.generated.todo) is generated from the records.

  series todo list [--all] | add --section 6 "text" | done 012 [--note "…"] | edit 012 --old "…" --new "…" | clean
"""
import argparse, re, sys

from . import core, store
from .i18n import T


def sections():
    return sorted(store.all("todo_section"), key=lambda b: b["no"])


def items():
    return sorted(store.all("todo"), key=lambda t: (t["section"], t["order"]))


def md():
    name = core.cfg().get("name", "")
    out = [f"# TODO — {name}".rstrip(" —"), "",
           T("> Open work. This file is generated from the TODO records with `series docs build`; **do not edit it by hand**.",
             "> Açık işler. Bu dosya `series docs build` ile TODO kayıtlarından üretilir; **elle düzenleme**."),
           T("> Add: `series todo add --section 6 \"text\"` · done: `series todo done 012 [--note \"…\"]` · "
             "edit: `series todo edit 012 --old … --new …` · `[x]` items go away with `series todo clean`.",
             "> Ekle: `series todo add --section 6 \"metin\"` · bitti: `series todo done 012 [--note \"…\"]` · "
             "düzelt: `series todo edit 012 --old … --new …` · `[x]` maddeler `series todo clean` ile kalkar."),
           T("> Only open work: assets to make, files/decisions to wait for, engine work. Episode status is in `series status`.",
             "> Yalnızca açık işler: üretilecek varlık, beklenen dosya/karar, hat işi. Bölüm durumu `series status`'tadır."),
           "", "---", ""]
    it = items()
    for b in sections():
        out += [f"## {b['no']}. {b['name']}", ""]
        if b.get("description"):
            out += [b["description"], ""]
        for t in it:
            if t["section"] == b["no"] and not t.get("archived"):
                out.append(f"- [{'x' if t['done'] else ' '}] #{t['id']} · {t['text']}")
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def cmd(a):
    from . import docs
    from .ideas import apply_changes
    if a.op == "list":
        for t in items():
            if t.get("archived") or (t["done"] and not a.all):
                continue
            print(f"#{t['id']} [{t['section']}]{' x' if t['done'] else ''} {re.sub(r'[*`]', '', t['text'])[:110]}")
        return 0
    if a.op == "add":
        if not (a.section and a.text):
            sys.exit(T("required: --section N \"text\"", "gerekli: --section N \"metin\""))
        if not store.exists("todo_section", str(a.section)):
            sys.exit(T(f"section {a.section} missing: ", f"bölüm {a.section} yok: ")
                     + ", ".join(f"{b['no']}={b['name']}" for b in sections()))
        text = " ".join(a.text)
        n = max([int(t["id"]) for t in items()] or [0]) + 1
        order = max([t["order"] for t in items()] or [0]) + 1
        k = store.new_sequential("todo", lambda j: "%03d" % (n + j), lambda rid: {
            "section": int(a.section), "order": order, "done": False, "archived": False, "text": text})
        print(T(f"added #{k['id']}", f"eklendi #{k['id']}"))
    elif a.op in ("done", "edit"):
        ids = [x.lstrip("#").zfill(3) for x in (a.text or [])]
        if not ids:
            sys.exit(T("item number needed (e.g. 012)", "madde no gerekli (ör. 012)"))
        for rid in (ids if a.op == "done" else ids[:1]):
            if not store.exists("todo", rid):
                sys.exit(T(f"#{rid} missing", f"#{rid} yok"))

            def f(k):
                if a.op == "done":
                    k["done"] = True
                    if a.note:
                        k["text"] += f" — {a.note}"
                else:
                    if a.old is not None or a.json or a.new_text is not None:
                        k["text"] = apply_changes(k["text"], argparse.Namespace(text=a.new_text, json=a.json,
                                                                                old=a.old, new=a.new))
                    if a.section:
                        k["section"] = int(a.section)
                    if a.reopen:
                        k["done"] = False
                return k
            store.update("todo", rid, f)
            print(f"#{rid} " + (T("done", "bitti") if a.op == "done" else T("updated", "güncellendi")))
    elif a.op == "clean":
        n = 0
        for t in items():
            if t["done"] and not t.get("archived"):
                store.update("todo", t["id"], lambda k: dict(k, archived=True))
                n += 1
        print(T(f"{n} finished items removed (archived)", f"{n} bitmiş madde kaldırıldı (arşiv)"))
    docs.build(quiet=False)
    return 0


def add_parser(sp):
    p = sp.add_parser("todo", help=T("open work list (records)", "açık işler listesi (kayıt)"))
    p.add_argument("op", choices=["list", "add", "done", "edit", "clean"])
    p.add_argument("text", nargs="*", help=T("add: item text · done/edit: item number(s)", "add: madde metni · done/edit: madde no(ları)"))
    p.add_argument("--section"); p.add_argument("--note"); p.add_argument("--old"); p.add_argument("--new")
    p.add_argument("--json"); p.add_argument("--new-text"); p.add_argument("--reopen", action="store_true")
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd)
