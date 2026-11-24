// series-factory — Gemini bridge (Apps Script web app on the Google account that owns the exchange folder).
// Deploy: Apps Script > New project > paste > Deploy as web app (execute as me, anyone with the link).
// Put the web app URL and the key into the series .env as GEMINI_BRIDGE_URL / GEMINI_BRIDGE_KEY (never commit them).
// Gemini sayfasından gelen kareyi Drive'da <exchange>/<out_dir>/ klasörüne yazar.
const KLASOR_ID = 'PUT_EXCHANGE_FOLDER_ID_HERE'; // Drive id of paths.exchange
const ANAHTAR = 'PUT_A_LONG_RANDOM_KEY_HERE';

function doPost(e) {
  try {
    const d = JSON.parse(e.postData.contents);
    if (d.k !== ANAHTAR) return ContentService.createTextOutput('yetkisiz');
    const ana = DriveApp.getFolderById(KLASOR_ID);
    const it = ana.getFoldersByName('_out');
    const hedef = it.hasNext() ? it.next() : ana.createFolder('_out');
    const eski = hedef.getFilesByName(d.ad);
    while (eski.hasNext()) eski.next().setTrashed(true); // aynı adlı eski sürüm çöpe (geri alınabilir)
    hedef.createFile(Utilities.newBlob(Utilities.base64Decode(d.b64), d.mime || 'image/png', d.ad));
    return ContentService.createTextOutput('ok');
  } catch (err) {
    return ContentService.createTextOutput('hata: ' + err);
  }
}

// GET ?k=ANAHTAR&ad=<dosya adı>  ->  {"mime":..,"b64":..}  (_gemini klasöründe ve alt klasörlerinde adıyla arar)
function doGet(e) {
  const p = (e && e.parameter) || {};
  if (p.k !== ANAHTAR || !p.ad) return ContentService.createTextOutput('kai-kopru calisiyor');
  const ana = DriveApp.getFolderById(KLASOR_ID);
  const q = 'title = "' + p.ad.replace(/"/g, '\\"') + '" and trashed = false';
  let it = ana.searchFiles(q);
  if (!it.hasNext()) { const alt = ana.getFolders(); while (alt.hasNext() && !it.hasNext()) it = alt.next().searchFiles(q); }
  const out = it.hasNext() ? (b => ({ mime: b.getContentType(), b64: Utilities.base64Encode(b.getBytes()) }))(it.next().getBlob()) : { hata: 'yok: ' + p.ad };
  return ContentService.createTextOutput(JSON.stringify(out)).setMimeType(ContentService.MimeType.JSON);
}
