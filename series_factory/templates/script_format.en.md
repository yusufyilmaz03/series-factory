## script.json (format 3) rules
- "format": 3, episode_no, title, genre, source_idea (code from the idea pool, e.g. "G-05"), target_sec, hook, caption,
  hashtags, sponsor_slot {scene_no, description}, closing {line, real_footage_note}, canon_updates [..].
- "slug": short folder name, ASCII only, underscores (e.g. "neighbour_visit").
- "summary": a readable 3–5 sentence summary.
- Locations: the series has a fixed location library (codes and descriptions below). If a frame happens in one of them,
  add that location's code to refs; viewers should see the same places in every episode. Only if a place is missing
  from the library, write set_frame {file: "00_<place>.jpg", prompt} (no characters, English, ends with
  "No people, no animals.") and use the SET code in those frames.
- scenes[]: {no, duration_sec, narration, dialogue[], title_text|null, frames[]}
  * narration: the narrator's text. Use short sentences so it reads aloud smoothly. No digits; write numbers as words.
    Emotion tags (ElevenLabs, English, square brackets, e.g. [dramatic], [deadpan]): one at the start of every scene and,
    if needed, before a sentence where the tone changes. Tags are not spoken and never reach the subtitles.
    Use punctuation for emphasis: "!" adds energy; "..." is a curious pause (use sparingly); ";" gives a short, tense pause.
    start_word and anchor words are written without tags and with EXACTLY the same punctuation.
  * frames[]: 1–2 frames per scene. {file: "NN_name.jpg" (two-digit scene number, a second frame like 05b),
    motion: in|out|panR|panL|fast|static, refs: [...], prompt: English scene description,
    start_word?: (only for the 2nd and later frames) the single word where the frame starts, EXACTLY as in narration,
    video_prompt?: English, only for an action moment,
    subtitle_pos?: "top" | "middle" — move subtitles up when the main subject sits in the lower half; otherwise omit (bottom),
    reads: [short] the 1–3 things the viewer must understand IN ORDER in this frame (see "Timing"),
    hold?: 0.3–1.5 (s) silent screen time after the frame's words; only when an important moment must land,
    transition?: how this frame is entered; "cut" | "fade" | "fadeblack" | "fadewhite" | "dissolve" | "slideleft" |
    "slideright" | "slideup" | "slidedown" | "smoothleft" | "smoothright" | "wipeleft" | "wiperight" | "circleopen" |
    "circleclose" | "radial" | "hblur" or {"type": "...", "duration": 0.2–0.8}. Default: "fade" (0.35 s) at scene
    starts, "cut" inside a scene.}
  * refs come from: character codes, location codes (library), SET (if there is an episode set frame), or a frame file
    that comes EARLIER in the same episode (continuity). Every character visible in the frame needs its sheet.
  * a frame prompt only describes the scene; style and the intro sentence are added automatically. Name characters.
    Make camera angle, composition, expression and who-is-where clear.
  * dialogue[]: spoken lines of characters other than the narrator {character: "<CODE>", text, at}. at:
    {"frame_start": "<frame file>"} or {"after_word": "<word EXACTLY as in narration>"}. Keep lines short (1–6 words).
    Only characters with a voice in the series settings can speak.

## Timing: reads (timing is the most common mistake)
The viewer sees the video once, at full speed, for the first time. You know what happens; they do not.
- Write "reads" for every frame: what the viewer must understand in this frame, in order. A read is something seen or
  heard on screen, not information.
- Finding and understanding one read takes at least ~1.2 s. Narration runs ~2 words per second; a frame lasts
  ≈ words/2 + lines + hold. If the reads do not fit, split the frame, drop a read or add "hold"; never cram.
- One read at a time. Cause and reaction do not overlap: show what happens first, then the reaction.
- Fast action, slow meaning: an action frame can be short, but the result or reaction after it needs time.
- Lead the eye: before an important read the character looks at it, the camera moves to it, or it is centred.
- Use "hold" sparingly (1–3 times per episode): after the climax result, the funniest reaction and the closing.
  Do not end before the last read of the last frame lands (hold ≥ 0.8 on the last frame).
- The hook is in the first frame and the first sentence; the first frame never opens from black.

## Stay alive
- No dead frames: "static" only for frames shorter than 2 s. Two frames in a row never share a motion.
- "fast" for action, "in"/"out" for calm narration, "panR"/"panL" to show a place or two things side by side.
- Every scene start is a transition. Choose it by story: time jump "fadeblack", dream or memory "fadewhite"/"dissolve",
  change of direction "slideleft"/"slideright", fast escape "smoothleft". Cut inside a scene on action.

- sfx[]: {id (snake_case), prompt (English, ElevenLabs sound effect), duration (s, ≤ 5), anchor, offset (s), volume (0.2–0.8)}.
  anchor: {"scene": no} | {"word": "<word EXACTLY as in narration>"} | {"line": n (line order, from 1)}.
  Reusing a library id avoids generating it again (list below). 5–9 effects are enough.
- music: {id, prompt (English, instrumental loop), duration: 22, volume: 0.10–0.14, mute?: [{anchor, offset}, {anchor, offset}]}
  (mute: a dramatic moment where the music drops out, between two anchors). A library track can be reused.
- scenes[].title_steps?: an on-screen title that changes step by step [{text, anchor?, offset?}].
