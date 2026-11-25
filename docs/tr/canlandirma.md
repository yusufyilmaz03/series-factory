# Kare canlandırma (`series animate`)

Tek bir durağan karede küçük 2.5D hareketler, **üretken AI olmadan**: nefes, göz kırpma, kısık bakış, göz bebeği,
bakış, kafa eğme / onaylama / sallama, irkilme, zıplama ve kulak seğirmesi. Her piksel karenin kendisinden gelir.

Nasıl çalışır: karakter maskeyle ayrılır (rembg), arkasında kalan arka plan klasik inpaint ile doldurulur
(OpenCV Telea) ve yalnızca karakter katmanı bükülür. Göz kapakları göz çevresindeki tüyden üretilir (inpaint taban renk
+ gözün üstündeki şeridin tüy detayı). Maske ve kapak dokuları `<kareler>/_animate/` altında önbelleğe alınır.

```bash
pip install -e ".[animate]"      # numpy, opencv-python-headless, rembg (maske modeli ilk kullanımda iner)
```

## Bir kare için akış

```bash
series animate grid 004 05_yakin.jpg                  # ızgaralı kare -> koordinatları oku
series animate set 004 05_yakin.jpg --eyes "226,618,75,77;543,613,78,77" \
    --head-pivot 390,1010 --neck 870,1010 --chest 390,1150 --preset innocent
series animate grid 004 05_yakin.jpg                  # kontrol: gözler, pivot, boyun ve kulaklar üstüne çizilir
series animate demo 004 05_yakin.jpg                  # bütün paketler, etiketli, art arda
series animate preview 004 05_yakin.jpg --preset suspicious --seconds 5
```

Kulaklar opsiyonel: `--ears "uçx,uçy,t0x,t0y,t1x,t1y;..."` (kulak ucu ve kulak tabanının iki ucu).

## Plan alanları (karede)

```json
"animate": {
  "anchors": {
    "eyes": [[cx, cy, rx, ry]],
    "head_pivot": [x, y],
    "neck": [y0, y1],
    "chest": [x, y],
    "ears": [{"tip": [x, y], "base": [[x, y], [x, y]]}]
  },
  "preset": "suspicious",
  "events": []
}
```

`events` (opsiyonel) paketin yerine elle yazılmış bir zaman çizelgesi koyar:
`{"type": "blink" | "slow_blink" | "squint" | "pupils" | "look" | "look_path" | "tilt" | "nod" | "shake" | "jolt" |
"bounce" | "ear_flick", "start": sn, "dur": sn, ...}`. `series animate presets --json` bütün paketleri örnek olarak basar.

## Paketler

| Ad | Hareket |
|---|---|
| `idle` (Sakin) | nefes, iki göz kırpma |
| `innocent` (Masum) | göz bebekleri büyür, yavaş kafa eğme, yavaş kırpma |
| `suspicious` (Şüpheli) | tutulan kısık bakış, önce sağa sonra sola bakar |
| `eye_roll` (Göz devirme) | gözler yukarıdan yana devrilir, hafif kısık, kırpma |
| `surprised` (Şaşırmış) | irkilme, göz bebekleri küçülür, zıplama, çift kırpma |
| `sleepy` (Uykulu) | kapaklar düşer, kafa düşer ve toparlanır |
| `no` / `yes` (Hayır / Onay) | kafa sallama / onaylama |
| `smug` (Kibirli) | çene yukarı, düz kısık bakış, yan bakış |
| `love` (Kedi öpücüğü) | kafa eğikken iki yavaş kırpma |
| `ears` (Kulak seğirmesi) | kulak seğirmeleri (kulak noktası gerekir) |

## Sınırlar

- Yakın ve orta plan. Uzak planda gözler kapak için çok küçük; yalnızca nefes ve kafa hareketleri kullanılır.
- Karede tek karakter canlanır. Maskedeki diğer özneler kıpırdamaz: hareket noktaların çevresiyle sınırlı.
- Yürüme ya da büyük uzuv hareketi yok: bunun için rig'li kukla (Live2D / Inochi2D / Spine) ya da 3D gerekir.
