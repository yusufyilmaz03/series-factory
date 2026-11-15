"""HEIC/HEIF -> JPG converter (standalone; no other engine module needed).

  series heic photo.HEIC                     photo.jpg next to it
  series heic a.heic b.heic --to folder/
  series heic references/Cat                 every HEIC in the folder (recursive)
  options: --quality 92   --move-original _trash/heic_originals   (never deletes, moves)

Tries in order: ImageMagick (fixes orientation) -> sips (built into macOS) -> heif-convert -> ffmpeg.
In code: from series_factory.heic import convert; convert("x.HEIC") -> "x.jpg"
"""
import os, shutil, subprocess

from .i18n import T

EXT = (".heic", ".heif")


def is_heic(p):
    return p.lower().endswith(EXT)


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, timeout=120).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _imagemagick(src, dst, q):
    for exe in (["magick"], ["convert"]):
        if shutil.which(exe[0]) and _run(exe + [src + "[0]", "-auto-orient", "-quality", str(q), dst]):
            return True
    return False


def _sips(src, dst, q):
    return bool(shutil.which("sips")) and _run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(q), src,
                                                "--out", dst])


def _heif_convert(src, dst, q):
    return bool(shutil.which("heif-convert")) and _run(["heif-convert", "-q", str(q), src, dst])


def _ffmpeg(src, dst, q):
    return bool(shutil.which("ffmpeg")) and _run(["ffmpeg", "-v", "error", "-y", "-i", src, "-frames:v", "1",
                                                  "-q:v", "2", dst])


def convert(src, to=None, quality=92, move_original=None, overwrite=False):
    """Convert a HEIC to JPG and return the JPG path. to: file or folder (default: next to the source)."""
    if not is_heic(src):
        raise ValueError(T(f"not a HEIC: {src}", f"HEIC değil: {src}"))
    stem = os.path.splitext(os.path.basename(src))[0]
    if to and (os.path.isdir(to) or to.endswith(os.sep)):
        os.makedirs(to, exist_ok=True)
        dst = os.path.join(to, stem + ".jpg")
    else:
        dst = to or os.path.join(os.path.dirname(src), stem + ".jpg")
    if os.path.exists(dst) and not overwrite:
        raise FileExistsError(T(f"already exists: {dst}", f"zaten var: {dst}"))
    tmp = dst + ".tmp.jpg"
    for method in (_imagemagick, _sips, _heif_convert, _ffmpeg):
        if method(src, tmp, quality) and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, dst)
            break
    else:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError(T(f"could not convert (ImageMagick/sips/heif-convert/ffmpeg missing or failed): {src}",
                             f"çevrilemedi (ImageMagick/sips/heif-convert/ffmpeg yok ya da başarısız): {src}"))
    try:  # keep the capture date
        st = os.stat(src)
        os.utime(dst, (st.st_atime, st.st_mtime))
    except OSError:
        pass
    if move_original:
        r = os.path.relpath(src)
        d = os.path.join(move_original, "" if r.startswith("..") else os.path.dirname(r))
        os.makedirs(d, exist_ok=True)
        os.rename(src, os.path.join(d, os.path.basename(src)))
    return dst


def cmd(a):
    files = []
    for y in a.paths:
        if os.path.isdir(y):
            for d, _, fs in os.walk(y):
                files += [os.path.join(d, f) for f in sorted(fs) if is_heic(f) and not f.startswith(".")]
        elif is_heic(y):
            files.append(y)
        else:
            print(T("skipped (not HEIC):", "atlandı (HEIC değil):"), y)
    err = 0
    for f in files:
        try:
            print(f, "->", convert(f, a.to, a.quality, a.move_original, a.overwrite))
        except Exception as e:
            print(T("ERROR:", "HATA:"), e)
            err += 1
    print(T(f"{len(files) - err}/{len(files)} files converted", f"{len(files) - err}/{len(files)} dosya çevrildi"))
    return 1 if err else 0


def add_parser(sp):
    p = sp.add_parser("heic", help=T("convert HEIC/HEIF photos to JPG", "HEIC/HEIF fotoğrafları JPG'ye çevir"))
    p.add_argument("paths", nargs="+")
    p.add_argument("--to")
    p.add_argument("--quality", type=int, default=92)
    p.add_argument("--move-original")
    p.add_argument("--overwrite", action="store_true")
    p.set_defaults(func=cmd, needs_root=False)
