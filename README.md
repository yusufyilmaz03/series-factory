**English** · [Türkçe](README.tr.md)

# series-factory

An AI-assisted production line for episodic short videos:
**script plan → frames → voice → edit → check → publish**, one command per step, for any series.

It was extracted from a working pipeline that produced 80+ episodes of a Turkish vertical-video series, then made
series-independent: everything about a particular series (characters, voices, image style, rules, folder names) lives
in that series' own `series.json`, never in the code.

## Two ways to use it

- **Chat layer** (no install, no API keys): the plan format, prompt templates and checklists can be used inside a Claude
  chat; you generate frames and audio in your own tools. `--manual` modes write ready-to-paste prompts and guides.
- **Full layer** (this engine + API keys): the whole line runs locally. Every step skips what already exists, so a
  half-finished run is resumed by running the same command again.

## Install

```bash
pip install -e .                      # the `series` command; Python 3.10+, Pillow
pip install -e ".[subtitles]"         # optional: automatic subtitle placement (numpy, onnxruntime)
pip install -e ".[animate]"           # optional: frame animation without generative AI (opencv, rembg)
```
You also need `ffmpeg`/`ffprobe` with libass (macOS: `brew install ffmpeg-full`).

## Quick start

```bash
series init "My Series" --series-lang en       # new series folder with series.json, docs/, .env.example
cd "My Series"
series script new --manual                     # prompt for a Claude chat -> series script save answer.json
series check 001                               # plan validation + style rules
series frames 001 --dry-run                    # what would be generated
series produce 001                             # frames -> voice -> assemble (does what is missing)
series strips 001                              # timing report + motion strips of the finished video
```
Try it on the bundled fictional example: `series --series example_series status`, `series --series example_series check 001`.

## Commands

| Step | Command | Needs |
|---|---|---|
| Script | `series script new / validate / save`, `series context <idea>` | `ANTHROPIC_API_KEY` (or `--manual`) |
| Frames | `series frames <ep>` with an image adapter: `gemini`, `manual`, `higgsfield` (optional, `series hf …`) | `GEMINI_API_KEY` for `gemini` |
| Voice | `series voice episode <ep>` (narration + word timings, lines, sfx, music) | `ELEVENLABS_API_KEY` |
| Edit | `series assemble <ep>` (Ken Burns, transitions, subtitles, mix, loudness) | ffmpeg |
| Cut | `series assemble <ep> --cut [calm/medium/lively]` (more shots from the same frames, highlighted words; [docs](docs/en/cut.md)) | ffmpeg (+ `[subtitles]` for subject framing) |
| Animate | `series animate presets / grid / set / preview / demo` (blinks, gaze, head motion on a still frame; [docs](docs/en/animate.md)) | `[animate]` extra |
| Check | `series check <ep>`, `series strips <ep>` | — |
| Batch | `series batch 013-018`, `series produce <ep>` | — |
| Series | `series status`, `series ideas`, `series todo`, `series canon`, `series docs`, cards: `series character / location / sound` | — |
| Formats | `series formats [organize / set]`, `series carousel <ep>`, `series gemini prepare / collect` (Gemini web) | Pillow for carousels |
| Jobs | `series jobs add <command>`, `series jobs list / log / cancel` (run commands on the series computer from a phone or sandbox; worker inside `series ui`; [docs](docs/en/jobs.md)) | — |
| Calendar | `series calendar [--stock] [--html f]`, `series schedule add / move / remove / auto`, `series views`, `series ui` | — |
| Publish | `series publish list / add / sync`, `series drive prepare` | — |

`series help` prints the job → command list. Commands print a short summary; most support `--json` and `--dry-run`
(cost estimate, nothing produced), and they stop at approval points — ready for agents later.

## Formats

A series can have several episode formats (e.g. a normal episode and a 30 s short), each with its own folder, output
(video and/or carousel), word limits and posting slot; `series calendar` and `series ui` show what was posted when, what
is scheduled and where the gaps are. See [docs/en/formats-and-calendar.md](docs/en/formats-and-calendar.md).

Each format uses a profile: `vertical_short` (45–75 s, 1080×1920; tuned) or `horizontal_long` (8–15 min,
1920×1080; skeleton, phase 2). Size, fps, subtitle layout and length rules come from the profile.

## Languages

Code and data field names are English. Messages follow the series language (`"lang": "tr" | "en"`, or `--lang`).
Docs exist in both languages.

## Migrating a series made with the original pipeline

`series migrate <folder> [--extra series_extra.json]` converts `pipeline/ayarlar.json` into `series.json` and every plan,
timing file, asset map and record from Turkish to English field names (after a backup). Folder and file names are
kept. See [docs/en/migration.md](docs/en/migration.md).

## Docs

- [Series settings (`series.json`)](docs/en/series-config.md)
- [Migration](docs/en/migration.md)

## Contributing

Run `python3 scripts/leak_check.py` before committing (or enable the hook: `git config core.hooksPath .githooks`).
Tests: `python3 -m pytest -q` (offline, no keys needed).

## License

MIT. The optional subtitle placement can use the Ultralytics YOLO11n weights, which are AGPL-3.0; they are not part of
this repository and are only used if you export and point to them yourself (`series subtitles model`).
