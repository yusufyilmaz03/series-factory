"""Format profiles: everything that depends on the target format (size, fps, subtitle layout, length).

A series picks one with `series.json` -> "profile" and may override single values with
`series.json` -> "profile_overrides" (deep-merged).

- vertical_short: 45–75 s vertical Reels/Shorts (the values the source pipeline was built and tested with).
- horizontal_long: 8–15 min horizontal YouTube story. Skeleton only in phase 1: values are a reasonable
  starting point but have not been tuned on a real episode yet.
"""
import copy

# ASS colours are &HAABBGGRR.
_WHITE, _GREEN, _YELLOW, _SHADOW = "&H00FFFFFF", "&H00A8F0C8", "&H0040D8FF", "&H64000000"

PROFILES = {
    "vertical_short": {
        "width": 1080, "height": 1920, "fps": 30, "aspect": "9:16",
        "words": {"min": 90, "max": 190, "target": "110–170"},
        "subtitles": {
            "max_words": 4,              # per subtitle chunk (5 allowed when one word would be left alone)
            "margin_l": 90, "margin_r": 140,
            "narration": {"size": 72, "colour": _WHITE, "italic": 0},
            "line": {"size": 62, "colour": _GREEN, "italic": -1},      # other characters' spoken lines
            "title": {"size": 74, "colour": _YELLOW, "spacing": 2, "outline": 7, "shadow": 3, "margin_v": 230},
            # position -> (alignment, narration margin_v, line margin_v); "top2" = top while a title is on screen
            "positions": {"bottom": (2, 440, 560), "top": (8, 360, 520), "top2": (8, 560, 700),
                          "middle": (8, 860, 860)},
        },
        # automatic subtitle placement: output-pixel bands each position covers
        "bands": {"narration": {"bottom": (1290, 1490), "top": (355, 545), "middle": (855, 1045)},
                  "line": {"bottom": (1190, 1360), "top": (520, 700), "middle": (1040, 1200)},
                  "horizontal": (0.12, 0.88)},
        "end_pad": 0.5,          # silence after the last word
        "title_min": 2.6,        # an on-screen title stays at least this long
        "default_line_gap": 1.4,
        "contact": {"thumb": (270, 480), "tile": "6x2"},
        "strip_width": 216,
    },
    "horizontal_long": {
        "width": 1920, "height": 1080, "fps": 30, "aspect": "16:9",
        "words": {"min": 1100, "max": 2400, "target": "1300–2000"},
        "subtitles": {
            "max_words": 7,
            "margin_l": 200, "margin_r": 200,
            "narration": {"size": 54, "colour": _WHITE, "italic": 0},
            "line": {"size": 48, "colour": _GREEN, "italic": -1},
            "title": {"size": 58, "colour": _YELLOW, "spacing": 2, "outline": 6, "shadow": 3, "margin_v": 70},
            "positions": {"bottom": (2, 70, 140), "top": (8, 120, 190), "top2": (8, 200, 270),
                          "middle": (8, 470, 540)},
        },
        "bands": {"narration": {"bottom": (920, 1030), "top": (110, 220), "middle": (460, 570)},
                  "line": {"bottom": (850, 950), "top": (180, 280), "middle": (530, 630)},
                  "horizontal": (0.1, 0.9)},
        "end_pad": 0.8,
        "title_min": 3.0,
        "default_line_gap": 1.4,
        "contact": {"thumb": (480, 270), "tile": "4x3"},
        "strip_width": 320,
        "experimental": True,
    },
}


def _merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def get(name="vertical_short", overrides=None):
    if name not in PROFILES:
        raise SystemExit(f"unknown format profile: {name} (choices: {', '.join(PROFILES)})")
    return _merge(PROFILES[name], overrides)


def ass_styles(p, font, line_styles=None):
    """[V4+ Styles] lines for a profile. line_styles: {style_name: colour} extra per-character line styles."""
    s = p["subtitles"]
    fmt = ("Style: {name},{font},{size},{colour},&H00FFFFFF,&H00000000,{shadow_c},-1,{italic},0,0,100,100,"
           "{spacing},0,1,{outline},{shadow},{align},{ml},{mr},{mv},1")

    def line(name, kind, align, mv, colour=None):
        k = s[kind]
        return fmt.format(name=name, font=font, size=k["size"], colour=colour or k["colour"], shadow_c=_SHADOW,
                          italic=k.get("italic", 0), spacing=k.get("spacing", 0), outline=k.get("outline", 6),
                          shadow=k.get("shadow", 2), align=align, ml=s["margin_l"], mr=s["margin_r"], mv=mv)

    suffix = {"bottom": "", "top": "Top", "top2": "Top2", "middle": "Mid"}
    out = []
    styles = {"Line": None, **(line_styles or {})}
    for pos in ("bottom", "top", "top2", "middle"):
        align, mv_n, mv_l = s["positions"][pos]
        out.append(line("Default" + suffix[pos], "narration", align, mv_n))
        for name, colour in styles.items():
            out.append(line(name + suffix[pos], "line", align, mv_l, colour))
    out.append(line("Title", "title", 8, s["title"]["margin_v"]))
    return out


POSITION_SUFFIX = {"bottom": "", "top": "Top", "top2": "Top2", "middle": "Mid"}
