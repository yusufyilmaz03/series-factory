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
pip install -e ".[animate]"           # opsiyonel: üretken AI olmadan kare canlandırma (opencv, rembg)
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
| Kurgu | `series assemble <bölüm> --cut [calm/medium/lively]` (aynı karelerden daha çok çekim, vurgulu kelimeler; [doküman](docs/tr/kurgu.md)) | ffmpeg (+ özne kadrajı için `[subtitles]`) |
| Canlandırma | `series animate presets / grid / set / preview / demo` (durağan karede göz kırpma, bakış, kafa hareketi; [doküman](docs/tr/canlandirma.md)) | `[animate]` eki |
| Kontrol | `series check <bölüm>`, `series strips <bölüm>` | — |
| Toplu | `series batch 013-018`, `series produce <bölüm>` | — |
| Seri | `series status`, `series ideas`, `series todo`, `series canon`, `series docs`; kartlar: `series character / location / sound` | — |
| Formatlar | `series formats [organize / set]`, `series carousel <bölüm>`, `series gemini prepare / collect` (Gemini web) | karusel için Pillow |
| İşler | `series jobs add <komut>`, `series jobs list / log / cancel` (komutları telefondan ya da kum havuzundan seri bilgisayarında çalıştır; çalıştırıcı `series ui` içinde; [doküman](docs/tr/isler.md)) | — |
| Takvim | `series calendar [--stock] [--html f]`, `series schedule add / move / remove / auto`, `series views`, `series ui` | — |
| Yayın | `series publish list / add / sync`, `series drive prepare` | — |

`series help` iş → komut listesini basar. Komutlar kısa özet basar; çoğu `--json` ve `--dry-run` (maliyet tahmini,
hiçbir şey üretmeden) destekler ve onay noktalarında durur; ileride ajanlara hazır.

## Formatlar

Bir serinin birden fazla bölüm formatı olabilir (ör. normal bölüm ve 30 sn'lik kısa); her birinin klasörü, çıktısı (video
ve/veya karusel), kelime sınırı ve yayın kuşağı vardır. `series calendar` ve `series ui` neyin ne zaman yayınlandığını,
neyin planlı olduğunu ve boşlukları gösterir. Bkz. [docs/tr/formatlar-ve-takvim.md](docs/tr/formatlar-ve-takvim.md).

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
