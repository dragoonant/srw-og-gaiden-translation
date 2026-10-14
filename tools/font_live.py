"""Live font preview over PINE: repaint the Latin glyphs in RAM and reload the width table.

Caveat: the game caches glyphs it has already drawn, so letters already on screen show stale
images cropped with the new widths. Compare fonts with real builds (build_ogg.py --iso).

  font_live.py <font> [cap] [baseline] [weight]

Needs the English build running (vwf_patch applied) and PINE on. Writes a sample into the
dialogue row buffers so the result shows at once.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import font_latin
import ogg_text
import vwf_patch
from pine import Pine

FONT_RAM = 0xA7DF40          # font leaf in RAM during map dialogue (font object +0x24)
ROWS = 0xE29044
SAMPLE = ("Foglia: Must be nice to cut loose like that! Units with Super Robots and new "
          "models have it made. Quite a fight, huh? 1234567890 (Hugo)")

name = sys.argv[1]
cap = int(sys.argv[2]) if len(sys.argv) > 2 else None
base = int(sys.argv[3]) if len(sys.argv) > 3 else None
axes = dict(dict(font_latin.CANDIDATES).get(name, {}))
if len(sys.argv) > 4:
    axes["Weight"] = int(sys.argv[4])
g, size = font_latin.render(name, axes, None, cap, base)
p = Pine()
for ch, (px, u0, adv) in g.items():
    if ch == " ":
        continue
    i = font_latin.glyph_index(font_latin.game_char(ch))
    a = FONT_RAM + i * font_latin.GLYPH_BYTES
    p.write(a, font_latin.encode_glyph(px, p.read(a, font_latin.GLYPH_BYTES)))
tab = bytearray(p.read(vwf_patch.TABLE, 384))
for ch, (px, u0, adv) in g.items():
    gch = "　" if ch == " " else font_latin.game_char(ch)
    code = int.from_bytes(gch.encode("cp932"), "big")
    idx = ((code >> 8) - 0x81) * 0x60 + (code & 0xFF) - 0x40
    tab[2 * idx], tab[2 * idx + 1] = adv, u0
p.write(vwf_patch.TABLE, bytes(tab))
rows = SAMPLE
words, cur, out = rows.split(" "), "", []
space = g[" "][2]
def w(s): return sum(g[c][2] if c in g else 20 for c in s)
for word in words:
    if cur and w(cur) + space + w(word) > ogg_text.ROW_PX:
        out.append(cur); cur = word
    else:
        cur = (cur + " " + word) if cur else word
out.append(cur)
for k in range(3):
    text = out[k] if k < len(out) else ""
    p.write(ROWS + 0x80 * k, (text.encode("ascii") + b"\0").ljust(0x7C, b"\0"))
print(f"{name} {axes} cap={cap} size={size}px rows={len(out)}")
