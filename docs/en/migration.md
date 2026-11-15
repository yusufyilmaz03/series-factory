**English** · [Türkçe](../tr/gecis.md)

# Migrating a series from the original pipeline

The original pipeline kept its code inside the series (`<series>/pipeline/`), its settings in `pipeline/ayarlar.json`
and Turkish field names in every data file. `series migrate` turns such a folder into a regular series.

```bash
series migrate "/path/to/series" --dry-run                         # what would change
series migrate "/path/to/series" --extra series_extra.json         # convert (after a backup)
```

What it does:

1. Writes `series.json` from `pipeline/ayarlar.json`: voices, TTS, references, descriptions, image settings, script
   model. Folder and file names stay as they were (`kareler/`, `ses/`, `cikti/`, `Dokümanlar/`, `kayit/` …) through
   `series.json` → `layout` and `paths`, so no file is moved.
2. Converts every episode plan (`script.json` format 2 → 3), montage timing file, the asset map, the library, the
   publish log and every record revision to English field names. The originals are copied first to
   `<trash>/migrate_backup_<time>/`.
3. Merges `--extra`: series knowledge that the old code had hard-coded and `ayarlar.json` never held — character
   aliases, idea types, document names, the writer brief, custom style rules. Write it once per series (see
   [series-config.md](series-config.md)); keep it in the series folder, not in this repository.

Notes:

- API keys are read from `<series>/.env`; copy `pipeline/.env` there.
- The engine also reads unconverted plans (converted in memory), so episodes written later in the old format still
  work. Plans saved by the engine are written in format 3.
- Generated docs (idea views, TODO) mention the new commands after migration, so they show up as "to upload" once.
- `--settings-only` writes only `series.json`.

## Acceptance test used for phase 1

On a temporary copy (never the live folder), with the network disabled (`SERIES_OFFLINE=1`):

- the old `montaj.py` and the new `series assemble` were run on the same episodes; videos were compared frame by frame
  (`ffmpeg -f framemd5`), together with duration and the timing file;
- `durum`, `olaylar --durum bekliyor`, `kanon`, `kontrol` and the card commands were compared with their new
  counterparts (`status`, `ideas --status waiting`, `canon`, `check`, `character`, `location`, `sound`).
