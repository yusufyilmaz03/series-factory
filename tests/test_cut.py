"""Motion-comic cut: planning rules, no media files needed."""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from series_factory import cut  # noqa: E402

WORDS = [("Bir", 0.0, 0.3), ("iki.", 0.4, 0.8), ("Üç", 1.0, 1.3), ("dört,", 1.4, 1.9), ("beş", 2.1, 2.4),
         ("altı.", 2.5, 3.0), ("Yedi", 3.2, 3.5), ("sekiz.", 3.6, 4.1), ("Dokuz", 4.3, 4.6), ("on.", 4.7, 5.2),
         ("On", 5.4, 5.6), ("bir.", 5.7, 6.2), ("Son", 6.4, 6.8)]


def test_cuts_only_at_sentence_or_clause_ends_and_respect_minimum():
    for density, (mn, _, mx) in cut.DENSITY.items():
        cs = cut.split_times(0.0, 7.0, WORDS, density)
        assert len(cs) + 1 <= mx
        edges = [0.0] + cs + [7.0]
        assert all(b - a >= mn - 1e-6 for a, b in zip(edges, edges[1:])), density
        ends = {(w[2] + WORDS[i + 1][1]) / 2 for i, w in enumerate(WORDS[:-1]) if w[0][-1] in cut.PUNCT}
        assert all(any(abs(c - e) < 1e-9 for e in ends) for c in cs)


def test_density_order():
    n = {d: len(cut.split_times(0.0, 7.0, WORDS, d)) for d in cut.DENSITY}
    assert n["calm"] <= n["medium"] <= n["lively"]


def test_effect_frame_is_capped_and_still():
    shots = [{"f0": 0, "f1": 150, "frame": "a.jpg", "motion": "in"}]
    frames = {"a.jpg": {"animate": {"anchors": {"eyes": [[10, 10, 3, 3]]}, "preset": "innocent"}}}
    import tempfile
    from PIL import Image
    d = tempfile.mkdtemp()
    Image.new("RGB", (768, 1376), (90, 90, 90)).save(os.path.join(d, "a.jpg"))
    os.environ["SERIES_OFFLINE"] = "1"
    plan = cut.plan_shots(shots, d, frames, WORDS, "lively", 1080, 1920, 30)
    assert [p[5] for p in plan] == ["push", "anim"]
    push, anim = plan
    assert push[4] == anim[3] == anim[4]                 # stops where the effect starts, then still
    assert anim[3][2] <= cut.ANIM_MAX_ZOOM


def test_effect_keeps_last_pose():
    fr = {"animate": {"preset": "innocent"}}
    ev = cut.anim_events(fr, 5.0)
    for e in ev:
        if e["type"] == "pupils" or (e["type"] == "tilt" and e.get("hold")):
            assert e["start"] + e["dur"] > 5.0


def test_karaoke_highlights_each_word_once():
    ev = [("Default", 0.0, 1.0, "Bir iki."), ("Title", 0.0, 3.0, "BAŞLIK")]
    out = cut.karaoke(ev, WORDS)
    subs = [e for e in out if e[0] == "Default"]
    assert len(subs) == 2 and subs[0][3].startswith("{\\c") and "iki." in subs[1][3].split("}")[1]
    assert ("Title", 0.0, 3.0, "BAŞLIK") in out


def test_subtitle_band_follows_the_shot_framing():
    """A face in the upper third of the frame is near the top in a wide shot; in a close shot on the lower body the
    same box leaves the screen, so the preferred band (top) is free again."""
    from series_factory import profiles
    P = profiles.get()
    boxes = [("cat", 0.9, 0.30, 0.05, 0.70, 0.45)]
    wide = cut.shot_position(boxes, 768, 1376, (384, 688, 1.0), 1080, 1920, P, {})
    assert wide in ("bottom", "middle")
    hand = cut.shot_position(boxes, 768, 1376, (384, 688, 1.0), 1080, 1920, P, {"cut": {"subtitle_pos": "top"}})
    assert hand == "top"
