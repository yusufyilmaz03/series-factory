[English](README.md) · **Türkçe**

# series-factory

Bölümlü kısa videolar için yapay zekâ destekli üretim hattı:
**senaryo planı → kareler → seslendirme → montaj → kontrol → yayın**; her adım tek komut, her seri için.

Türkçe bir dikey video serisinin 80'den fazla bölümünü üreten çalışan bir hattan çıkarıldı ve seriden bağımsız hâle
getirildi: bir seriye ait her şey (karakterler, sesler, görsel stil, kurallar, klasör adları) o serinin kendi
`series.json` dosyasında durur, koda gömülmez.

## İki kullanım katmanı

- **Sohbet katmanı** (kurulum ve API anahtarı gerekmez): plan formatı, istem şablonları ve kontrol listeleri bir Claude
  sohbetinde kullanılabilir; kareleri ve sesleri kendi araçlarında üretirsin. `--manual` kipleri yapıştırmaya hazır
  istemler ve rehberler yazar.
- **Tam katman** (bu motor + API anahtarları): hattın tamamı yerelde çalışır. Her adım var olanı atlar; yarıda kalan
  iş aynı komutu yeniden çalıştırınca kaldığı yerden sürer.

## Kurulum

```bash
pip install -e .                      # `series` komutu; Python 3.10+, Pillow
pip install -e ".[subtitles]"         # opsiyonel: otomatik altyazı yerleşimi (numpy, onnxruntime)
```
Ayrıca libass destekli `ffmpeg`/`ffprobe` gerekir (macOS: `brew install ffmpeg-full`).

## Hızlı başlangıç

```bash
series init "Serim" --series-lang tr           # series.json, docs/, .env.example içeren yeni seri klasörü
cd "Serim"
series script new --manual                     # Claude sohbeti için istem -> series script save cevap.json
series check 001                               # plan doğrulama + yazım kuralları
series frames 001 --dry-run                    # neler üretilecek
series produce 001                             # kareler -> ses -> montaj (eksik olanları yapar)
series strips 001                              # bitmiş videonun zamanlama raporu + hareket şeritleri
```
Repodaki uydurma örnek seriyle dene: `series --series example_series status`, `series --series example_series check 001`.

## Komutlar

| Adım | Komut | Gerekenler |
|---|---|---|
| Senaryo | `series script new / validate / save`, `series context <olay>` | `ANTHROPIC_API_KEY` (ya da `--manual`) |
| Kareler | `series frames <bölüm>`; görsel adaptörü: `gemini`, `manual`, `higgsfield` (opsiyonel, `series hf …`) | `gemini` için `GEMINI_API_KEY` |
| Ses | `series voice episode <bölüm>` (anlatım + kelime zamanları, replikler, efekt, müzik) | `ELEVENLABS_API_KEY` |
| Montaj | `series assemble <bölüm>` (Ken Burns, geçişler, altyazı, miksaj, ses seviyesi) | ffmpeg |
| Kontrol | `series check <bölüm>`, `series strips <bölüm>` | — |
| Toplu | `series batch 013-018`, `series produce <bölüm>` | — |
| Seri | `series status`, `series ideas`, `series todo`, `series canon`, `series docs`; kartlar: `series character / location / sound` | — |
| Yayın | `series publish list / add`, `series drive prepare` | — |

`series help` iş → komut listesini basar. Komutlar kısa özet basar; çoğu `--json` ve `--dry-run` (maliyet tahmini,
hiçbir şey üretmeden) destekler ve onay noktalarında durur; ileride ajanlara hazır.

## Formatlar

Seri bir format profili seçer: `vertical_short` (45–75 sn, 1080×1920; ayarlı) ya da `horizontal_long` (8–15 dk,
1920×1080; iskelet, 2. aşama). Boyut, fps, altyazı yerleşimi ve uzunluk kuralları profilden gelir.

## Dil

Kod ve veri alan adları İngilizce. Mesajlar serinin diline göre basılır (`"lang": "tr" | "en"` ya da `--lang`).
Dokümanlar iki dilde de var.

## Eski hatla yapılmış bir seriyi taşımak

`series migrate <klasör> [--extra seri_ek.json]`, `pipeline/ayarlar.json` dosyasını `series.json`'a, bütün planları,
zaman dosyalarını, varlık haritasını ve kayıtları Türkçe alan adlarından İngilizceye çevirir (önce yedek alır).
Klasör ve dosya adları korunur. Bkz. [docs/tr/gecis.md](docs/tr/gecis.md).

## Dokümanlar

- [Seri ayarları (`series.json`)](docs/tr/seri-ayarlari.md)
- [Geçiş (migrate)](docs/tr/gecis.md)

## Katkı

Commit'ten önce `python3 scripts/leak_check.py` çalıştır (ya da kancayı aç: `git config core.hooksPath .githooks`).
Testler: `python3 -m pytest -q` (ağsız, anahtar gerekmez).

## Lisans

MIT. Opsiyonel altyazı yerleşimi Ultralytics YOLO11n ağırlıklarını kullanabilir; bunlar AGPL-3.0 lisanslıdır, bu
reponun parçası değildir ve yalnızca sen dışa aktarıp yolunu verirsen kullanılır (`series subtitles model`).
