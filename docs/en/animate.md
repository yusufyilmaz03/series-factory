# Frame animation (`series animate`)

Small 2.5D motions on a single still frame, **without generative AI**: breathing, blinks, squints, pupils, gaze,
head tilt / nod / shake, a jolt, a bounce and ear flicks. Every pixel comes from the frame itself.

How it works: the character is cut out with a mask (rembg), the background behind it is filled with classical
inpainting (OpenCV Telea), and only the character layer is warped. Lids are built from the fur around the eye
(inpainted base colour + fur detail from the strip above the eye). Masks and lid textures are cached in
`<frames>/_animate/`.

```bash
pip install -e ".[animate]"      # numpy, opencv-python-headless, rembg (mask model is downloaded on first use)
```

## Workflow for one frame

```bash
series animate grid 004 05_close.jpg                  # frame with a pixel grid -> read the coordinates
series animate set 004 05_close.jpg --eyes "226,618,75,77;543,613,78,77" \
    --head-pivot 390,1010 --neck 870,1010 --chest 390,1150 --preset innocent
series animate grid 004 05_close.jpg                  # check: eyes, pivot, neck and ears are drawn on it
series animate demo 004 05_close.jpg                  # every preset, labelled, one after another
series animate preview 004 05_close.jpg --preset suspicious --seconds 5
```

Ears are optional: `--ears "tipx,tipy,b0x,b0y,b1x,b1y;..."` (tip and the two ends of the ear base).

## Plan fields (on a frame)

```json
"animate": {
  "anchors": {
    "eyes": [[cx, cy, rx, ry]],
    "head_pivot": [x, y],
    "neck": [y0, y1],
    "chest": [x, y],
    "ears": [{"tip": [x, y], "base": [[x, y], [x, y]]}]
  },
  "preset": "suspicious",
  "events": []
}
```

`events` (optional) replaces the preset with a hand-made timeline:
`{"type": "blink" | "slow_blink" | "squint" | "pupils" | "look" | "look_path" | "tilt" | "nod" | "shake" | "jolt" |
"bounce" | "ear_flick", "start": s, "dur": s, ...}`. `series animate presets --json` prints every preset as an example.

## Presets

| Name | Motion |
|---|---|
| `idle` | breathing, two blinks |
| `innocent` | pupils widen, slow head tilt, slow blink |
| `suspicious` | held squint, looks right then left |
| `eye_roll` | eyes roll up and across, light squint, blink |
| `surprised` | jolt, pupils shrink, bounce, double blink |
| `sleepy` | lids drop, head sinks and snaps back |
| `no` / `yes` | head shake / nod |
| `smug` | chin up, flat squint, side glance |
| `love` | two slow blinks ("cat kiss") with a tilt |
| `ears` | ear flicks (needs ear anchors) |

## Limits

- Close and medium shots. In wide shots the eyes are too small for lids; use breathing and head motions only.
- One character per frame. Other subjects in the mask stay still: motion is limited to the area around the anchors.
- No walking or large limb motion: that needs a rigged puppet (Live2D / Inochi2D / Spine) or 3D.
