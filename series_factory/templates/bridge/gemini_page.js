// series-factory — Gemini web page helper (paste into the Gemini tab's console or inject with a browser tool).
// Then: __kai.KOPRU = <GEMINI_BRIDGE_URL>; __kai.A = <GEMINI_BRIDGE_KEY>; __kai.JOB = '_job.json' (series.json image.gemini_web.job_name suffix)
// __kai.bolum('067') runs the job list <exchange>/067_job.json; __kai.durum shows progress; __kai.dur = true stops.
// NOTE: the button/menu labels below are those of the Turkish Gemini interface; change them for another UI language.
(function(){
const K = window.__kai = window.__kai || {};
K.S = ms => new Promise(r => setTimeout(r, ms));
K.bekle = async (f, ms = 25000) => { const t = Date.now(); while (Date.now() - t < ms) { const v = f(); if (v) return v; await K.S(250); } return null; };
K.bloblar = K.bloblar || {};
try { performance.setResourceTimingBufferSize(100000); } catch (e) {}
if (!K.hook) { K.hook = true; K.urller = [];
  new PerformanceObserver(l => l.getEntries().forEach(e => { if (/googleusercontent\.com\/gg-dl\//.test(e.name)) K.urller.push([e.startTime, e.name]); })).observe({ type: 'resource', buffered: true }); }
K.refc = K.refc || {};
// Köprü okuması geçici olarak "Failed to fetch" verebilir: 3 kez yeniden dener. Referanslar sayfada önbelleğe alınır (K.ref).
K.oku = async ad => { for (let d = 0; ; d++) { try { const r = await fetch(K.KOPRU + '?k=' + encodeURIComponent(K.A) + '&ad=' + encodeURIComponent(ad)); const j = await r.json();
  if (j.hata) throw j.hata; const b = Uint8Array.from(atob(j.b64), c => c.charCodeAt(0)); return new Blob([b], { type: j.mime }); } catch (e) { if (d >= 3) throw e; await K.S(1500 * (d + 1)); } } };
K.ref = async ad => K.refc[ad] || (K.refc[ad] = await K.oku(ad));
K.yeni = async () => { const c = [...document.querySelectorAll('a,button')].filter(e => /Yeni sohbet/i.test(e.getAttribute('aria-label') || '') || e.innerText?.trim() === 'Yeni sohbet'); const b = c.find(e => e.tagName === 'A' && /\/app$/.test(e.getAttribute('href') || '')) || c.find(e => e.tagName === 'BUTTON') || c[c.length - 1];
  if (!b) throw 'yeni sohbet dugmesi yok'; b.click(); await K.bekle(() => !document.querySelector('model-response'), 8000); await K.S(800); };
K.hazirla = async (oran = '9:16') => { await K.bekle(() => document.querySelector('button[aria-label="Yükleme ve araçlar"]'));
  if (!document.querySelector('button[aria-label="close Resimler"],button[aria-label="Resimler öğesinin seçimini kaldır"]')) { document.querySelector('button[aria-label="Yükleme ve araçlar"]').click();
    const g = await K.bekle(() => [...document.querySelectorAll('[role=menuitemcheckbox]')].find(e => e.innerText.trim() === 'Görüntü oluştur' && e.offsetParent));
    if (!g) throw 'Görüntü oluştur yok'; g.click(); await K.bekle(() => document.querySelector('button[aria-label="close Resimler"],button[aria-label="Resimler öğesinin seçimini kaldır"]')); }
  // Oran düğmesinin aria-label'ı yok (metin 'En-boy oranı') ve hiçbir oran işaretli gelmez: oranı her seferinde seç.
  const sec = () => [...document.querySelectorAll('input-companion-item[role=menuitemradio]')].find(e => e.innerText.trim() === oran && e.offsetParent);
  if (!sec()) { const ob = await K.bekle(() => document.querySelector('button[aria-label^="En-boy oranı"]') || [...document.querySelectorAll('button')].find(b => /^En-boy oranı/.test(b.innerText.trim()) && b.offsetParent));
    if (!ob) throw 'oran dugmesi yok'; ob.click(); }
  const o = await K.bekle(sec); if (!o) throw 'oran yok ' + oran;
  if (o.getAttribute('aria-checked') !== 'true') o.click(); await K.S(500);
  if ([...document.querySelectorAll('input-companion-item[role=menuitemradio]')].some(e => e.offsetParent)) { document.body.click(); await K.S(300); }
  // Dar pencerede oran seçici alttan açılan bir sayfa olur, body tıklamasıyla kapanmaz ve gönder düğmesini örter (20 Kas): Escape + arka plan.
  for (let i = 0; i < 3 && [...document.querySelectorAll('input-companion-item[role=menuitemradio]')].some(e => e.offsetParent); i++) {
    for (const h of [document, document.activeElement]) h?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true })); await K.S(400); }
  const bd = document.querySelector('.cdk-overlay-backdrop'); if (bd && [...document.querySelectorAll('input-companion-item[role=menuitemradio]')].some(e => e.offsetParent)) { bd.click(); await K.S(300); } };
K.gonder = async (refs, prompt) => { const dt = new DataTransfer(); let i = 0;
  for (const r of refs) { i++; let b;
    if (typeof r === 'string') b = await K.ref(r);
    else if (r instanceof Blob) b = r;
    else { b = await K.bekle(() => K.bloblar[r.onceki], 5000); if (!b) throw 'onceki yok ' + r.onceki; }
    dt.items.add(new File([b], String(i).padStart(2, '0') + '.' + (b.type.split('/')[1] || 'jpg'), { type: b.type })); }
  const ed = document.querySelector('rich-textarea .ql-editor'); ed.focus();
  ed.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
  await K.S(1500 + 400 * refs.length); ed.focus(); document.execCommand('insertText', false, prompt); await K.S(400);
  K.t0 = performance.now(); const btn = await K.bekle(() => { const x = document.querySelector('button[aria-label="Mesaj gönder"]'); return x && x.getAttribute('aria-disabled') !== 'true' && x; }, 10000);
  if (!btn) throw 'gonder dugmesi pasif'; btn.click(); };
K.zincir = async u => { for (let i = 0; i < 5; i++) { const r = await fetch(u, { credentials: 'include' }); const ct = r.headers.get('content-type') || ''; if (ct.startsWith('text/plain')) u = (await r.text()).trim(); else return await r.blob(); } };
K.yolla = async (blob, ad) => { const b64 = await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result.split(',')[1]); fr.readAsDataURL(blob); });
  await fetch(K.KOPRU, { method: 'POST', mode: 'no-cors', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify({ k: K.A, ad, mime: blob.type, b64 }) }); };
// Kota dolunca Gemini görsel yerine metinle (İngilizce de olabilir: 'limit resets') cevap verir; 5 dk beklemeden hata ver (20 Kas).
K.sinir = () => { const m = [...document.querySelectorAll('model-response')].pop(); const t = m?.innerText || ''; return /limit resets|limitiniz|sınır|daha sonra tekrar/i.test(t) && t; };
K.al = async (ad, ms = 300000) => { const t0 = K.t0;
  const u = await K.bekle(() => { if (K.sinir()) return 'SINIR'; const x = K.urller.filter(e => e[0] > t0); return x.length && x[x.length - 1][1]; }, ms);
  if (!u || u === 'SINIR') { const m = [...document.querySelectorAll('model-response')].pop(); throw 'gorsel yok: ' + (m?.innerText || '').slice(0, 200); }
  const blob = await K.zincir(u.replace(/=s\d+(-rw)?(?=\?)/, '=s0-rw')); const bm = await createImageBitmap(blob);
  K.bloblar[ad] = blob; await K.yolla(blob, ad + '.' + (blob.type.split('/')[1] || 'png')); return [bm.width, bm.height]; };
K.kare = async is => { await K.yeni(); await K.hazirla(is.oran || '9:16'); await K.gonder(is.refs, is.prompt); return await K.al(is.ad); };
K.bolum = (no, sadece) => { K.dur = false; K.durum = { bolum: no, biten: [], hata: null, sirada: null };
  (async () => { try { const j0 = JSON.parse(await (await K.oku(no + (K.JOB || '_job.json'))).text());
    const is = j0.kareler ? j0 : { kareler: j0.frames.map(f => ({ ad: f.name, oran: f.aspect, prompt: f.prompt, refs: f.refs.map(r => typeof r === 'string' ? r : { onceki: r.previous }) })) };
    for (const k of is.kareler) { if (sadece && !sadece.includes(k.ad)) continue; if (K.dur) { K.durum.hata = 'durduruldu'; break; }
      K.durum.sirada = k.ad; const b = await K.kare(k); K.durum.biten.push([k.ad, b]); }
    K.durum.sirada = null; K.durum.bitti = true; } catch (e) { K.durum.hata = String(e); } })(); return 'basladi'; };
// Bekçi: sekme arka plandayken gönder tıklaması bazen boşa düşer; prompt kutuda kalıp 15 sn geçtiyse yeniden basar (20 Kas).
if (!K.bekci) K.bekci = setInterval(() => { try { const ed = document.querySelector('rich-textarea .ql-editor'); const b = document.querySelector('button[aria-label="Mesaj gönder"]');
  const dur = [...document.querySelectorAll('button')].some(x => x.getAttribute('aria-label') === 'Yanıtı durdur');
  if (ed && ed.innerText.length > 50 && b && b.getAttribute('aria-disabled') !== 'true' && !dur && performance.now() - K.t0 > 15000) { b.click(); K.bekciSay = (K.bekciSay || 0) + 1; } } catch (e) {} }, 5000);
return 'kai yuklendi';
})();
