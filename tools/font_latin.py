"""Repaint the Latin glyphs of the game font from an open-licensed font.

The game font is SHARED.BIN leaf 0000 (and IM.BIN leaf 0000): 4-bit glyphs, 176 bytes each,
9 bytes (18 px) per row, drawn as 18 x 18 sprites; value 15 = clear, 1 = solid ink, values
between are anti-aliasing. Glyph index for a Shift-JIS code c:
    (c - 0x8140) - 64 * (lead - 0x81)
The original Latin sits caps on rows 2-16 with 1 px for descenders; we set caps on rows 2-13
(baseline 14) so g, j, p, q, y get room.

  font_latin.py preview <out.png>                  compare candidate fonts
  font_latin.py apply <font> [cap] [baseline] [weight]   write data/glyph_metrics.json + data/font_latin.json

The build (build_ogg.py) repaints both font leaves from data/font_latin.json.
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FONTS = os.path.join(os.path.expanduser("~"), "srwogg-work", "fonts")
GLYPH_BYTES, ROW_BYTES, CELL_W, CELL_H = 176, 9, 18, 18
BASELINE = 14          # first row below the caps (descenders need rows 14-17 of the 18-row cell)
CAP = 12               # cap height in px
ORIGIN = 1             # pen origin inside the cell (room for small negative side bearings)
TRACKING = 0           # extra px between letters

# characters we draw: the full-width twin of every printable ASCII, plus typographic marks
CHARS = [chr(c) for c in range(0x21, 0x7F) if chr(c) not in "'\""] + ["’", "‘", "“", "”", "―", "…"]  # no ＂＇ in the font
SOURCE = {"―": "—"}    # draw the full-width dash as an em dash
# Letters the font lacks, drawn into symbol cells no game text uses (checked over every script
# and data-table string). ogg_text.to_game maps the letters to these codes.
EXTRA = {"ä": "¢", "ö": "£", "ü": "§", "Ä": "¨", "Ü": "´", "é": "℃"}
CHARS += list(EXTRA)

CANDIDATES = [
    ("NotoSans[wdth,wght].ttf", {"Weight": 500}),
    ("SourceSans3[wght].ttf", {"Weight": 600}),
    ("FiraSans-Medium.ttf", {}),
    ("MPLUS1p-Medium.ttf", {}),
    ("MPLUS1p-Bold.ttf", {}),
]


def font_path_of(name):
    return os.path.join(FONTS, name)


def game_char(ch):
    """The full-width code a character is drawn as."""
    if ch in EXTRA:
        return EXTRA[ch]
    if "!" <= ch <= "~":
        return chr(ord(ch) + 0xFEE0)
    return ch


def glyph_index(gch):
    c = int.from_bytes(gch.encode("cp932"), "big")
    return (c - 0x8140) - 64 * ((c >> 8) - 0x81)


def load_font(name, axes, size):
    f = ImageFont.truetype(os.path.join(FONTS, name), size)
    if axes:
        names = [a["name"].decode() if isinstance(a["name"], bytes) else a["name"] for a in f.get_variation_axes()]
        vals = []
        for a, n in zip(f.get_variation_axes(), names):
            vals.append(axes.get(n, a["default"]))
        f.set_variation_by_axes(vals)
    return f


def fit_size(name, axes, cap=None):
    """Pixel size whose capital H is cap px tall."""
    cap = cap or CAP
    for size in range(10, 30):
        f = load_font(name, axes, size)
        top, bottom = f.getbbox("H")[1], f.getbbox("H")[3]
        if bottom - top >= cap:
            return size
    return 20


def render(name, axes, size=None, cap=None, baseline=None):
    """{char: (alpha 18x18 list, u_start, advance)}: each glyph drawn with its pen origin at
    x=ORIGIN, using the font's own advance width (so spacing follows the font's metrics)."""
    size = size or fit_size(name, axes, cap)
    baseline = baseline or BASELINE
    f = load_font(name, axes, size)
    asc = f.getbbox("H")[3]                  # baseline offset from the draw origin
    out = {}
    for ch in CHARS:
        src = SOURCE.get(ch, ch)
        cell = Image.new("L", (CELL_W, CELL_H), 0)
        ImageDraw.Draw(cell).text((ORIGIN, baseline - asc), src, font=f, fill=255)
        if not cell.getbbox():
            continue
        adv = max(2, round(f.getlength(src)) + TRACKING)
        adv = min(adv, CELL_W - ORIGIN)
        out[ch] = (list(cell.tobytes()), ORIGIN, adv)
    out[" "] = ([0] * (CELL_W * CELL_H), 0, max(3, round(f.getlength(" "))))
    return out, size


def encode_glyph(px, orig):
    """18x18 alpha -> 4-bit glyph bytes (rows 0-17), padding kept from the original."""
    g = bytearray(orig)
    for y in range(CELL_H):
        for xb in range(ROW_BYTES):
            lo = 15 - round(px[y * CELL_W + 2 * xb] * 14 / 255)
            hi = 15 - round(px[y * CELL_W + 2 * xb + 1] * 14 / 255)
            g[y * ROW_BYTES + xb] = lo | (hi << 4)
    return bytes(g)


def repaint(leaf, spec):
    """Apply data/font_latin.json to a font leaf."""
    out = bytearray(leaf)
    for ch, px in spec["glyphs"].items():
        i = glyph_index(game_char(ch))
        out[i * GLYPH_BYTES:(i + 1) * GLYPH_BYTES] = encode_glyph(px, leaf[i * GLYPH_BYTES:(i + 1) * GLYPH_BYTES])
    return bytes(out)


def preview(path):
    sample = ["Albero: ...Wolf 1 to all units. Report your status.",
              "Foglia: Must be nice to cut loose like that! 1234567890",
              "Hugo: Judging by the surface, quite a fight. (\"Head\"?)"]
    rows = []
    for name, axes in CANDIDATES:
        g, size = render(name, axes)
        rows.append((f"{name} {axes or ''} {size}px", g))
    W, H = 560, 26 * 3 + 18
    sheet = Image.new("RGB", (W, H * len(rows)), (20, 70, 45))
    d = ImageDraw.Draw(sheet)
    for r, (label, g) in enumerate(rows):
        d.text((4, r * H + 2), label, fill=(255, 255, 0))
        for k, line in enumerate(sample):
            x, y = 4, r * H + 16 + k * 26
            for ch in line:
                px, u0, adv = g[ch]
                im = Image.frombytes("L", (CELL_W, CELL_H), bytes(px)).crop((u0, 0, u0 + adv, CELL_H))
                sheet.paste((255, 255, 255), (x, y, x + adv, y + CELL_H), im)
                x += adv
    sheet = sheet.resize((W * 2, sheet.height * 2), Image.NEAREST)
    sheet.save(path)
    print("wrote", path)


def apply(name, cap=None, baseline=None, weight=None):
    axes = dict(dict(CANDIDATES).get(name, {}))
    if weight:
        axes["Weight"] = int(weight)
    cap, baseline = int(cap or CAP), int(baseline or BASELINE)
    g, size = render(name, axes, None, cap, baseline)
    metrics = {}
    for ch in g:
        metrics["　" if ch == " " else game_char(ch)] = [g[ch][1], g[ch][2]]
    json.dump(metrics, open(os.path.join(REPO, "data", "glyph_metrics.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    json.dump({"font": name, "axes": axes, "size": size, "baseline": baseline, "cap": cap,
               "glyphs": {ch: g[ch][0] for ch in g if ch != " "}},
              open(os.path.join(REPO, "data", "font_latin.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"{name} {axes} {size}px: {len(g)} glyphs -> data/font_latin.json, data/glyph_metrics.json")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "preview":
        preview(a[1])
    elif a[0] == "apply":
        apply(*a[1:])
