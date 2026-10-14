"""Repaint picture text in P2IG textures from small JSON specs (textures/*.json).

Spec:
  {"names": ["AT026"],                      texture names this applies to (all copies)
   "items": [{"box": [x0, y0, x1, y1],       region to clear and fill (x1/y1 exclusive)
              "en": "Robot Encyclopedia",
              "font": "FiraSansCondensed-Bold",   file in ~/srwogg-work/fonts (or data/fonts)
              "style": "glow",                    glow | plain | outline | shadow
              "align": "left",                    left | center | right
              "color": [255, 255, 255],
              "italic": false,                    synthetic slant (fonts without an italic cut)
              "track": 0}]}                       extra letter spacing in px

Each item: the box (grown by `pad`, default 2) is cleared to transparent, the English is fitted
(largest size whose height fits, then squeezed horizontally down to 70% if too wide, then
smaller), drawn with its style, and the texture is re-encoded into its own palette.

  tex_text_ogg.py preview SPEC.json SRC.png OUT.png     render over a decoded texture (x3)
  apply(data, spec) -> new P2IG bytes                    used by build_ogg.py
"""
import json
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import p2ig

FONT_DIRS = [os.path.join(REPO, "data", "fonts"), os.path.join(os.path.expanduser("~"), "srwogg-work", "fonts")]


def font_path(name):
    for d in FONT_DIRS:
        for ext in ("", ".ttf", ".otf"):
            p = os.path.join(d, name + ext)
            if os.path.exists(p):
                return p
    raise FileNotFoundError(name)


def text_image(item, size):
    """Render the English as an RGBA image (tight, before squeezing)."""
    f = ImageFont.truetype(font_path(item.get("font", "FiraSansCondensed-Bold")), size)
    track = item.get("track", 0)
    text = item["en"]
    widths = [f.getlength(c) for c in text]
    w = int(sum(widths) + track * max(0, len(text) - 1)) + 8
    asc, desc = f.getmetrics()
    h = asc + desc + 8
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    x = 4
    for c, cw in zip(text, widths):
        d.text((x, 4), c, font=f, fill=255)
        x += cw + track
    if item.get("italic"):
        sh = 0.2
        im = im.transform((w + int(h * sh), h), Image.AFFINE, (1, sh, -h * sh, 0, 1, 0), Image.BICUBIC)
    bbox = im.getbbox() or (0, 0, 1, 1)
    return im.crop(bbox)


def fit(item, bw, bh):
    """Largest rendering that fits bw x bh (ink box), squeezing width down to 70% first.
    item["size"] caps the font size so items in one column match."""
    for size in range(min(item.get("size", 999), max(6, bh * 2)), 5, -1):
        im = text_image(item, size)
        if im.height > bh:
            continue
        if im.width <= bw:
            return im
        if im.width * item.get("squeeze", 0.7) <= bw:
            return im.resize((bw, im.height), Image.LANCZOS)
    return text_image(item, 6)


def styled(mask, item):
    color = tuple(item.get("color", (255, 255, 255)))
    style = item.get("style", "glow")
    m = 4
    big = Image.new("L", (mask.width + 2 * m, mask.height + 2 * m), 0)
    big.paste(mask, (m, m))
    out = Image.new("RGBA", big.size, color + (0,))
    if style == "glow":
        halo = big.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.6)).point(lambda v: int(v * 0.55))
        out.putalpha(Image.eval(Image.merge("L", [halo]), lambda v: v))
        out = Image.alpha_composite(out, Image.merge("RGBA", (*Image.new("RGB", big.size, color).split(), big)))
    elif style == "outline":
        oc = tuple(item.get("outline", (0, 0, 0)))
        ring = big.filter(ImageFilter.MaxFilter(2 * item.get("outline_px", 1) + 1))
        out = Image.merge("RGBA", (*Image.new("RGB", big.size, oc).split(), ring))
        out = Image.alpha_composite(out, Image.merge("RGBA", (*Image.new("RGB", big.size, color).split(), big)))
    elif style == "heavy":
        # thick dark outline plus a drop shadow down-right (map/battle pop-up labels); the fill
        # gets a light top and darker bottom like the originals
        oc = tuple(item.get("outline", (0, 0, 0)))
        ring = big.filter(ImageFilter.MaxFilter(3))
        sh = Image.new("L", big.size, 0)
        sh.paste(ring, (2, 2))
        dark = ImageChops.lighter(ring, sh)
        out = Image.merge("RGBA", (*Image.new("RGB", big.size, oc).split(), dark))
        grad = Image.new("RGB", big.size)
        top = tuple(min(255, int(c + (255 - c) * 0.35)) for c in color)
        bot = tuple(int(c * 0.8) for c in color)
        gd = ImageDraw.Draw(grad)
        y0, y1 = m, big.height - m
        for y in range(big.height):
            t = min(1, max(0, (y - y0) / max(1, y1 - y0)))
            gd.line([(0, y), (big.width, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bot)))
        out = Image.alpha_composite(out, Image.merge("RGBA", (*grad.split(), big)))
    elif style == "shadow":
        sc = tuple(item.get("outline", (0, 0, 0)))
        sh = Image.new("L", big.size, 0)
        sh.paste(big, (1, 1))
        out = Image.merge("RGBA", (*Image.new("RGB", big.size, sc).split(), sh))
        out = Image.alpha_composite(out, Image.merge("RGBA", (*Image.new("RGB", big.size, color).split(), big)))
    else:
        out = Image.merge("RGBA", (*Image.new("RGB", big.size, color).split(), big))
    return out, m


def auto_item(im, item):
    """Resolve "box": "auto" (ink bounding box) and "color": "auto" (median saturated colour)."""
    item = dict(item)
    if item.get("box") == "card":
        # card art: the picture's bounds (non-black), inset
        lit = im.convert("RGB").point(lambda v: 255 if v > 24 else 0).convert("L").point(lambda v: 255 if v else 0)
        x0, y0, x1, y1 = lit.getbbox() or (0, 0, im.width, im.height)
        i = item.get("inset", 10)
        item["box"] = [x0 + i, y0 + i, x1 - i, y1 - i]
    if item.get("box") == "auto":
        bbox = im.split()[-1].point(lambda v: 255 if v > 40 else 0).getbbox()
        item["box"] = list(bbox) if bbox else [0, 0, im.width, im.height]
    if item.get("wide"):
        # one-sprite labels: English may run on to the texture's right edge
        mg = item.get("wide_margin", 1)
        x0 = mg if item["wide"] == "both" else item["box"][0]     # "both": whole texture width
        item["box"] = [x0, item["box"][1], im.width - mg, item["box"][3]]
    if item.get("color") == "auto":
        x0, y0, x1, y1 = item["box"]
        px = [c for c in im.crop((x0, y0, x1, y1)).getdata()
              if c[3] > 200 and max(c[:3]) - min(c[:3]) > 60 and max(c[:3]) > 120]
        if px:
            px.sort(key=lambda c: sum(c[:3]))
            q = 2 if item.get("style") == "heavy" else 3         # heavy adds its own highlight
            item["color"] = list(px[len(px) * q // 4][:3])      # a bright fill tone
        else:
            item["color"] = [255, 255, 255]
    return item


def paint(im, spec):
    im = im.convert("RGBA").copy()
    for item in spec["items"]:
        item = auto_item(im, item)
        x0, y0, x1, y1 = item["box"]
        pad = item.get("pad", 2)
        if item.get("fill") == "inpaint":
            # picture backgrounds (card art): rebuild the box from its surroundings
            import cv2
            import numpy as np
            pad = 0
            a = np.array(im)
            mask = np.zeros(a.shape[:2], np.uint8)
            mask[y0:y1, x0:x1] = 255
            rgb = cv2.inpaint(np.ascontiguousarray(a[:, :, :3]), mask, item.get("inpaint_r", 6), cv2.INPAINT_TELEA)
            a[y0:y1, x0:x1, :3] = rgb[y0:y1, x0:x1]
            im = Image.fromarray(a, "RGBA")
        elif "bg_col" in item:
            # refill each row with the median of its background-coloured pixels (skipping the
            # old glyph's fill, outline and highlights) to keep a gradient inside a frame
            pad = 0
            px = im.load()
            prev = px[item["bg_col"], y0]

            def is_bg(c):
                r, g, b, a = c
                yellow = r > 140 and g > 120 and b < 110
                dark = r + g + b < 70
                light = r + g + b > 600
                return a > 0 and not (yellow or dark or light)
            for y in range(y0, y1):
                row = [px[x, y] for x in range(x0, x1) if is_bg(px[x, y])]
                if row:
                    row.sort(key=lambda c: sum(c[:3]))
                    prev = row[len(row) // 2]
                for x in range(x0, x1):
                    px[x, y] = prev
        else:
            clear = Image.new("RGBA", (x1 - x0 + 2 * pad, y1 - y0 + 2 * pad), (0, 0, 0, 0))
            im.paste(clear, (x0 - pad, y0 - pad))
        if item.get("ring"):
            # emblem cards: repaint the ring (and its face) the kanji overlapped
            r = item["ring"]
            cx, cy = r["center"]
            rx, ry = r["r"]
            dr = ImageDraw.Draw(im)
            dr.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=tuple(r["face"]) + (255,),
                       outline=tuple(r["color"]) + (255,), width=r["w"])
            if r.get("edge"):
                dr.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=tuple(r["edge"]) + (255,), width=2)
        if item.get("text_box"):
            x0, y0, x1, y1 = item["text_box"]
        if not item.get("en"):
            continue
        inset = 2 if item.get("style", "glow") != "plain" else 0
        mask = fit(item, x1 - x0 - 2 * inset, y1 - y0 - 2 * inset)
        layer, m = styled(mask, item)
        bw, bh = x1 - x0, y1 - y0
        align = item.get("align", "left")
        tx = x0 + inset if align == "left" else (x0 + (bw - mask.width) // 2 if align == "center" else x1 - inset - mask.width)
        ty = y0 + (bh - mask.height) // 2
        region = Image.new("RGBA", im.size, (0, 0, 0, 0))
        region.paste(layer, (tx - m, ty - m))
        # stay inside the cleared box so neighbouring sprites are untouched
        clip = Image.new("L", im.size, 0)
        ImageDraw.Draw(clip).rectangle([x0 - pad, y0 - pad, x1 + pad - 1, y1 + pad - 1], fill=255)
        region.putalpha(Image.composite(region.split()[-1], Image.new("L", im.size, 0), clip))
        im = Image.alpha_composite(im, region)
    return im


def apply(data, spec):
    return p2ig.from_image(data, paint(p2ig.to_image(data), spec))


def content_hash(data):
    import hashlib
    return hashlib.sha1(data[0x20:]).hexdigest()[:10]


def load_specs():
    """{name: [spec, ...]}. A spec may list "hashes" (content hashes of the original texture)
    to tell apart different textures that share a name. Label files (textures/labels_*.json)
    hold many one-sprite textures: {"defaults": {...}, "labels": [{"name", "en", "hash"?}]}."""
    specs = {}
    d = os.path.join(REPO, "textures")
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not f.endswith(".json"):
            continue
        s = json.load(open(os.path.join(d, f), encoding="utf-8"))
        if "labels" in s:
            for lab in s["labels"]:
                item = dict({"box": "auto"}, **s.get("defaults", {}), en=lab["en"])
                item.update({k: v for k, v in lab.items() if k not in ("name", "hash")})
                spec = {"names": [lab["name"]], "items": [item]}
                if lab.get("hash"):
                    spec["hashes"] = [lab["hash"]]
                specs.setdefault(lab["name"], []).append(spec)
        else:
            for n in s["names"]:
                specs.setdefault(n, []).append(s)
    return specs


def spec_for(specs, name, data):
    for s in specs.get(name, []):
        if not s.get("hashes") or content_hash(data) in s["hashes"]:
            return s
    return None


def main():
    a = sys.argv[1:]
    if not a or a[0] != "preview":
        sys.exit(__doc__)
    spec = json.load(open(a[1], encoding="utf-8"))
    if "labels" in spec:      # preview the first label only
        lab = spec["labels"][int(a[4]) if len(a) > 4 else 0]
        spec = {"items": [dict({"box": "auto"}, **spec.get("defaults", {}), **{k: v for k, v in lab.items() if k not in ("name", "hash")})]}
    im = paint(Image.open(a[2]), spec)
    bg = Image.new("RGBA", im.size, (40, 60, 90, 255))
    bg.alpha_composite(im)
    bg.resize((im.width * 3, im.height * 3), Image.NEAREST).save(a[3])


if __name__ == "__main__":
    main()
