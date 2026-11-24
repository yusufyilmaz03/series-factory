"""Carousel output: swipeable slides (Instagram / TikTok photo mode) from the plan's "carousel" block.

  series carousel 079 [--json]   ->  <episode>/<carousel>/079_01.jpg ... + _contact.jpg

Plan block (script.json):
  "carousel": {"kicker": "The Guide #1", "title": "WINTER STREET CATS",
    "slides": [{"frame": "01_heater.jpg", "type": "cover", "subtitle": "..."},
               {"frame": "02_box.jpg", "no": 1, "title": "...", "text": "...", "crop": 0.5},
               {"frame": "05_quote.jpg", "type": "quote", "text": "...", "signature": "Narrator"},
               {"frame": "06_sum.jpg", "type": "summary", "title": "SAVE", "bullets": [...], "warning": "...", "footer": "..."}]}
  type: cover | item (default) | quote | summary. crop: vertical position when the frame is cropped (0 top, 0.5 middle, 1 bottom).

Look (series.json "carousel"): width, height, font (path in the series), accent / dark / text colours [r, g, b],
handle (shown bottom-left), signature (default quote signature), quality.
"""
import json, os

from . import core
from .i18n import T

DEFAULT = {"width": 1080, "height": 1350, "font": None, "accent": [236, 176, 72], "dark": [43, 44, 56],
           "text": [255, 255, 255], "handle": "", "signature": "", "quality": 92}


def look():
    c = {**DEFAULT, **core.cfg().get("carousel", {})}
    c["accent"], c["dark"], c["text"] = tuple(c["accent"]), tuple(c["dark"]), tuple(c["text"])
    return c


class Renderer:
    def __init__(self, ep):
        from PIL import Image, ImageDraw, ImageFilter, ImageFont   # optional dependency (Pillow)
        self.Image, self.ImageDraw, self.ImageFilter, self.ImageFont = Image, ImageDraw, ImageFilter, ImageFont
        self.L = look()
        self.W, self.H = self.L["width"], self.L["height"]
        self.ep = ep
        f = self.L["font"]
        self.font_path = core.path(f) if f and not os.path.isabs(f) else f

    def font(self, size, weight):
        F = self.ImageFont
        if not self.font_path or not os.path.exists(self.font_path):
            try:
                return F.truetype("DejaVuSans-Bold.ttf" if weight >= 700 else "DejaVuSans.ttf", size)
            except OSError:
                return F.load_default()
        f = F.truetype(self.font_path, size)
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
        return f

    def wrap(self, d, text, f, width):
        out = []
        for par in text.split("\n"):
            s = ""
            for w in par.split():
                t = (s + " " + w).strip()
                if d.textlength(t, font=f) <= width:
                    s = t
                else:
                    out.append(s)
                    s = w
            out.append(s)
        return out

    def base(self, s):
        im = self.Image.open(core.ep_path(self.ep, "frames", s["frame"])).convert("RGB")
        k = max(self.W / im.width, self.H / im.height)
        im = im.resize((round(im.width * k), round(im.height * k)), self.Image.LANCZOS)
        x = (im.width - self.W) // 2
        y = int((im.height - self.H) * s.get("crop", 0.5))
        return im.crop((x, y, x + self.W, y + self.H)).convert("RGBA")

    def gradient(self, im, top=True, h=560, a=200):
        g = self.Image.new("L", (1, h))
        for i in range(h):
            g.putpixel((0, i), int(a * (1 - i / h) ** 1.4))
        g = g.resize((self.W, h))
        if not top:
            g = g.transpose(self.Image.FLIP_TOP_BOTTOM)
        layer = self.Image.new("RGBA", (self.W, h), (20, 20, 28, 0))
        layer.putalpha(g)
        im.alpha_composite(layer, (0, 0 if top else self.H - h))

    def shadowed(self, d, xy, t, f, colour=None):
        d.text((xy[0] + 2, xy[1] + 3), t, font=f, fill=(0, 0, 0, 150))
        d.text(xy, t, font=f, fill=colour or self.L["text"])

    def pill(self, im, text, f, y, pad=34):
        W = self.W
        d = self.ImageDraw.Draw(im)
        tb = d.textbbox((0, 0), text, font=f)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        box = (W // 2 - tw // 2 - pad, y, W // 2 + tw // 2 + pad, y + th + 2 * pad - 10)
        sh = self.Image.new("RGBA", im.size, (0, 0, 0, 0))
        self.ImageDraw.Draw(sh).rounded_rectangle((box[0] + 6, box[1] + 10, box[2] + 6, box[3] + 10), 40, fill=(0, 0, 0, 110))
        im.alpha_composite(sh.filter(self.ImageFilter.GaussianBlur(10)))
        d = self.ImageDraw.Draw(im)
        d.rounded_rectangle(box, 40, fill=self.L["accent"] + (255,))
        d.text((W // 2 - tw // 2 - tb[0], y + pad - tb[1] - 5), text, font=f, fill=self.L["dark"])

    def counter(self, im, i, n):
        d = self.ImageDraw.Draw(im)
        f = self.font(30, 600)
        self.shadowed(d, (self.W - 60 - d.textlength(f"{i}/{n}", font=f), self.H - 70), f"{i}/{n}", f)
        if self.L["handle"]:
            self.shadowed(d, (60, self.H - 70), self.L["handle"], f)

    def panel(self, im, box, a=175):
        k = self.Image.new("RGBA", im.size, (0, 0, 0, 0))
        self.ImageDraw.Draw(k).rounded_rectangle(box, 34, fill=(22, 22, 30, a))
        im.alpha_composite(k)

    def cover(self, s, c, i, n):
        W, H = self.W, self.H
        im = self.base(s)
        self.gradient(im, True, 520, 170)
        self.gradient(im, False, 520, 210)
        d = self.ImageDraw.Draw(im)
        fu = self.font(52, 700)
        u = c.get("kicker", "")
        self.shadowed(d, (W // 2 - d.textlength(u, font=fu) // 2, 70), u, fu)
        sz = 120
        while d.textlength(c.get("title", ""), font=self.font(sz, 800)) > W - 180 and sz > 40:
            sz -= 6
        self.pill(im, c.get("title", ""), self.font(sz, 800), 150)
        d = self.ImageDraw.Draw(im)
        f = self.font(46, 600)
        lines = self.wrap(d, s.get("subtitle", ""), f, W - 180)
        y = H - 150 - len(lines) * 58
        for t in lines:
            self.shadowed(d, (W // 2 - d.textlength(t, font=f) // 2, y), t, f)
            y += 58
        self.counter(im, i, n)
        return im

    def item(self, s, c, i, n):
        W = self.W
        im = self.base(s)
        d = self.ImageDraw.Draw(im)
        x, y, r = 96, 92, 46
        x2 = x + 2 * r + 26 if "no" in s else x
        fb, fm = self.font(60, 800), self.font(40, 500)
        sb = self.wrap(d, s.get("title", ""), fb, W - x2 - 96)
        sm = self.wrap(d, s.get("text", ""), fm, W - 2 * x)
        yb = y + 4
        ym = max(yb + 68 * len(sb), y + 2 * r) + 16
        self.panel(im, (56, 56, W - 56, ym + 52 * len(sm) + 30))
        d = self.ImageDraw.Draw(im)
        if "no" in s:
            d.ellipse((x, y, x + 2 * r, y + 2 * r), fill=self.L["accent"] + (255,))
            fn = self.font(60, 800)
            t = str(s["no"])
            tb = d.textbbox((0, 0), t, font=fn)
            d.text((x + r - (tb[2] - tb[0]) / 2 - tb[0], y + r - (tb[3] - tb[1]) / 2 - tb[1]), t, font=fn, fill=self.L["dark"])
        for t in sb:
            d.text((x2, yb), t, font=fb, fill=self.L["text"])
            yb += 68
        for t in sm:
            d.text((x, ym), t, font=fm, fill=(235, 235, 240))
            ym += 52
        self.counter(im, i, n)
        return im

    def quote(self, s, c, i, n):
        W = self.W
        im = self.base(s)
        d = self.ImageDraw.Draw(im)
        f, fi = self.font(54, 700), self.font(40, 600)
        lines = self.wrap(d, "“" + s.get("text", "") + "”", f, W - 200)
        y = 100
        self.panel(im, (56, 56, W - 56, y + 66 * len(lines) + 90))
        d = self.ImageDraw.Draw(im)
        for t in lines:
            d.text((W // 2 - d.textlength(t, font=f) // 2, y), t, font=f, fill=self.L["text"])
            y += 66
        sig = s.get("signature") or self.L["signature"]
        if sig:
            t = "— " + sig
            d.text((W // 2 - d.textlength(t, font=fi) // 2, y + 10), t, font=fi, fill=self.L["accent"])
        self.counter(im, i, n)
        return im

    def summary(self, s, c, i, n):
        W = self.W
        im = self.base(s)
        fm, fu = self.font(44, 700), self.font(38, 600)
        bullets = s.get("bullets", [])
        ph = 150 + len(bullets) * 66 + 150
        pan = self.Image.new("RGBA", im.size, (0, 0, 0, 0))
        self.ImageDraw.Draw(pan).rounded_rectangle((60, 60, W - 60, 60 + ph), 36, fill=(24, 24, 32, 200))
        im.alpha_composite(pan)
        d = self.ImageDraw.Draw(im)
        fb = self.font(54, 800)
        t = s.get("title", T("SAVE", "KAYDET"))
        d.text((W // 2 - d.textlength(t, font=fb) // 2, 92), t, font=fb, fill=self.L["accent"])
        y = 180
        for m in bullets:
            d.ellipse((110, y + 18, 126, y + 34), fill=self.L["accent"])
            d.text((146, y), m, font=fm, fill=self.L["text"])
            y += 66
        y += 20
        d.line((110, y, W - 110, y), fill=(255, 255, 255, 90), width=2)
        y += 24
        if s.get("warning"):
            d.text((110, y), s["warning"], font=fu, fill=(255, 210, 140))
            y += 60
        fs = self.font(36, 500)
        for t in self.wrap(d, s.get("footer", ""), fs, W - 220):
            d.text((110, y), t, font=fs, fill=(230, 230, 235))
            y += 46
        self.counter(im, i, n)
        return im


def render(episode):
    ep = core.episode_dir(episode)
    d = core.load_plan(ep)
    c = d.get("carousel")
    if not c or not c.get("slides"):
        raise SystemExit(T(f"{os.path.basename(ep)}: the plan has no carousel block", f"{os.path.basename(ep)}: planda carousel bloğu yok"))
    R = Renderer(ep)
    out = core.ep_path(ep, "carousel")
    os.makedirs(out, exist_ok=True)
    no = core.episode_no(ep)
    fn = {"cover": R.cover, "quote": R.quote, "summary": R.summary}
    slides = c["slides"]
    paths = []
    for i, s in enumerate(slides, 1):
        im = fn.get(s.get("type"), R.item)(s, c, i, len(slides))
        p = os.path.join(out, f"{no}_{i:02d}.jpg")
        im.convert("RGB").save(p, quality=R.L["quality"])
        paths.append(p)
    tw, th = 270, round(270 * R.H / R.W)
    thumbs = [R.Image.open(p).resize((tw, th)) for p in paths]
    cols = min(4, len(paths))
    sheet = R.Image.new("RGB", (tw * cols, th * ((len(paths) + cols - 1) // cols)), "white")
    for j, t in enumerate(thumbs):
        sheet.paste(t, ((j % cols) * tw, (j // cols) * th))
    sheet.save(os.path.join(out, core.layout("contact")), quality=85)
    return [core.rel(p) for p in paths]


def cmd(a):
    paths = render(a.episode)
    core.emit({"slides": paths}, a.json, [T(f"{len(paths)} slides → ", f"{len(paths)} slayt → ") + os.path.dirname(paths[0])])
    return 0


def add_parser(sp):
    p = sp.add_parser("carousel", help=T("render carousel slides from the plan", "plandan karusel slaytlarını üret"))
    p.add_argument("episode"); p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd)
