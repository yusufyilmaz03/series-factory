[English](../en/series-config.md) · **Türkçe**

# Seri ayarları: `series.json`

Bir seri, kökünde `series.json` bulunan bir klasördür. Motor onu `--series <yol>`, `SERIES_ROOT` ortam değişkeni ya da
bulunduğun klasörden yukarı doğru arayarak bulur. API anahtarları `<seri>/.env` dosyasında durur (asla commit edilmez).

```text
serim/
  series.json        ayarlar (bu sayfa)
  .env             ANTHROPIC_API_KEY, GEMINI_API_KEY, ELEVENLABS_API_KEY, opsiyonel DRIVE_FOLDER_ID, HF_CDN_BASE
  docs/            seri dokümanları (kanon, kurallar); üretilen olay/TODO görünümleri
  records/         olaylar ve TODO maddeleri, her kayıt ayrı klasör (paralel oturumlarda güvenli)
  assets/          karakter sayfaları, mekân planları, ses kütüphanesi, assets.json, library.json
  episodes/NNN_slug/
    script.json    bölüm planı (format 3)
    frames/  audio/  output/
```

## Alanlar

| Alan | Anlamı |
|---|---|
| `name`, `lang` (`tr`/`en`), `timezone` | seri adı, mesaj dili, kayıtlar ve tarihler için saat dilimi |
| `profile`, `profile_overrides` | `vertical_short` ya da `horizontal_long`; tek tek değerleri ez (ör. `{"fps": 25}`) |
| `video` | `font`, `target_lufs` (-14), `end_fade` (sondaki kararma, sn) |
| `narrator` | anlatıcının karakter kodu |
| `voices` | `{KOD: {name, id}}` ElevenLabs sesleri; yalnızca burada olan karakterler konuşabilir |
| `tts`, `narration_tts` | ElevenLabs modeli ve ayarları (replik / anlatım); `language_code`, `scribe_language` |
| `references` | `{KOD: yol}` kare istemlerine eklenen karakter sayfaları ve mekân planları |
| `character_descriptions`, `location_descriptions` | her kod için kare istemlerinde kullanılan tek İngilizce cümle |
| `characters` | karakter başına: `display_name` (repliklerde ekrandaki ad), `aliases` (olay metinlerinde karakteri bulan regex'ler), `line_colour` (altyazı satırının ASS rengi) |
| `image` | `adapter` (`gemini` / `manual` / `higgsfield`), `model`, `size`, `intro`, `style`, `expression_suffix` |
| `script_writer` | `model`, `max_tokens`, `system_prompt` ya da `system_prompt_file`, opsiyonel `format_file` |
| `ideas` | `types`: `{ÖNEK: {name, label, words?}}` olay kodu önekleri (sıralama) ve tipe özel kelime sınırları; `labels` olay metinlerindeki işaretleri değiştirir |
| `docs` | `canon` (karakter dosyası), `script_context` (senaristin aldığı doküman önekleri), `generated` (üretilen görünümlerin adları), `project_paths` (doküman → Claude proje yolu), `generated_title_prefix` |
| `context` | `always`: `series context`'te hep bulunan karakterler; `narrator_strip`: anlatıcının kanon bölümünden çıkarılan regex |
| `rules` | yazım kontrolleri: `emotion_tags`, `max_ellipsis`, `address_pattern`, `max_hashtags`, `require_sponsor_slot`, `custom` (aşağıda) |
| `formats`, `schedule` | bölüm formatları ve yayın kuşakları, bkz. [formatlar-ve-takvim.md](formatlar-ve-takvim.md) |
| `carousel` | slayt görünümü: `width`, `height`, `font`, `accent` / `dark` / `text` renkleri, `handle`, `signature`, `quality` |
| `publish` | `platforms`, `cover_file` (ör. `"{no}_kapak.jpg"`) |
| `library` | üretilen sayfa/planların dosya adı parçaları: `sheet_suffix`, `master_suffix` |
| `subtitles` | `model`: opsiyonel YOLO11n ONNX dosyasının yolu |
| `paths`, `layout` | klasör ve dosya adları (varsayılanlar İngilizce; taşınan seri eski adlarını korur) |

### Seriye özel yazım kuralları

```json
"rules": {"custom": [
  {"field": "narration", "pattern": ",\\s*dostum\\s*[.!?]", "flags": "i", "message": "hitaptan önce virgül yok"},
  {"field": "dialogue:SUNUCU", "pattern": "\\bneyse\\b", "message": "sunucu bunu asla demez"},
  {"field": "hashtags", "pattern": "^#sis$", "flags": "i", "message": "bu etiket yanlış kitleyi getirir"}
]}
```
`narration` ve `dialogue` kuralları sahne sahne denetlenir; `dialogue:KOD` yalnızca o karakter için.

## Bölüm planı (`script.json`, format 3)

Senaristin aldığı kuralların tamamı [`series_factory/templates/script_format.tr.md`](../../series_factory/templates/script_format.tr.md)
dosyasında. Temel yapı:

```json
{"format": 3, "episode_no": 1, "title": "...", "source_idea": "G-01",
 "scenes": [{"no": 1, "narration": "[dramatic] ...", "dialogue": [], "title_text": "...",
             "frames": [{"file": "01_kanca.jpg", "motion": "in", "refs": ["KARAKTER", "MEKAN_KODU"], "prompt": "...",
                         "reads": ["..."], "subtitle_pos": "top", "hold": 0.5, "transition": "fade"}]}],
 "sfx": [{"id": "kapi_gicirti", "anchor": {"word": "Aç!"}, "offset": 0, "volume": 0.5}],
 "music": {"id": "muzik_tema", "volume": 0.12}}
```
Eski hatla yazılmış planlar (format 2, Türkçe alan adları) da okunur; bellekte çevrilir, `series migrate` dosyaları çevirir.
