"""Series status (one table) and the job -> command help list.

  series status [--json]     every episode + ready ideas + publishing + docs sync
  series help                job -> command (at most ~25 lines)
"""
import json

from . import catalog, core, docs, ideas, publish
from .i18n import T


def collect():
    pub = publish.load()
    eps = []
    for b in catalog.episodes():
        if "plan" not in b:
            eps.append({"no": b["folder"][:4], "error": b["error"]})
            continue
        o = catalog.episode_summary(b)
        o["publish"] = publish.cell(pub.get(o["no"]))
        eps.append(o)
    rec = ideas.derived() if _has_ideas() else []
    y, p = publish.counts(pub)
    return {"episodes": eps,
            "ideas": {"waiting": [r["code"] for r in rec if r["status"] == "waiting"],
                      "open_version": [r["code"] for r in rec if r["open_version"]],
                      "counts": {d: sum(r["status"] == d for r in rec) for d in ideas.STATES}},
            "publish": {"published": y, "scheduled": p},
            "docs_to_upload": [x[1] for x in docs.diff()]}


def _has_ideas():
    import os
    p = core.series_path("records", core.layout("records")["idea"])
    return os.path.isdir(p) and bool(os.listdir(p))


def cmd_status(a):
    d = collect()
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
        return 0
    print(T(f"{'no':<5}{'title':<28}{'idea':<10}{'frame':>6}  {'stage':<14}{'s':>5}  {'publish':<15}video",
            f"{'no':<5}{'başlık':<28}{'olay':<10}{'kare':>6}  {'aşama':<14}{'sn':>5}  {'yayın':<15}video"))
    for o in d["episodes"]:
        if "error" in o:
            print(f"{o['no']} {T('ERROR', 'HATA')}: {o['error']}")
            continue
        print(f"{o['no']:<5}{o['title'][:27]:<28}{o['idea'][:9]:<10}{o['frames']:>6}  {catalog.stage_name(o['stage']):<14}"
              f"{o['duration']:>5}  {o['publish']:<15}{o['video']}")
    i = d["ideas"]
    print(T(f"\nready ideas: {len(i['waiting'])} ({', '.join(i['waiting'])})", f"\nhazır olay: {len(i['waiting'])} ({', '.join(i['waiting'])})")
          + (T(f" · with an open version: {', '.join(i['open_version'])}", f" · açık versiyonu olan: {', '.join(i['open_version'])}") if i["open_version"] else ""))
    if any(i["counts"].values()):
        print(T("ideas: ", "olaylar: ") + " · ".join(f"{v} {ideas.state_name(k)}" for k, v in i["counts"].items() if v)
              + T("  (details: series ideas --status ...)", "  (ayrıntı: series ideas --status ...)"))
    print(T(f"publish: {d['publish']['published']} episodes published, {d['publish']['scheduled']} scheduled (details: series publish list)",
            f"yayın: {d['publish']['published']} bölüm yayında, {d['publish']['scheduled']} planlı (ayrıntı: series publish list)"))
    f = d["docs_to_upload"]
    print(T("docs sync:", "doküman senkronu:"), T("same", "aynı") if not f else T("to upload: ", "yüklenecek: ") + ", ".join(f))
    return 0


HELP = {
    "en": """series help — job → command (series <command>; update this list when a command is added)
status [--json]             episodes + ready ideas + publishing + docs sync
ideas --type real --status waiting [--character CAT] [--json]   idea list (status is derived)
idea G-12                   full text + derived status · idea-status G-12 "written (episode 027 'Title')"
idea-add --type K --group g08 --title .. --text .. [--star] (or --file list.json)   new idea (code is automatic)
idea-edit K-43 --old .. --new .. [--group g05]   edit an idea · idea-group list|add|edit
todo list · todo add --section 6 "text" · todo done 012 [--note ..] · todo edit 012 --old .. --new .. · todo clean
canon CAT [--list]          only that character's canon section
context G-12 [--example 021]   script context → plan: script save answer.json
script new|validate|save    write / validate / save an episode plan
check 027                   plan validation + style rules (+ assemble timing)
docs diff|build|mark|edit|insert   generated docs and Claude project sync
frames 013 [--manual|--place|--dry-run]   frames through the image adapter · hf next|batch|wait|download (Higgsfield)
subtitles 013 [--write]     automatic subtitle position (optional extra) · subtitles model
voice episode 013 [--dry-run]   narration + lines + sfx + music (ElevenLabs)
assemble 013                video from frames + audio · strips 013 [--report]   timing report + motion strips
batch 013-018 [--dry-run]   voice + assemble + check for several episodes
produce 013 | produce new | produce status 013   the whole line · contact 013
assets import <file> --folder Cat --name .. --description ..   new photo/video → references + asset map
character CAT · location LIVING · sound door   cards (look before making something new)
library list|generate|approve|guide|place|contact   character sheets and location plates
publish list [001] · publish add 001 --platform instagram --status scheduled --date 2026-11-15
drive prepare 005 008 · drive list · drive clean   Drive staging
migrate [--from ayarlar.json] [--extra x.json] [--dry-run]   convert a legacy series · init <folder>   new series""",
    "tr": """series help — iş → komut (series <komut>; yeni komut eklenince bu liste güncellenir)
status [--json]             bölümler + hazır olaylar + yayın + doküman senkronu
ideas --type gercek --status waiting [--character X] [--json]   olay listesi (durum türetilir)
idea G-12                   tam metin + türetilmiş durum · idea-status G-12 "yazıldı (bölüm 027 'Başlık')"
idea-add --type K --group g08 --title .. --text .. [--star] (ya da --file liste.json)   yeni olay (kod otomatik)
idea-edit K-43 --old .. --new .. [--group g05]   olay metnini düzelt · idea-group list|add|edit
todo list · todo add --section 6 "metin" · todo done 012 [--note ..] · todo edit 012 --old .. --new .. · todo clean
canon X [--list]            kanondan yalnızca o karakter
context G-12 [--example 021]   senaryo bağlamı → plan: script save cevap.json
script new|validate|save    bölüm planı yaz / doğrula / kaydet
check 027                   plan doğrulama + yazım kuralları (+ montaj zamanlaması)
docs diff|build|mark|edit|insert   üretilen dokümanlar ve Claude proje senkronu
frames 013 [--manual|--place|--dry-run]   görsel adaptörüyle kareler · hf next|batch|wait|download (Higgsfield)
subtitles 013 [--write]     otomatik altyazı yeri (opsiyonel) · subtitles model
voice episode 013 [--dry-run]   anlatım + replik + efekt + müzik (ElevenLabs)
assemble 013                kareler + seslerden video · strips 013 [--report]   zamanlama raporu + hareket şeritleri
batch 013-018 [--dry-run]   birden fazla bölüm için ses + montaj + kontrol
produce 013 | produce new | produce status 013   tüm hat · contact 013
assets import <dosya> --folder X --name .. --description ..   yeni foto/video → referanslar + varlık haritası
character X · location SALON · sound kapi   kartlar (yeni bir şey üretmeden önce bak)
library list|generate|approve|guide|place|contact   karakter sayfaları ve mekân planları
publish list [001] · publish add 001 --platform instagram --status scheduled --date 2026-11-15
drive prepare 005 008 · drive list · drive clean   Drive hazırlığı
migrate [--from ayarlar.json] [--extra x.json] [--dry-run]   eski seriyi çevir · init <klasör>   yeni seri""",
}


def cmd_help(a):
    from .i18n import lang
    print(HELP.get(lang(), HELP["en"]))
    return 0


def add_parser(sp):
    p = sp.add_parser("status", help=T("series status table", "seri durum tablosu")); p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)
    p = sp.add_parser("help", help=T("job -> command list", "iş -> komut listesi")); p.set_defaults(func=cmd_help, needs_root=False)
