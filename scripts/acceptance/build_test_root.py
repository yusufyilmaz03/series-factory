"""Build a throw-away test copy of a legacy series (the source is only read, never written).

  python3 scripts/acceptance/build_test_root.py <legacy series> <new empty folder> 008 027 061
Copies pipeline/ (without .env, backups, caches, sketches), assets/, kayit/, Dokümanlar/, yayin/. The listed episodes are
copied in full (for assemble tests); every other episode gets its .json/.txt/.md files plus empty media placeholders with
the original modification times, so status/idea commands see the same state as the live folder.
"""
import os, shutil, sys
src, dst, full = sys.argv[1], sys.argv[2], set(sys.argv[3:])
if os.path.exists(dst):
    sys.exit("dst exists")
os.makedirs(dst)
ign = shutil.ignore_patterns(".env", "_yedek_*", "__pycache__", "krokiler", ".DS_Store")
shutil.copytree(os.path.join(src, "pipeline"), os.path.join(dst, "pipeline"), ignore=ign)
for d in ("assets", "kayit", "Dokümanlar", "yayin"):
    shutil.copytree(os.path.join(src, d), os.path.join(dst, d), ignore=shutil.ignore_patterns("_yedek_*", ".DS_Store"))
E = os.path.join(src, "episodes")
for ep in sorted(os.listdir(E)):
    sp = os.path.join(E, ep)
    if not os.path.isdir(sp):
        continue
    dp = os.path.join(dst, "episodes", ep)
    if ep[:3] in full:
        shutil.copytree(sp, dp, ignore=shutil.ignore_patterns(".DS_Store"))
        continue
    for root, dirs, files in os.walk(sp):
        r = os.path.relpath(root, sp)
        os.makedirs(os.path.join(dp, r), exist_ok=True)
        for f in files:
            s, t = os.path.join(root, f), os.path.join(dp, r, f)
            if f.endswith((".json", ".txt", ".md")):
                shutil.copy2(s, t)
            else:                       # media: empty placeholder with the same mtime
                open(t, "wb").close()
                st = os.stat(s)
                os.utime(t, (st.st_atime, st.st_mtime))
print("ok", dst)
