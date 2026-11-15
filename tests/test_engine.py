"""Engine tests that need no network, no API keys and no media files.

Run: python3 -m pytest -q
"""
import json, os, subprocess, sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "example_series")
sys.path.insert(0, ROOT)

from series_factory import migrate, profiles  # noqa: E402


def run_cli(*args, lang="tr"):
    env = dict(os.environ, SERIES_OFFLINE="1", SERIES_LANG=lang)
    env.pop("SERIES_ROOT", None)
    return subprocess.run([sys.executable, "-m", "series_factory", "--series", EXAMPLE, *args], cwd=ROOT, env=env,
                          capture_output=True, text=True)


# ---------------------------------------------------------------- migration
LEGACY_PLAN = {
    "bolum_no": 7, "baslik": "T", "tur": "kurgu", "kaynak_olay": "K-01", "sure_hedef_sn": 60, "kanca": "h",
    "mekan_karesi": {"dosya": "00_m.jpg", "prompt": "p", "duzenle": {"kaynak": "MEKAN", "referanslar": ["A"], "prompt": "e"}},
    "sahneler": [{
        "no": 1, "sure_sn": 5, "seslendirme": "[x] Bir iki üç.", "ekran_yazisi": "B", "ekran_yazisi_sn": 2,
        "diyalog": [{"karakter": "B", "metin": "Hey", "yer": {"kelime_sonrasi": "Bir"}}],
        "ekran_yazilari": [{"metin": "a", "capa": {"replik": 1}, "kayma": 0.2}],
        "kareler": [{"dosya": "01.jpg", "hareket": "sabit", "referanslar": ["MEKAN", "A"], "prompt": "p",
                     "altyazi": "ust", "altyazi_oto": True, "okumalar": ["r"], "bekle": 0.5,
                     "gecis": {"tur": "kes", "sure": 0.3}},
                    {"dosya": "01b.jpg", "hareket": "in", "referanslar": [], "prompt": "p", "baslangic": "iki",
                     "gecis": "kes"}]}],
    "efektler": [{"ad": "s", "capa": {"kelime": "üç."}, "kayma": 0, "ses": 0.4, "sure": 1, "prompt": "x", "aciklama": "d"}],
    "muzik": {"ad": "m", "ses": 0.1, "sus": [{"capa": {"sahne": 1}, "kayma": 0}, {"capa": {"kare": "01b.jpg"}, "kayma": 0}]},
    "sponsor_yuvasi": {"sahne_no": 1, "aciklama": "x"},
    "kapanis": {"replik": "l", "gercek_goruntu_notu": "n", "gercek_video": {"dosya": "v", "baslangic": 1, "sure": 2}},
    "hashtagler": ["#a"], "kanon_guncellemesi": [], "tts": {"stability": 0, "style": 0.4}, "format": 2,
}


def test_plan_conversion_keys_and_values():
    d = migrate.plan_to_v3(LEGACY_PLAN)
    assert d["format"] == 3 and d["episode_no"] == 7 and d["source_idea"] == "K-01"
    f0, f1 = d["scenes"][0]["frames"]
    assert f0["motion"] == "static" and f0["subtitle_pos"] == "top" and f0["refs"] == ["SET", "A"]
    assert f0["transition"] == {"type": "cut", "duration": 0.3} and f1["transition"] == "cut"
    assert f1["start_word"] == "iki" and f0["hold"] == 0.5 and f0["reads"] == ["r"]
    s = d["scenes"][0]
    assert s["dialogue"][0] == {"character": "B", "text": "Hey", "at": {"after_word": "Bir"}}
    assert s["title_text"] == "B" and s["title_sec"] == 2 and s["title_steps"][0]["anchor"] == {"line": 1}
    assert d["sfx"][0] == {"id": "s", "anchor": {"word": "üç."}, "offset": 0, "volume": 0.4, "duration": 1,
                           "prompt": "x", "description": "d"}
    assert d["music"]["mute"][1]["anchor"] == {"frame": "01b.jpg"}
    assert d["set_frame"]["edit"]["source"] == "SET"
    assert d["closing"]["real_video"] == {"file": "v", "start": 1, "duration": 2}
    assert d["sponsor_slot"] == {"scene_no": 1, "description": "x"}


def test_converters_are_idempotent():
    d = migrate.plan_to_v3(LEGACY_PLAN)
    assert migrate.plan_to_v3(d) == d
    z = migrate.timing_to_v2({"video": "v.mp4", "sure": 1.0, "fps": 30, "son_karartma": 0.4, "kareler": [
        {"sahne": 1, "kare": "a.jpg", "hareket": "sabit", "t0": 0, "t1": 1, "soz_sonu": 1, "bekle": 0,
         "gecis": {"tur": "kes", "sure": 0}, "replik": 0, "okumalar": []}]})
    assert z["frames"][0]["motion"] == "static" and z["frames"][0]["transition"]["type"] == "cut"
    assert migrate.timing_to_v2(z) == z
    a = migrate.assets_to_v2({"gorseller": {"x": {"yol": "p", "tur": "karakter_sayfasi", "etiketler": ["ifade_sayfasi"]}},
                              "sesler": {}})
    assert a["images"]["x"] == {"path": "p", "type": "character_sheet", "tags": ["expression_sheet"]}
    assert migrate.assets_to_v2(a) == a
    r = migrate.record_to_v2("idea", {"kod": "G-01", "grup": "g01", "sira": 1, "bicim": "madde", "metin": "t", "eklendi": "x"})
    assert r == {"code": "G-01", "group": "g01", "order": 1, "form": "item", "text": "t", "created": "x"}
    assert migrate.record_to_v2("idea", r) == r


def test_settings_conversion_keeps_legacy_layout():
    c = migrate.settings_to_cfg({"video": {"genislik": 1080, "yukseklik": 1920, "fps": 30, "font": "F"},
                                 "sesler": {"NAR": {"ad": "n", "id": "i"}}, "anlatici": "NAR",
                                 "gorsel": {"mod": "elle", "en_boy": "9:16"}, "yollar": {"dokumanlar": "Docs"}})
    assert c["narrator"] == "NAR" and c["voices"]["NAR"] == {"name": "n", "id": "i"}
    assert c["image"]["adapter"] == "manual" and "profile_overrides" not in c
    assert c["layout"]["frames"] == "kareler" and c["paths"]["docs"] == "Docs"


# ---------------------------------------------------------------- profiles
def test_vertical_short_subtitle_styles_match_source_pipeline():
    """The source pipeline's ASS header, with style names translated. Values must never drift."""
    p = profiles.get("vertical_short")
    got = set(profiles.ass_styles(p, "F"))
    w, g, y, s = "&H00FFFFFF", "&H00A8F0C8", "&H0040D8FF", "&H64000000"
    exp = {
        f"Style: Default,F,72,{w},&H00FFFFFF,&H00000000,{s},-1,0,0,0,100,100,0,0,1,6,2,2,90,140,440,1",
        f"Style: Line,F,62,{g},&H00FFFFFF,&H00000000,{s},-1,-1,0,0,100,100,0,0,1,6,2,2,90,140,560,1",
        f"Style: DefaultTop,F,72,{w},&H00FFFFFF,&H00000000,{s},-1,0,0,0,100,100,0,0,1,6,2,8,90,140,360,1",
        f"Style: LineTop,F,62,{g},&H00FFFFFF,&H00000000,{s},-1,-1,0,0,100,100,0,0,1,6,2,8,90,140,520,1",
        f"Style: DefaultTop2,F,72,{w},&H00FFFFFF,&H00000000,{s},-1,0,0,0,100,100,0,0,1,6,2,8,90,140,560,1",
        f"Style: LineTop2,F,62,{g},&H00FFFFFF,&H00000000,{s},-1,-1,0,0,100,100,0,0,1,6,2,8,90,140,700,1",
        f"Style: DefaultMid,F,72,{w},&H00FFFFFF,&H00000000,{s},-1,0,0,0,100,100,0,0,1,6,2,8,90,140,860,1",
        # the source defined the middle line style twice; libass uses the last definition (860)
        f"Style: LineMid,F,62,{g},&H00FFFFFF,&H00000000,{s},-1,-1,0,0,100,100,0,0,1,6,2,8,90,140,860,1",
        f"Style: Title,F,74,{y},&H00FFFFFF,&H00000000,{s},-1,0,0,0,100,100,2,0,1,7,3,8,90,140,230,1",
    }
    assert got == exp


def test_profile_overrides_merge():
    p = profiles.get("vertical_short", {"fps": 25, "subtitles": {"max_words": 5}})
    assert p["fps"] == 25 and p["subtitles"]["max_words"] == 5 and p["subtitles"]["margin_l"] == 90


# ---------------------------------------------------------------- the example series (CLI end to end, offline)
def test_example_series_checks_clean():
    r = run_cli("check", "001")
    assert r.returncode == 0, r.stderr
    assert "sorun yok" in r.stdout


def test_example_series_english_messages():
    r = run_cli("check", "001", lang="en")
    assert "no problems" in r.stdout


def test_status_json_is_machine_readable():
    r = run_cli("status", "--json")
    d = json.loads(r.stdout)
    assert d["episodes"][0]["no"] == "001" and d["episodes"][0]["stage"] == "script"
    assert set(d["ideas"]["waiting"]) == {"G-02", "H-01"}


def test_dry_runs_produce_nothing():
    before = sorted(os.listdir(os.path.join(EXAMPLE, "episodes", "001_kayip_kibrit")))
    for args in (("frames", "001", "--dry-run", "--json"), ("voice", "episode", "001", "--dry-run", "--json"),
                 ("batch", "001", "--dry-run", "--json"), ("script", "new", "--dry-run")):
        r = run_cli(*args)
        assert r.returncode == 0, (args, r.stderr)
    assert sorted(os.listdir(os.path.join(EXAMPLE, "episodes", "001_kayip_kibrit"))) == before
    d = json.loads(run_cli("voice", "episode", "001", "--dry-run", "--json").stdout)
    assert d["characters"] > 500 and "bip_cirp" in d["new_sfx"]


def test_offline_guard_blocks_network():
    from series_factory import core
    os.environ["SERIES_OFFLINE"] = "1"
    with pytest.raises(RuntimeError):
        core.http("GET", "https://example.com/")


# ---------------------------------------------------------------- leak check
def test_repository_is_leak_free():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "leak_check.py")], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
