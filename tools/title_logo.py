"""English title logo (Special Disk / title screen, DATA_SP/WINDOW1.BIN).

The Japanese logo is four sprites cut from AT4036 and AT4037 (group 6 textures 17/18), placed
by the screen layouts in group 7. A layout leaf starts with eight texture ids (36 = AT4036,
37 = AT4037 in this group) followed at 0x60 by 72-byte records:
  i32 texture slot, i32 0, f32 u0 v0 u1 v1, f32 x y (sprite centre, origin = screen centre,
  y up), f32 sx sy (scale about the centre), f32 rot, f32 x2 y2, ..., u32 colour
Title layouts (7,0,0) and (7,0,3) draw the logo with records 2-5; (7,0,2) draws both textures
whole, side by side.

The new logo is one 512 x LOGO_H picture: the left half goes in AT4036, the right half in
AT4037 (each with its own 255-colour palette), drawn 1:1 by records 4 and 5. Records 2 and 3
(the old left column) are pointed at a transparent strip.

Source art: ~/srwogg-work/assets/title_logo_src.webp (logo on a sky background; the sky is
keyed out here). Not in the repo: it contains the game's OG emblem.

  title_logo.py preview OUT.png     the logo over a title-screen frame
build(src, root) -> {leaf path: new bytes} (used by build_ogg.py)
"""
import os
import struct
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lice
import p2ig

WORK = os.path.join(os.path.expanduser("~"), "srwogg-work")
SRC = os.path.join(WORK, "assets", "title_logo_src.webp")
TEX = {(6, 0, 17): "left", (6, 0, 18): "right"}
LAYOUTS = [(7, 0, 0), (7, 0, 3)]
LOGO_W, LOGO_H = 512, 222        # texture area used (both halves); content gets a 4 px margin
CENTRE_Y = 77                    # logo centre, y up from screen centre (original logo: ~82)
GLOW = (40, 140, 255)


def key_out(rgb):
    """Alpha mask of the logo: everything not sky, plus the dark-blue rim next to it."""
    a = rgb.astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    blue = (b - r >= 35) & (b >= 170)
    core = (~blue).astype(np.uint8)
    core = cv2.morphologyEx(core, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(core)
    keep = np.zeros_like(core)
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] >= 300:
            keep[lab == i] = 1
    ring = cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
    mask = keep | (ring & ((r < 118) & blue).astype(np.uint8))
    k5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k5), cv2.MORPH_OPEN, k5)
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask)
    mask = (lab == 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats((1 - mask).astype(np.uint8))
    for i in range(1, n):                         # specks inside letters; keep the O/G loops open
        if st[i, cv2.CC_STAT_AREA] < 300:
            mask[lab == i] = 1
    return mask


def logo_image():
    """The finished logo, LOGO_W x LOGO_H RGBA."""
    rgb = np.array(Image.open(SRC).convert("RGB"))
    mask = key_out(rgb)
    x, y, w, h = cv2.boundingRect(mask)
    rgb, mask = rgb[y:y + h, x:x + w], mask[y:y + h, x:x + w]
    alpha = cv2.GaussianBlur(mask.astype(np.float32), (3, 3), 0)
    # scale with premultiplied alpha so the edge does not pick up sky colour
    cw = LOGO_W - 8
    ch = min(LOGO_H - 8, round(h * cw / w))
    cw = round(w * ch / h)
    pre = rgb.astype(np.float32) * alpha[..., None]
    pre = cv2.resize(pre, (cw, ch), interpolation=cv2.INTER_AREA)
    al = cv2.resize(alpha, (cw, ch), interpolation=cv2.INTER_AREA)
    col = pre / np.maximum(al[..., None], 1e-4)
    canvas = np.zeros((LOGO_H, LOGO_W, 4), np.float32)
    ox, oy = (LOGO_W - cw) // 2, (LOGO_H - ch) // 2
    # soft blue glow outside the rim, like the original logo
    hard = np.zeros((LOGO_H, LOGO_W), np.float32)
    hard[oy:oy + ch, ox:ox + cw] = al
    glow = cv2.GaussianBlur(cv2.dilate(hard, np.ones((3, 3), np.uint8)), (0, 0), 2.2) * 0.75
    canvas[..., :3] = GLOW
    canvas[..., 3] = glow
    a = hard[..., None]
    body = np.zeros((LOGO_H, LOGO_W, 3), np.float32)
    body[oy:oy + ch, ox:ox + cw] = col
    out_a = a + canvas[..., 3:] * (1 - a)
    canvas[..., :3] = (body * a + canvas[..., :3] * canvas[..., 3:] * (1 - a)) / np.maximum(out_a, 1e-4)
    canvas[..., 3:] = out_a
    return Image.fromarray(np.clip(np.round(canvas * [1, 1, 1, 255]), 0, 255).astype(np.uint8), "RGBA")


def quantize(im):
    """RGBA -> (palette[256] RGBA, indices). Index 0 is fully transparent."""
    q = im.quantize(colors=255, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    pal = q.getpalette("RGBA")[:255 * 4]
    entries = [(0, 0, 0, 0)] + [tuple(pal[i:i + 4]) for i in range(0, len(pal), 4)]
    entries += [(0, 0, 0, 0)] * (256 - len(entries))
    idx = np.array(q, np.uint8).astype(np.int32) + 1
    idx[np.array(im)[..., 3] < 6] = 0
    return entries, idx.astype(np.uint8)


def encode(orig, im):
    """Replace orig's palette and pixels with im (256x256 RGBA)."""
    h = p2ig.parse(orig)
    assert h["fmt"] == 0x13 and (h["w"], h["h"]) == im.size
    entries, idx = quantize(im)
    sw = p2ig.unswizzle_clut(entries)          # the swap is its own inverse
    pal = b"".join(bytes((r, g, b, (a + 1) // 2)) for r, g, b, a in sw)
    out = bytearray(orig)
    out[h["pal_off"]:h["pal_off"] + 1024] = pal
    out[h["img_off"]:h["img_off"] + 65536] = idx.tobytes()
    return bytes(out)


def halves():
    logo = logo_image()
    left = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    right = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    left.paste(logo.crop((0, 0, 256, LOGO_H)), (0, 0))
    right.paste(logo.crop((256, 0, 512, LOGO_H)), (0, 0))
    # records elsewhere sample AT4036 (0,0)-(4,4) as a blank quad: keep that corner empty
    left.paste((0, 0, 0, 0), (0, 0, 8, 8))
    return {"left": left, "right": right}, logo


def patch_layout(d):
    d = bytearray(d)
    assert struct.unpack_from("<2i", d, 0) == (36, 37)

    def rec(r, slot, uv, xy, s=1.0):
        o = 0x60 + r * 72
        assert struct.unpack_from("<i", d, o)[0] == slot
        struct.pack_into("<4f", d, o + 8, *uv)
        struct.pack_into("<2f", d, o + 24, *xy)
        struct.pack_into("<2f", d, o + 32, s, s)
        struct.pack_into("<2f", d, o + 44, *xy)
    blank = (0.0, 248.0, 4.0, 252.0)              # transparent rows of AT4036
    rec(2, 0, blank, (-245.0, 101.0))
    rec(3, 0, blank, (-253.0, 20.0))
    rec(4, 0, (0.0, 0.0, 256.0, float(LOGO_H)), (-128.0, float(CENTRE_Y)))
    rec(5, 1, (0.0, 0.0, 256.0, float(LOGO_H)), (128.0, float(CENTRE_Y)))
    return bytes(d)


def build(src, root):
    leaves = {p: n for p, n in lice.walk(root) if n["kind"] == "leaf"}
    tex, _ = halves()
    out = {}
    for p, side in TEX.items():
        n = leaves[p]
        d = src[n["off"]:n["off"] + n["size"]]
        assert p2ig.parse(d)["name"] in ("AT4036", "AT4037")
        out[p] = encode(d, tex[side])
    for p in LAYOUTS:
        n = leaves[p]
        out[p] = patch_layout(src[n["off"]:n["off"] + n["size"]])
    return out


def main():
    a = sys.argv[1:]
    if not a or a[0] != "preview":
        sys.exit(__doc__)
    tex, logo = halves()
    # show exactly what the game will draw: the quantized halves, at their screen positions
    src = open(os.path.join(WORK, "ext", "DATA_SP", "WINDOW1.BIN"), "rb").read()
    built = build(src, lice.parse(src))
    shot = Image.new("RGBA", (640, 448), (30, 40, 70, 255))
    bg = os.path.join(WORK, "ref", "title", "bg27.png")
    if os.path.exists(bg):
        shot = Image.open(bg).convert("RGBA").resize((640, 448))
    for p, x in (((6, 0, 17), 320 - 256), ((6, 0, 18), 320)):
        im = p2ig.to_image(built[p]).crop((0, 0, 256, LOGO_H))
        shot.alpha_composite(im, (x, 224 - CENTRE_Y - LOGO_H // 2))
    shot.convert("RGB").save(a[1])


if __name__ == "__main__":
    main()
