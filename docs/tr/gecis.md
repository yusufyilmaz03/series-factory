[English](../en/migration.md) · **Türkçe**

# Eski hatla yapılmış bir seriyi taşımak

Eski hat kodunu serinin içinde (`<seri>/pipeline/`), ayarlarını `pipeline/ayarlar.json` dosyasında tutuyor ve bütün
veri dosyalarında Türkçe alan adları kullanıyordu. `series migrate` böyle bir klasörü normal bir seriye çevirir.

```bash
series migrate "/seri/yolu" --dry-run                        # neler değişecek
series migrate "/seri/yolu" --extra seri_ek.json             # çevir (önce yedek alır)
```

Ne yapar:

1. `pipeline/ayarlar.json`'dan `series.json` yazar: sesler, TTS, referanslar, tanımlar, görsel ayarları, senaryo modeli.
   Klasör ve dosya adları olduğu gibi kalır (`kareler/`, `ses/`, `cikti/`, `Dokümanlar/`, `kayit/` …); bunu
   `series.json` → `layout` ve `paths` sağlar, hiçbir dosya taşınmaz.
2. Bütün bölüm planlarını (`script.json` format 2 → 3), montaj zaman dosyalarını, varlık haritasını, kütüphaneyi,
   yayın kaydını ve her kayıt sürümünü İngilizce alan adlarına çevirir. Orijinaller önce
   `<çöp klasörü>/migrate_backup_<zaman>/` altına kopyalanır.
3. `--extra` dosyasını birleştirir: eski kodun içine gömülü olan ama `ayarlar.json`'da hiç bulunmayan seri bilgisi —
   karakter takma adları, olay tipleri, doküman adları, senarist yönergesi, seriye özel yazım kuralları. Seri başına
   bir kez yazılır (bkz. [seri-ayarlari.md](seri-ayarlari.md)); bu repoda değil, serinin klasöründe durur.

Notlar:

- API anahtarları `<seri>/.env` dosyasından okunur; `pipeline/.env` dosyasını oraya kopyala.
- Motor çevrilmemiş planları da okur (bellekte çevirir); eski formatta sonradan yazılan bölümler de çalışır. Motorun
  kaydettiği planlar format 3 olarak yazılır.
- Üretilen dokümanlar (olay görünümleri, TODO) geçişten sonra yeni komutları andığı için bir kez "yüklenecek" görünür.
- `--settings-only` yalnızca `series.json` yazar.

## 1. aşamada kullanılan kabul testi

Geçici bir kopyada (canlı klasörde asla), ağ kapalıyken (`SERIES_OFFLINE=1`):

- eski `montaj.py` ve yeni `series assemble` aynı bölümlerde çalıştırıldı; videolar kare kare (`ffmpeg -f framemd5`),
  süre ve zaman dosyasıyla birlikte karşılaştırıldı;
- `durum`, `olaylar --durum bekliyor`, `kanon`, `kontrol` ve kart komutları yeni karşılıklarıyla (`status`,
  `ideas --status waiting`, `canon`, `check`, `character`, `location`, `sound`) karşılaştırıldı.
