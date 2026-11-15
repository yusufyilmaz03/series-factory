"""`series` — single entry point.

  series [--series PATH] [--lang tr|en] <command> ...
Run `series help` for the job -> command list, `series <command> -h` for options.
"""
import argparse, os, shutil, sys

from . import __version__, core, i18n
from .i18n import T

MODULES = ["status", "ideas", "todo", "canon", "check", "docs", "cards", "publish", "script", "images", "hf", "voice",
           "assemble", "subplace", "strips", "batch", "produce", "assets", "library", "heic"]
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "series")


def cmd_migrate(a):
    from . import migrate
    migrate.run(a.root or os.getcwd(), given=a.from_, extra=a.extra, name=a.name, lang=a.lang_ or "tr",
                dry=a.dry_run, settings_only=a.settings_only, as_json=a.json)
    return 0


def cmd_init(a):
    """Create a new, empty series folder from the template."""
    dst = os.path.abspath(a.folder)
    if core.config_file(dst):
        sys.exit(T(f"{dst} already has a {core.CONFIG_NAME}", f"{dst} içinde zaten {core.CONFIG_NAME} var"))
    if a.dry_run:
        print(T(f"[dry-run] would create a series in {dst}", f"[kuru] {dst} içinde seri oluşturulacaktı"))
        return 0
    for d, _, files in os.walk(TEMPLATE):
        r = os.path.relpath(d, TEMPLATE)
        os.makedirs(os.path.join(dst, r), exist_ok=True)
        for f in files:
            t = os.path.join(dst, r, f)
            if not os.path.exists(t):
                shutil.copy2(os.path.join(d, f), t)
    import json
    p = os.path.join(dst, core.CONFIG_NAME)
    c = json.load(open(p, encoding="utf-8"))
    c["name"] = a.name or os.path.basename(dst)
    c["lang"] = a.lang_ or c.get("lang", "en")
    json.dump(c, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(T(f"series created: {dst}\nnext: edit series.json (characters, voices, image style), add docs/, then "
            "'series --series <folder> script new --manual'",
            f"seri oluşturuldu: {dst}\nsonra: series.json'u düzenle (karakterler, sesler, görsel stil), docs/ ekle, ardından "
            "'series --series <klasör> script new --manual'"))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="series", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--series", help=T("series root (default: SERIES_ROOT or nearest series.json)", "seri kökü (varsayılan: SERIES_ROOT ya da en yakın series.json)"))
    ap.add_argument("--lang", choices=i18n.SUPPORTED)
    ap.add_argument("--version", action="version", version=f"series-factory {__version__}")
    sp = ap.add_subparsers(dest="command", required=True, metavar="<command>")
    for m in MODULES:
        __import__(f"series_factory.{m}", fromlist=["add_parser"]).add_parser(sp)
    p = sp.add_parser("migrate", help=T("convert a legacy series (ayarlar.json, Turkish field names)", "eski seriyi çevir (ayarlar.json, Türkçe alan adları)"))
    p.add_argument("root", nargs="?"); p.add_argument("--from", dest="from_"); p.add_argument("--extra")
    p.add_argument("--name"); p.add_argument("--series-lang", dest="lang_", default=None)
    p.add_argument("--dry-run", action="store_true"); p.add_argument("--settings-only", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_migrate, needs_root=False)
    p = sp.add_parser("init", help=T("create a new series folder", "yeni seri klasörü oluştur"))
    p.add_argument("folder"); p.add_argument("--name"); p.add_argument("--series-lang", dest="lang_", choices=i18n.SUPPORTED)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_init, needs_root=False)
    return ap


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--series")
    pre.add_argument("--lang")
    known, _ = pre.parse_known_args(argv)
    if known.series:
        core.set_root(known.series)
    if core.find_root(required=False):
        try:
            core.cfg()
        except (OSError, ValueError) as e:
            sys.exit(f"series.json: {e}")
    if known.lang:
        i18n.set_lang(known.lang)
    ap = build_parser()
    a, extra = ap.parse_known_args(argv)
    if extra:
        # free text after options (e.g. `todo add --section 6 "text"`) belongs to the trailing positional list
        if isinstance(getattr(a, "text", None), list) and not any(x.startswith("-") for x in extra):
            a.text += extra
        else:
            ap.error(T("unrecognized arguments: ", "tanınmayan argümanlar: ") + " ".join(extra))
    if getattr(a, "needs_root", True):
        core.root()
    try:
        rc = a.func(a)
    except BrokenPipeError:
        rc = 0
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
