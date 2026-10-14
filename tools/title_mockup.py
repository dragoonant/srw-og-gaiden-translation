"""Title-logo mockup (preview only, not injected), in the style of the GBA OG / PS2 OGs English logos (not injected).

Layout like OGs: "Super Robot Wars" in tall condensed gold italics, a chrome plate under it with
the subtitle, both inside one silver/blue silhouette, the OG emblem on the right.
Fonts: Saira Extra Condensed Black / Saira Condensed Black (SIL OFL).
"""
import os
import sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

WORK = os.path.join(os.path.expanduser("~"), "srwogg-work")
S = os.path.join(WORK, "ref", "title")     # bg27.png (title movie frame), emblem_clean.png
FONTS = os.path.join(WORK, "fonts")
K = 2
SUB = sys.argv[1] if len(sys.argv) > 1 else "GAIDEN"
TAG = sys.argv[2] if len(sys.argv) > 2 else "C"
W, H = 640 * K, 448 * K

bg = Image.open(f"{S}\\bg27.png").convert("RGBA").resize((W, H), Image.LANCZOS)


def text_mask(text, font, size, slant=0.22, track=0, sx=1.0):
    f = ImageFont.truetype(f"{FONTS}\\{font}", size)
    widths = [f.getlength(c) for c in text]
    w = int(sum(widths) + track * (len(text) - 1)) + 80
    asc, desc = f.getmetrics()
    h = asc + desc + 80
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    x = 40
    for c, cw in zip(text, widths):
        d.text((x, 40), c, font=f, fill=255)
        x += cw + track
    im = im.transform((w + int(h * slant), h), Image.AFFINE, (1, slant, -h * slant, 0, 1, 0), Image.BICUBIC)
    im = im.crop(im.getbbox())
    if sx != 1.0:
        im = im.resize((int(im.width * sx), im.height), Image.LANCZOS)
    return im


def grow(m, r):
    out = m
    while r > 0:
        s = min(r, 3)
        out = out.filter(ImageFilter.MaxFilter(2 * s + 1))
        r -= s
    return out


def vgrad(size, stops, top, bottom):
    w, h = size
    g = Image.new("RGB", size, stops[-1][1])
    d = ImageDraw.Draw(g)
    for y in range(max(0, top), min(h, bottom)):
        t = (y - top) / max(1, bottom - top - 1)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                u = (t - t0) / max(1e-6, t1 - t0)
                d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * u) for a, b in zip(c0, c1)))
                break
    for y in range(0, max(0, top)):
        d.line([(0, y), (w, y)], fill=stops[0][1])
    return g


def layer(color_or_img, mask):
    if isinstance(color_or_img, tuple):
        color_or_img = Image.new("RGB", mask.size, color_or_img)
    return Image.merge("RGBA", (*color_or_img.split(), mask))


def placed(m, x, y):
    c = Image.new("L", (W, H), 0)
    c.paste(m, (int(x), int(y)))
    return c


GOLD = [(0, (255, 246, 150)), (0.30, (255, 206, 40)), (0.46, (255, 252, 225)), (0.54, (246, 160, 10)),
        (0.82, (214, 96, 0)), (1, (255, 186, 60))]
SILVER = [(0, (255, 255, 255)), (0.45, (214, 222, 236)), (0.55, (150, 162, 184)), (1, (236, 240, 248))]

# --- line 1 ----------------------------------------------------------------------------
m1 = text_mask("Super Robot Wars", "SairaExtraCondensed-Black.ttf", 300, slant=0.24, track=-6)
s1 = 352 * K / m1.width
m1 = m1.resize((int(m1.width * s1), int(m1.height * s1 * 1.05)), Image.LANCZOS)
X1, Y1 = 66 * K, 100 * K
M1 = placed(m1, X1, Y1)

# --- line 2 plate + subtitle ------------------------------------------------------------
sub_font = "SairaCondensed-Black.ttf" if len(SUB) > 8 else "SairaSemiCondensed-Black.ttf"
m2 = text_mask(SUB, sub_font, 200, slant=0.22, track=4 if len(SUB) <= 8 else 0)
plate_w = m1.width + 4 * K
plate_h = 40 * K
s2 = min((plate_w - 26 * K) / m2.width, (plate_h - 8 * K) / m2.height)
m2 = m2.resize((int(m2.width * s2), int(m2.height * s2)), Image.LANCZOS)
PX, PY = X1 - 20 * K, Y1 + m1.height - 6 * K
sl = int(plate_h * 0.24)
plate = Image.new("L", (W, H), 0)
ImageDraw.Draw(plate).polygon([(PX + sl, PY), (PX + plate_w + sl, PY), (PX + plate_w, PY + plate_h), (PX, PY + plate_h)], fill=255)
plate = plate.filter(ImageFilter.GaussianBlur(0.6))
M2 = placed(m2, PX + (plate_w + sl - m2.width) / 2, PY + (plate_h - m2.height) / 2)

# --- silhouette: silver body + blue rim + glow around everything -------------------------
body = ImageChops.lighter(grow(M1, 7 * K), grow(plate, 3 * K))
rim = grow(body, 3 * K)
glow = grow(rim, 4 * K).filter(ImageFilter.GaussianBlur(6 * K))

img = bg.copy()
# OG emblem behind the logo plate, like the OGs logo (two-shot matte of the real title screen)
em = Image.open(f"{S}\emblem_clean.png").convert("RGBA")
ES = 1280 / 827 * 1.12
em = em.resize((int(em.width * ES), int(em.height * ES)), Image.LANCZOS)
EX = X1 + m1.width - 36 * K
EY = Y1 - 84 * K
img.alpha_composite(em, (int(EX), int(EY)))
img.alpha_composite(layer((60, 150, 255), glow.point(lambda v: min(255, int(v * 1.3)))))
img.alpha_composite(layer((24, 96, 220), rim))
bb = body.getbbox()
img.alpha_composite(layer(vgrad((W, H), SILVER, bb[1], bb[3]), body))
# thin dark seam between silver body and blue rim
seam = ImageChops.subtract(grow(body, 1 * K), body)
img.alpha_composite(layer((20, 30, 60), seam))

# line 1: black outline, gold fill, gloss streak
img.alpha_composite(layer((10, 6, 4), grow(M1, 3 * K)))
b1 = M1.getbbox()
img.alpha_composite(layer(vgrad((W, H), GOLD, b1[1], b1[3]), M1))
edge = ImageChops.subtract(M1, ImageChops.offset(M1, 0, 2 * K))
img.alpha_composite(layer((255, 255, 235), edge.point(lambda v: int(v * 0.6))))

# plate: dark border, inner silver, subtitle in gold with black outline
img.alpha_composite(layer((12, 10, 10), plate))
inner = plate.filter(ImageFilter.MinFilter(2 * 2 * K + 1))
pb = plate.getbbox()
img.alpha_composite(layer(vgrad((W, H), SILVER, pb[1], pb[3]), inner))
img.alpha_composite(layer((10, 6, 4), grow(M2, 2 * K)))
b2 = M2.getbbox()
img.alpha_composite(layer(vgrad((W, H), GOLD, b2[1], b2[3]), M2))

# --- PRESS ANY BUTTON + copyright from the game's sprites (AT4035) -----------------------
T = os.path.join(WORK, "ref", "tex", "DATA_SP_WINDOW1")
c = Image.open(f"{T}\\0006_0000_0016__AT4035.png").convert("RGBA")
pab = Image.new("RGBA", (251 + 133, 40), (0, 0, 0, 0))
pab.paste(c.crop((2, 2, 253, 40)), (0, 0))
pab.paste(c.crop((3, 45, 136, 83)), (251, 0))
pab = pab.resize((int(pab.width * 0.98 * K), int(pab.height * 0.98 * K)), Image.LANCZOS)
img.alpha_composite(pab, ((W - pab.width) // 2, 318 * K))
for crop, x in (((5, 90, 151, 106), 150), ((5, 110, 154, 126), 335)):
    cr = c.crop(crop)
    img.alpha_composite(cr.resize((cr.width * K, cr.height * K), Image.LANCZOS), (x * K, 420 * K))

img.convert("RGB").save(os.path.join(S, f"mock_{TAG}.png"))
