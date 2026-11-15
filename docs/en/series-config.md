**English** · [Türkçe](../tr/seri-ayarlari.md)

# Series settings: `series.json`

A series is a folder with a `series.json` at its root. The engine finds it from `--series <path>`, the `SERIES_ROOT`
environment variable, or by walking up from the current folder. API keys live in `<series>/.env` (never committed).

```text
my-series/
  series.json        settings (this page)
  .env             ANTHROPIC_API_KEY, GEMINI_API_KEY, ELEVENLABS_API_KEY, optional DRIVE_FOLDER_ID, HF_CDN_BASE
  docs/            series documents (canon, rules); generated idea/TODO views
  records/         ideas and TODO items, one folder per record (safe for parallel sessions)
  assets/          character sheets, location plates, audio library, assets.json, library.json
  episodes/NNN_slug/
    script.json    the episode plan (format 3)
    frames/  audio/  output/
```

## Keys

| Key | Meaning |
|---|---|
| `name`, `lang` (`tr`/`en`), `timezone` | series name, message language, time zone for records and dates |
| `profile`, `profile_overrides` | `vertical_short` or `horizontal_long`; override single values (e.g. `{"fps": 25}`) |
| `video` | `font`, `target_lufs` (-14), `end_fade` (seconds of fade to black at the end) |
| `narrator` | character code of the narrator |
| `voices` | `{CODE: {name, id}}` ElevenLabs voices; only characters listed here can speak |
| `tts`, `narration_tts` | ElevenLabs model and settings (lines / narration); `language_code`, `scribe_language` |
| `references` | `{CODE: path}` character sheets and location plates attached to frame prompts |
| `character_descriptions`, `location_descriptions` | one English sentence per code, used in frame prompts |
| `characters` | per character: `display_name` (on-screen name of lines), `aliases` (regexes that find the character in idea texts), `line_colour` (ASS colour of its subtitle lines) |
| `image` | `adapter` (`gemini` / `manual` / `higgsfield`), `model`, `size`, `intro`, `style`, `expression_suffix` |
| `script_writer` | `model`, `max_tokens`, `system_prompt` or `system_prompt_file`, optional `format_file` |
| `ideas` | `types`: `{PREFIX: {name, label, words?}}` idea code prefixes (sort order) and per-type word limits; `labels` override the markers used inside idea texts |
| `docs` | `canon` (character file), `script_context` (doc name prefixes given to the writer), `generated` (file names of generated views), `project_paths` (doc → Claude project path), `generated_title_prefix` |
| `context` | `always`: characters always included in `series context`; `narrator_strip`: regex removed from the narrator's canon section |
| `rules` | style checks: `emotion_tags`, `max_ellipsis`, `address_pattern`, `max_hashtags`, `require_sponsor_slot`, `custom` (see below) |
| `publish` | `platforms`, `cover_file` (e.g. `"{no}_cover.jpg"`) |
| `library` | `sheet_suffix`, `master_suffix` file name parts for generated sheets/plates |
| `subtitles` | `model`: path of the optional YOLO11n ONNX file |
| `paths`, `layout` | folder and file names (defaults are English; a migrated series keeps its old names) |

### Custom style rules

```json
"rules": {"custom": [
  {"field": "narration", "pattern": ",\\s*friend\\s*[.!?]", "flags": "i", "message": "no comma before the address"},
  {"field": "dialogue:HOST", "pattern": "\\bwhatever\\b", "message": "the host never says this"},
  {"field": "hashtags", "pattern": "^#smoke$", "flags": "i", "message": "this tag finds the wrong audience"}
]}
```
`narration` and `dialogue` rules are checked per scene; `dialogue:CODE` only for that character.

## The episode plan (`script.json`, format 3)

The full rules the script writer gets are in [`series_factory/templates/script_format.en.md`](../../series_factory/templates/script_format.en.md).
Core shape:

```json
{"format": 3, "episode_no": 1, "title": "...", "source_idea": "G-01",
 "scenes": [{"no": 1, "narration": "[dramatic] ...", "dialogue": [], "title_text": "...",
             "frames": [{"file": "01_hook.jpg", "motion": "in", "refs": ["CHAR", "PLACE"], "prompt": "...",
                         "reads": ["..."], "subtitle_pos": "top", "hold": 0.5, "transition": "fade"}]}],
 "sfx": [{"id": "door_creak", "anchor": {"word": "Open!"}, "offset": 0, "volume": 0.5}],
 "music": {"id": "music_theme", "volume": 0.12}}
```
Plans written with the original pipeline (format 2, Turkish field names) are read too; they are converted in memory,
and `series migrate` converts the files.
