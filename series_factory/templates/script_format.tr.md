## script.json (format 3) kuralları
- "format": 3, episode_no, title, genre, source_idea (olay havuzundaki kod, ör. "G-05"), target_sec, hook, caption,
  hashtags, sponsor_slot {scene_no, description}, closing {line, real_footage_note}, canon_updates [..].
- "slug": klasör adı için kısa, Türkçe karaktersiz, alt çizgili (ör. "komsu_ziyareti").
- "summary": 3–5 cümlelik okunabilir özet.
- Mekânlar: serinin sabit mekân kütüphanesi var (kodlar ve tarifleri aşağıda). Bir kare bu mekânlardan birinde geçiyorsa
  refs'e o mekânın kodunu ekle; izleyici her bölümde aynı yerleri görmeli. Yalnızca kütüphanede olmayan bir yer
  gerekiyorsa set_frame {file: "00_<mekan>.jpg", prompt} yaz (karaktersiz, İngilizce, "No people, no animals." ile biter)
  ve o karelerde SET kodunu kullan.
- scenes[]: {no, duration_sec, narration, dialogue[], title_text|null, frames[]}
  * narration: anlatıcının metni. Akıcı okunması için kısa cümleler kullan. Rakam yazma, sayıları yazıyla yaz.
    Duygu etiketleri (ElevenLabs, İngilizce, köşeli parantez, ör. [dramatic], [deadpan]): her sahnenin başına, gerekirse
    ton değişen cümlenin önüne bir etiket koy. Etiketler okunmaz, altyazıya girmez.
    Vurguyu noktalamayla ver: ünlem enerji katar; "..." merak duraklaması (az kullan); noktalı virgül kısa, gerilimli durak.
    start_word ve anchor kelimeleri etiketsiz, noktalaması AYNEN yazılır.
  * frames[]: her sahnede 1–2 kare. {file: "NN_ad.jpg" (sahne no iki hane, ikinci kare 05b gibi),
    motion: in|out|panR|panL|fast|static, refs: [...], prompt: İngilizce sahne tarifi,
    start_word?: (yalnızca 2. ve sonraki karelerde) karenin başladığı, narration'da AYNEN geçen tek kelime,
    video_prompt?: yalnızca aksiyon anı için İngilizce,
    subtitle_pos?: "top" | "middle" — karenin ana öznesi alt yarıdaysa altyazı yukarı alınır; yoksa yazma (bottom),
    animate?: {"preset": "innocent" | "suspicious" | "eye_roll" | "surprised" | "sleepy" | "no" | "yes" | "smug" | "love" |
    "idle"} — karakterin açık gözlerinin net göründüğü, anı yüzün taşıdığı yakın ya da orta bir karede küçük karakter
    efekti (göz kırpma, bakış, kafa eğme); bölüm başına en fazla 1–2 kare; metnin "gözünü kırpmadı" dediği karede asla.
    Göz/kafa noktaları kare gelince otomatik bulunur,
    reads: [kısa] izleyicinin bu karede SIRAYLA anlaması gereken 1–3 şey (bkz. "Zamanlama"),
    hold?: 0.3–1.5 (sn) karenin sözü bitince ekranda sessiz kalma süresi; yalnızca önemli bir an oturmalıysa,
    transition?: bu kareye nasıl girilir; "cut" | "fade" | "fadeblack" | "fadewhite" | "dissolve" | "slideleft" |
    "slideright" | "slideup" | "slidedown" | "smoothleft" | "smoothright" | "wipeleft" | "wiperight" | "circleopen" |
    "circleclose" | "radial" | "hblur" ya da {"type": "...", "duration": 0.2–0.8}. Yazmazsan sahne başında "fade"
    (0,35 sn), sahne içinde "cut".}
  * refs şunlardan seçilir: karakter kodları, mekân kodları (kütüphane), SET (bölüme özel mekân karesi varsa)
    ya da aynı bölümde DAHA ÖNCE gelen bir kare dosyası (süreklilik için). Karede görünen her karakterin sayfası eklenmeli.
  * kare prompt'u yalnızca sahneyi anlatır; stil ve giriş cümlesi otomatik eklenir. Karakterleri adlarıyla an.
    Kamera açısı, kompozisyon, ifade ve kim nerede net olsun.
  * dialogue[]: anlatıcı dışındaki karakterlerin sesli replikleri {character: "<KOD>", text, at}. at:
    {"frame_start": "<kare dosyası>"} ya da {"after_word": "<narration'da AYNEN geçen kelime>"}. Replikler kısa olsun (1–6 kelime).
    Yalnızca seri ayarlarında sesi olan karakterler konuşabilir.

## Zamanlama: okumalar (en sık yapılan hata zamanlama)
İzleyici videoyu bir kez, tam hızda ve ilk kez görür. Sen ne olduğunu biliyorsun, o bilmiyor.
- Her kare için "reads" yaz: izleyicinin bu karede sırayla anlaması gereken şeyler. Okuma ekranda görülen ya da
  duyulan bir şeydir, bilgi değil.
- Bir okumanın bulunup anlaşılması en az ~1,2 sn sürer. Anlatım saniyede ~2 kelime akar; bir karenin süresi
  ≈ kelime/2 + replikler + hold. Okumalar sığmıyorsa kareyi ikiye böl, bir okumayı at ya da "hold" ekle; sıkıştırma.
- Bir anda tek okuma. Neden ve tepki üst üste binmez: önce olan gösterilir, sonra tepki (ayrı kare ya da sırayla).
- Hızlı hareket, yavaş anlam: aksiyon karesi kısa olabilir, ama ardından gelen sonuç ya da tepki zaman ister.
- Gözü yönlendir: önemli bir okumadan önce karakter ona bakıyor, kamera ona gidiyor ya da o şey kadrajın merkezinde.
- "hold"u idareli kullan (bölümde 1–3 kez): doruğun sonucu, en komik tepki ve kapanıştan sonra.
  Son karenin son okuması oturmadan video bitmesin (son karede hold ≥ 0.8).
- Kanca ilk karede ve ilk cümlede; ilk kare siyahtan açılmaz, en güçlü görüntüyle başlar.

## Canlı kal
- Hiçbir kare ölü durmasın: "static" yalnızca 2 sn'den kısa karelerde. Arka arkaya iki kare aynı hareketi almasın.
- Aksiyon anında "fast", sakin anlatımda "in"/"out", mekânı ya da yan yana iki şeyi gösterirken "panR"/"panL".
- Her sahne başı bir geçiştir. Geçişi hikâyeye göre seç: zaman atlaması "fadeblack", hayal ya da anı
  "fadewhite"/"dissolve", yön değiştiren hareket "slideleft"/"slideright", hızlı kaçış "smoothleft".
  Sahne içinde kesme, hareketin ortasında olsun (cut on action).

- sfx[]: {id (snake_case), prompt (İngilizce, ElevenLabs ses efekti), duration (sn, ≤ 5), anchor, offset (sn), volume (0.2–0.8)}.
  anchor: {"scene": no} | {"word": "<narration'da AYNEN geçen kelime>"} | {"line": n (1'den başlayan replik sırası)}.
  Kütüphanede zaten olan efektlerin id'sini kullanırsan yeniden üretilmez (liste aşağıda). 5–9 efekt yeterli.
- music: {id, prompt (İngilizce, enstrümantal döngü), duration: 22, volume: 0.10–0.14, mute?: [{anchor, offset}, {anchor, offset}]}
  (mute: müziğin kısa süre kesildiği dramatik an, iki çapa arası). Kütüphanedeki bir müziği kullanabilirsin.
- scenes[].title_steps?: adım adım değişen ekran yazısı [{text, anchor?, offset?}]; her adım çapasında belirir.
