"""Spirit legend tiles: the 21 one-kanji spirit abbreviations (熱 閃 不 ...) repainted as
two-letter English tiles (VA FL PE ...) in the game font.

The legend row on the spirit screen is drawn by the row routine FUN_0016f620, which takes
each 2-byte unit as one glyph, so the abbreviations must stay single 2-byte characters. The
kanji keep their codes; only their glyphs change. English text never uses these kanji (the
name-entry kanji page is replaced), so nothing else is affected.

  spirit_tiles.py preview OUT.png
repaint(leaf) -> font leaf with the tiles (used by build_ogg.py)
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from font_latin import CELL_H, CELL_W, GLYPH_BYTES, encode_glyph, font_path_of, glyph_index

# spirit (2nd OG name) -> kanji used by the game
TILES = {"熱": "VA", "閃": "FL", "不": "PE", "鉄": "WA", "集": "FO", "必": "BU", "加": "AC",
         "覚": "ZE", "手": "ME", "狙": "SN", "直": "PI", "幸": "LU", "努": "GA", "突": "CH",
         "修": "EA", "予": "CL", "撹": "DI", "魂": "SO", "連": "BL", "同": "SY", "闘": "MT"}
FONT = "FiraSansCondensed-Bold.ttf"
S = 4


def render():
    f = ImageFont.truetype(font_path_of(FONT), 13 * S)
    out = {}
    for ch, txt in TILES.items():
        im = Image.new("L", (CELL_W * S, CELL_H * S), 0)
        d = ImageDraw.Draw(im)
        l, t, r, b = d.textbbox((0, 0), txt, font=f)
        w, h = r - l, b - t
        sx = min(1.0, (CELL_W - 1) * S / w)            # squeeze wide pairs (MW, WA) to the cell
        tile = Image.new("L", (w + 2, h + 2), 0)
        ImageDraw.Draw(tile).text((-l + 1, -t + 1), txt, font=f, fill=255)
        tile = tile.resize((max(1, int(tile.width * sx)), tile.height), Image.LANCZOS)
        im.paste(tile, ((im.width - tile.width) // 2, (im.height - tile.height) // 2 + S))
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
    tiles = render()
    sheet = Image.new("RGB", (len(tiles) * 22 + 4, 26), (20, 24, 40))
    for k, px in enumerate(tiles.values()):
        g = Image.new("L", (CELL_W, CELL_H))
        g.putdata(px)
        sheet.paste((235, 235, 235), (4 + k * 22, 4, 4 + k * 22 + CELL_W, 4 + CELL_H), g)
    sheet.resize((sheet.width * 3, sheet.height * 3), Image.NEAREST).save(sys.argv[2])


if __name__ == "__main__":
    main()
