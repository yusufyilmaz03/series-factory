"""Acceptance check: compare an old-pipeline edit with a new-engine edit of the same episode.

  python3 scripts/acceptance/compare_videos.py <repo> <old base> <new base>
  (base = path without extension; <base>.mp4 and <base>_zaman.json must exist; the old timing file may use legacy keys)
Prints duration difference, timing file equality, per-frame video md5 equality, audio packet equality, byte equality.
"""
import json, subprocess, sys, hashlib
sys.path.insert(0, sys.argv[1])
from series_factory.migrate import timing_to_v2
old, new = sys.argv[2], sys.argv[3]
def dur(p): return float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",p],capture_output=True,text=True).stdout)
def fmd5(p, stream):
    r = subprocess.run(["ffmpeg","-v","error","-i",p,"-map",stream,"-f","framemd5","-"],capture_output=True,text=True).stdout
    return [l.split(",")[-1].strip() for l in r.splitlines() if l and not l.startswith("#")]
do, dn = dur(old+".mp4"), dur(new+".mp4")
zo = timing_to_v2(json.load(open(old+"_zaman.json"))); zn = json.load(open(new+"_zaman.json"))
vo, vn = fmd5(old+".mp4","0:v"), fmd5(new+".mp4","0:v")
ao, an = fmd5(old+".mp4","0:a"), fmd5(new+".mp4","0:a")
same_bytes = hashlib.sha256(open(old+".mp4","rb").read()).hexdigest() == hashlib.sha256(open(new+".mp4","rb").read()).hexdigest()
print(f"duration old {do:.3f} new {dn:.3f} diff {abs(do-dn)*1000:.1f} ms (1 frame = 33.3 ms) | timing json equal: {zo == zn} | "
      f"video frames {len(vo)}/{len(vn)} identical: {vo == vn} | audio packets identical: {ao == an} | file bytes identical: {same_bytes}")
