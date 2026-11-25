# İş kuyruğu (`series jobs`)

Uzun komutlar (efektli montaj, toplu iş, seslendirme), seri klasörünün durduğu bilgisayarı ister: onun Python'u,
araçları ve hızı. Telefondan bir sohbet ya da yalnız klasörü gören bir kum havuzu dosya yazabilir ama uzun bir render'ı
ayakta tutamaz. İş kuyruğu bu ikisini bağlar.

```
series ui                                  # seri bilgisayarında: ekran + iş çalıştırıcı
series jobs add assemble 013               # klasöre yazabilen her yerden
series jobs add batch 013-018 --only assemble
series jobs list                           # durum: queued, running, done, failed, cancelled, interrupted
series jobs log <id> [--tail 80]
series jobs cancel <id>
series jobs worker                         # ekransız çalıştırıcı (oturum açılış öğesi ya da launchd için)
```

- Bir iş `<preview>/jobs/<id>.json` dosyasıdır; çıktısı yanındaki `<id>.log` dosyasına yazılır.
- Çalıştırıcı işleri en eskiden başlayarak teker teker çalıştırır. `batch` kendi içinde paralel çalışır.
- İşler kelime listesi olarak verilen series komutlarıdır, asla kabuk satırı değildir. `ui`, `jobs`, `init` ve
  `migrate` reddedilir.
- Çalıştırıcı kapandığında yarıda kalan iş `interrupted` olarak işaretlenir; yeniden sıraya almak gerekir.
- `series ui` içindeki **İşler** sekmesi komut sıraya alır, kuyruğu son günlük satırlarıyla gösterir ve iş durdurur.
- `series ui --no-jobs` ekranı çalıştırıcısız açar.
- `list`, `log` ve `cancel` seçenekleri işlemden sonra gelebilir. `add` için `--json` önce yazılır:
  `series jobs --json add status`.
