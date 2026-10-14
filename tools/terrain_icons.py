"""Terrain icons drawn into the font cells of 空 陸 海 宇 水 地 (air, land, sea, space, water,
underground).

The status screens show terrain ranks as these kanji followed by a letter (空A 陸B ...), from
one-character strings in the code (unit types also use 水 water and 地 underground).
English text never uses these kanji, so their glyphs are
repainted as small icons (cloud, mountains, waves, ringed planet); the game tints them as it
did the kanji.

  terrain_icons.py preview OUT.png
repaint(leaf) -> font leaf with the icons (used by build_ogg.py after the Latin repaint)
"""
import math
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from font_latin import CELL_H, CELL_W, GLYPH_BYTES, encode_glyph, glyph_index

S = 8                       # supersampling
W, H = CELL_W * S, CELL_H * S


def _cloud(d):
    # puffs of different heights over a flat base; the dips between them make the outline
    for cx, cy, r in ((4.6, 11.4, 2.5), (8.6, 8.6, 3.5), (12.4, 9.6, 2.9), (15.0, 12.0, 2.0)):
        d.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], fill=255)
    d.rounded_rectangle([2.1 * S, 11.6 * S, 16.9 * S, 14.4 * S], radius=1.4 * S, fill=255)


def _mountains(d):
    d.polygon([(1 * S, 15 * S), (6.5 * S, 5 * S), (12 * S, 15 * S)], fill=255)
    d.polygon([(7 * S, 15 * S), (12 * S, 7.5 * S), (17 * S, 15 * S)], fill=255)
    # snow line notch on the big peak so the two read as separate shapes
    d.line([(6.5 * S, 5 * S), (12 * S, 15 * S)], fill=0, width=int(1.1 * S))
    d.polygon([(1 * S, 15 * S), (6.5 * S, 5 * S), (11.4 * S, 14 * S), (11.4 * S, 15 * S)], fill=255)


def _waves(d):
    for y0 in (7.0, 12.0):
        pts = [((1.5 + t * 15) * S, (y0 + 1.6 * math.sin(t * 2 * math.pi * 1.5)) * S) for t in
               [k / 60 for k in range(61)]]
        d.line(pts, fill=255, width=int(2.2 * S), joint="curve")


def _planet(d):
    cx, cy, r = 9 * S, 9 * S, 4.6 * S
    ring = Image.new("L", (W, H), 0)
    rd = ImageDraw.Draw(ring)
    rd.ellipse([cx - 8.2 * S, cy - 2.6 * S, cx + 8.2 * S, cy + 2.6 * S], outline=255, width=int(1.5 * S))
    ring = ring.rotate(-20, resample=Image.BICUBIC, center=(cx, cy))
    body = Image.new("L", (W, H), 0)
    ImageDraw.Draw(body).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    # the ring passes in front of the planet's lower half: cut a gap above the front arc
    front = ring.copy()
    front.paste(0, (0, 0, W, int(cy)))
    gap = front.point(lambda v: 255 if v else 0).resize((W, H)).filter(__import__("PIL.ImageFilter", fromlist=["x"]).MaxFilter(int(S) | 1))
    body = Image.composite(Image.new("L", (W, H), 0), body, gap)
    out = Image.composite(Image.new("L", (W, H), 255), body, ring)
    d.bitmap((0, 0), out, fill=255)


def _underground(d):
    # a ground slab with an arrow pointing down into it
    d.rectangle([1.5 * S, 11 * S, 16.5 * S, 15.5 * S], fill=255)
    d.line([(1.5 * S, 13.2 * S), (16.5 * S, 13.2 * S)], fill=0, width=int(0.9 * S))
    d.rectangle([7.6 * S, 2 * S, 10.4 * S, 7 * S], fill=255)
    d.polygon([(4.8 * S, 6.6 * S), (13.2 * S, 6.6 * S), (9 * S, 10.6 * S)], fill=255)


ICONS = {"空": _cloud, "陸": _mountains, "海": _waves, "宇": _planet,
         "水": _waves, "地": _underground}   # unit types use 水 (water) and 地 (underground)


def render():
    out = {}
    for ch, fn in ICONS.items():
        im = Image.new("L", (W, H), 0)
        fn(ImageDraw.Draw(im))
        out[ch] = list(im.resize((CELL_W, CELL_H), Image.LANCZOS).getdata())
    return out


def repaint(leaf):
    out = bytearray(leaf)
    for ch, px in render().items():
        i = glyph_index(ch)
        out[i * GLYPH_BYTES:(i + 1) * GLYPH_BYTES] = encode_glyph(px, leaf[i * GLYPH_BYTES:(i + 1) * GLYPH_BYTES])
    return bytes(out)


def main():
    if len(sys.argv) != 3 or sys.argv[1] != "preview":
        sys.exit(__doc__)
    icons = render()
    sheet = Image.new("RGB", (len(icons) * 40 + 8, 48), (20, 24, 40))
    for k, (ch, px) in enumerate(icons.items()):
        g = Image.new("L", (CELL_W, CELL_H))
        g.putdata(px)
        tint = Image.new("RGB", g.size, (40, 220, 230))
        cell = Image.new("RGB", g.size, (20, 24, 40))
        cell.paste(tint, (0, 0), g)
        sheet.paste(cell.resize((36, 36), Image.NEAREST), (8 + k * 40, 6))
    sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST).save(sys.argv[2])


if __name__ == "__main__":
    main()
