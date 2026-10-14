"""Full-screen pictures in GRAPHIC.BIN group 0 (warning screen, backgrounds).

Format (361,472 bytes): 256-colour palette (RGBA, PS2 alpha 0x80 = opaque, CSM1 order) then
704 x 512 8-bit pixels, row-major. Found by dumping EE RAM while the photosensitivity warning
was on screen: entry (0, 152).

  fullscreen_ogg.py dump  OUTDIR          every group-0 picture as PNG
  fullscreen_ogg.py warning OUT.png       render the English warning (preview)

build_ogg.py calls build(src) -> {leaf path: new bytes}.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lice
import p2ig
from tex_text_ogg import font_path

W, H = 704, 512
SIZE = 1024 + W * H


def is_fullscreen(d):
    return len(d) == SIZE and all(d[i * 4 + 3] <= 0x80 for i in range(256))


def palette(d):
    raw = [tuple(d[i * 4:i * 4 + 3]) + (min(255, d[i * 4 + 3] * 2),) for i in range(256)]
    return raw


def to_image(d):
    pal = palette(d)
    im = Image.new("RGBA", (W, H))
    im.putdata([pal[b] for b in d[1024:1024 + W * H]])
    return im


def from_image(d, im):
    """Re-encode into the picture's own palette (nearest colour)."""
    pal = palette(d)
    cache = {}

    def nearest(c):
        if c not in cache:
            cache[c] = min(range(256), key=lambda i: sum((a - b) ** 2 for a, b in zip(pal[i], c)))
        return cache[c]
    px = bytes(nearest(c) for c in im.convert("RGBA").getdata())
    return d[:1024] + px + d[1024 + W * H:]


# The photosensitivity warning shown at boot (entry (0, 152)).
WARNING_KEY = (0, 152)
WARNING_EN = [
    ["When playing this game, keep the room well lit", "and sit as far from the TV screen as you can."],
    ["This game uses flashing images and flash effects."],
    ["In very rare cases, some people may experience", "muscle spasms or a temporary loss of consciousness",
     "when exposed to bright or flashing lights."],
    ["If you have ever had such symptoms,", "consult a doctor before playing this game."],
    ["Before playing, be sure to read", "the instruction manual."],
]


def render_warning(d):
    """White text on black, laid out like the original (paragraph blocks, centred)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    dr = ImageDraw.Draw(im)
    f = ImageFont.truetype(font_path("FiraSans-Medium"), 22)
    line, gap = 29, 21
    total = sum(len(p) for p in WARNING_EN) * line + (len(WARNING_EN) - 1) * gap
    y = (H - total) // 2
    for para in WARNING_EN:
        for text in para:
            w = dr.textlength(text, font=f)
            dr.text(((W - w) / 2, y), text, font=f, fill=(255, 255, 255, 255))
            y += line
        y += gap
    return from_image(d, im)


def build(src):
    root = lice.parse(src)
    out = {}
    for p, n in lice.walk(root):
        if p == WARNING_KEY and n["kind"] == "leaf":
            d = src[n["off"]:n["off"] + n["size"]]
            assert is_fullscreen(d)
            out[p] = render_warning(d)
    return out


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    src = open(os.path.join(os.path.expanduser("~"), "srwogg-work", "ext", "DATA", "GRAPHIC.BIN"), "rb").read()
    root = lice.parse(src)
    leaves = {p: n for p, n in lice.walk(root) if n["kind"] == "leaf"}
    if a[0] == "dump":
        os.makedirs(a[1], exist_ok=True)
        for p, n in leaves.items():
            d = src[n["off"]:n["off"] + n["size"]]
            if p[0] == 0 and is_fullscreen(d):
                to_image(d).save(os.path.join(a[1], "_".join(map(str, p)) + ".png"))
    elif a[0] == "warning":
        n = leaves[WARNING_KEY]
        d = src[n["off"]:n["off"] + n["size"]]
        to_image(render_warning(d)).save(a[1])


if __name__ == "__main__":
    main()
