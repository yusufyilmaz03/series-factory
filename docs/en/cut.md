# Motion-comic cut (`series assemble <ep> --cut`)

More shots from the same frames, no generated pixels. The whole assemble pipeline stays (audio mix, lines, titles,
subtitle positions); only the picture changes, and subtitles highlight the word being spoken.

```bash
series assemble 004 --cut            # medium (default) -> output/<episode>_cut.mp4
series assemble 004 --cut calm       # fewer shots
series assemble 004 --cut lively     # more shots
```

## Rules

| | calm | medium | lively |
|---|---|---|---|
| shortest shot | 3.2 s | 1.8 s | 1.2 s |
| target shot | 4.0 s | 2.6 s | 1.8 s |
| shots per frame (max) | 2 | 3 | 4 |

- Cuts only at the end of a sentence or clause (word timings).
- Shots alternate: wide (slow push towards the subject) → close on the subject → medium. The subject comes from the
  object detector of the `subtitles` extra (animals first, then people); without it, the frame centre.
- Subtitle band is chosen per shot, on what is actually on screen (the frame's boxes moved into the shot's framing,
  faces weighted, same rules as `series subtitles`); `"cut": {"subtitle_pos": ...}` on a frame overrides it.
- Moves are slow pushes; no shakes, no speed lines. Small frames are not enlarged beyond ~2x.
- A frame with a character effect (`frame.animate`, see [animate.md](animate.md)) is not split: the camera pushes in to at
  most **1.35x**, stops where the effect starts and stays still; the effect keeps its last pose (it does not go back) and
  breathing is off.

## Frame fields (optional)

```json
"cut": {"subject": [x, y], "height": 0.5, "close": 1.8, "split": false},
"accent": {"mark": "?", "word": "bakarım."}
```

`subject` overrides the detector (pixels of the frame), `split: false` keeps the frame as one shot, `accent` pops a small
mark in at that word.

Effect masks are cached in `<frames>/_animate/` (`SERIES_ANIMATE_CACHE` moves the cache elsewhere).
