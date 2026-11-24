[English](../en/formats-and-calendar.md)

# Bölüm formatları, kuşaklar ve yayın takvimi

Bir seri birden fazla türde bölüm yapabilir (normal bölüm, 30 saniyelik kısa, kaydırmalı kılavuz…) ve bunları günün
farklı kuşaklarında yayınlayabilir. Bunların hiçbiri koda gömülü değildir; hepsi `series.json`'da durur.

## `formats`

```json
"formats": {
  "normal": {"label": "Bölüm", "folder": "normal", "output": ["video"], "idea_types": ["G", "K"],
             "counter": {"label": "Bölüm {n}"}, "default": true},
  "kisa":   {"label": "Kısalar", "folder": "kisa", "output": ["video"], "idea_types": ["T"],
             "words": {"min": 30, "max": 80, "target": "35–70"}, "counter": {"label": "Kısa {n}"}},
  "kilavuz": {"label": "Kılavuz", "folder": "kilavuz", "output": ["carousel", "video"], "ready": "any",
              "idea_types": ["B"], "platforms": ["instagram", "tiktok"], "counter": {"label": "Kılavuz #{n}"}}
}
```

| Alan | Anlamı |
|---|---|
| `label` | raporlarda ve ekranda görünen ad |
| `folder` | bu formatın bölümleri `episodes/<folder>/NNN_slug/` altında durur (`""`: doğrudan `episodes/`) |
| `output` | formatın çıktısı: `video`, `carousel` ya da ikisi |
| `ready` | `all` (varsayılan): bütün çıktılar hazır olmalı; `any`: biri yeter |
| `idea_types` | bu formata ait olay kodu önekleri (`T-04` için yazılan plan `kisa` altına kaydedilir) |
| `words` | bu formatın anlatım kelime sınırları (yoksa profilinki) |
| `profile`, `profile_overrides` | bu format için farklı boyut / altyazı düzeni |
| `counter` | takvimdeki numara: `{"label": "Kısa {n}", "start": 1}` (takvim sırasına göre sayılır) |
| `platforms` | bu formatın yayınlandığı platformlar (varsayılan: `publish.platforms`) |
| `sequential` | numaralı başlıklar: `series schedule auto` bu formatın takvimdeki bir bölümünden önceye bölüm koymaz |
| `start` | `series schedule auto`un bu format için kullanabileceği ilk tarih (YYYY-AA-GG) |
| `order` | isteğe bağlı yayın sırası, `series schedule auto` için (bölüm numaraları; kalanlar numara sırasıyla) |
| `default` | klasörü, planı ve olayı bir şey söylemeyen bölümün formatı |

Bir bölümün formatı sırayla: format klasörü, plandaki `episode_format`, olay tipi, varsayılan format.
`series formats` formatları aşama sayılarıyla listeler; `series formats organize` klasörsüz bölümleri klasörlerine
taşır (yayın kaydındaki yollar da güncellenir); `series formats set 087 kisa` tek bölümü taşır.

## `schedule`

```json
"schedule": {
  "slots": {
    "noon":    {"label": "Öğle", "time": "12:00", "days": "daily", "formats": ["kisa", "kilavuz"],
                "weekday_formats": {"tue": ["kilavuz"]}},
    "evening": {"label": "Akşam", "time": "18:00", "days": "daily", "formats": ["normal"]}
  },
  "horizon_days": 28,
  "assume_published": true
}
```

| Alan | Anlamı |
|---|---|
| `slots.<anahtar>.time` | yayın saati (serinin `timezone` değeri) |
| `slots.<anahtar>.days` | `daily` ya da `mon … sun` listesi |
| `slots.<anahtar>.formats` | bu kuşakta yayınlanan formatlar |
| `slots.<anahtar>.weekday_formats` | isteğe bağlı: hangi gün hangi format(lar) (yoksa en uzun süredir kullanılmayan format) |
| `horizon_days` | `series schedule auto` varsayılan olarak kaç gün ileriye planlar |
| `assume_published` | saati geçmiş planlı gönderi yayında sayılır (zamanlayıcı zamanında paylaşır) |
| `exclude` | yayına hiç önerilmeyecek bölümler (ör. alternatif kurgu) |

## Takvim nereden gelir

| Durum | Kaynak |
|---|---|
| yayında / planlı | yayın kaydı (`series publish add`, `series publish sync`) |
| taslak | plan dosyası (`paths.schedule`, varsayılan `publish/schedule.json`), `series schedule` yazar |
| boş | içinde bir şey olmayan kuşak günü |

```
series calendar                          bu hafta + 3 hafta
series calendar --from 2026-11-16        geçmiş dahil
series calendar --stock                  kuşak başına hazır stok, üretim hattı, ilk plansız gün, stoğun bittiği gün
series schedule auto --until 2026-12-31  boş kuşak günlerini hazır bölümlerle doldur (en küçük numara önce)
series schedule add 094 --date 2026-12-01 --slot noon · move · remove · list
series publish sync [--from-file zamanlayici.json]
series views                             views/<durum>/<tarih>_<saat>_<format>_<bölüm> kısayolları
series ui                                aynısı yerel ekranda (hazır bölümü boş güne sürükle)
series calendar --html takvim.html       ekranın salt okunur tek dosyalık kopyası
```

## Yerel ekran

`series ui` bilgisayarında `http://127.0.0.1:8765` adresinde küçük bir sunucu açar (yalnızca bu bilgisayar erişir) ve
tarayıcıyı açar. Veritabanı yoktur: her istek seri klasörünü okur, ekrandaki planlama `series schedule` ile aynı kodu
çağırır; klasör tek doğru kaynak olarak kalır. Sekmeler: takvim (iki kuşaklı hafta ızgarası, yanda hazır stok,
sürükleyerek planla, × ile plandan çıkar), bölümler (kareler, video, karusel, yayın durumu), stok, olaylar, TODO.
