# Hareketli çizgi roman kurgusu (`series assemble <bölüm> --cut`)

Aynı karelerden daha çok çekim, üretilmiş piksel yok. Montaj hattının tamamı aynen kalır (ses karışımı, replikler,
başlıklar, altyazı yerleri); yalnızca görüntü değişir, altyazıda o an okunan kelime vurgulanır.

```bash
series assemble 004 --cut            # orta (varsayılan) -> cikti/<bölüm>_cut.mp4
series assemble 004 --cut calm       # sakin: daha az çekim
series assemble 004 --cut lively     # hareketli: daha çok çekim
```

## Kurallar

| | sakin | orta | hareketli |
|---|---|---|---|
| en kısa çekim | 3,2 sn | 1,8 sn | 1,2 sn |
| hedef çekim | 4,0 sn | 2,6 sn | 1,8 sn |
| kare başına en fazla çekim | 2 | 3 | 4 |

- Kesmeler yalnızca cümle ya da yan cümle sonunda (kelime zamanları).
- Çekimler sırayla: geniş (özneye doğru yavaş yaklaşma) → öznede yakın → orta. Özne, `subtitles` ekinin nesne
  dedektöründen gelir (önce hayvanlar, sonra insanlar); dedektör yoksa karenin ortası.
- Altyazı yeri her çekim için, ekranda gerçekten görünene göre seçilir (karenin kutuları çekimin kadrajına taşınır,
  yüzler ağırlıklı, `series subtitles` ile aynı kurallar); karede `"cut": {"subtitle_pos": ...}` bunu ezer.
- Hareketler yavaş yaklaşmalar; sarsıntı ve hız çizgisi yok. Küçük kareler ~2 katından fazla büyütülmez.
- Karakter efekti olan kare (`frame.animate`, bkz. [canlandirma.md](canlandirma.md)) bölünmez: kamera en fazla **1,35x**
  yaklaşır, efektin başladığı kadrajda durur ve sabit kalır; efekt son pozunda kalır (geri dönmez), nefes kapalıdır.

## Kare alanları (opsiyonel)

```json
"cut": {"subject": [x, y], "height": 0.5, "close": 1.8, "split": false},
"accent": {"mark": "?", "word": "bakarım."}
```

`subject` dedektörün yerine özneyi verir (karenin pikselleri), `split: false` kareyi tek çekim bırakır, `accent` o kelimede
küçük bir işaret çıkarır.

Seri varsayılanı: `series.json` → `"video": {"cut": "medium"}` ile `assemble`, `produce` ve `batch` kurguyu kullanır ve
normal çıktıyı yazar; `--no-cut` tek seferlik klasik görüntü verir.

Bir kare efekti `"animate": {"preset": "..."}` ile ister (senaryoyla yazılır). Göz/kafa noktaları kare gelince bulunur
(`series animate anchors <bölüm> --write` elle yapar); açık göz bulunamazsa kare normal kurgulanır. Elle girilmiş
noktalar asla ezilmez.

Efekt maskeleri `<kareler>/_animate/` altında önbellektedir (`SERIES_ANIMATE_CACHE` önbelleği başka yere taşır).
