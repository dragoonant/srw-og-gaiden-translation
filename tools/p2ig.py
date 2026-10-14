"""P2IG images (OG Gaiden's texture format).

Header (little-endian):
  0x00 "P2IG"  ...  0x10 name[8] (e.g. AT004)  0x18 8 bytes (hash/id, kept)
  0x20 u16 log2 width, u16 log2 height   0x24 u32 GS pixel format (0x13 = 8-bit, 0x14 = 4-bit)
  0x40 u32 palette offset, u32 palette size, u32 pixel offset, u32 pixel size
Palettes are RGBA8888 with PS2 alpha (0x80 = opaque); 8-bit palettes use the GS CSM1 block
order (entries 8-15 and 16-23 swapped in every 32). Pixels are stored linear (row-major).

  p2ig.py info FILE...
  p2ig.py topng FILE OUT.png
  p2ig.py dump DIR OUTDIR        every P2IG leaf under DIR to PNG (for browsing)
  p2ig.py frompng ORIG.bin IN.png OUT.bin   re-encode with the original palette (nearest colour)
"""
import os
import struct
import sys

from PIL import Image


def parse(d):
    assert d[:4] == b"P2IG"
    lw, lh = struct.unpack_from("<HH", d, 0x20)
    fmt = struct.unpack_from("<I", d, 0x24)[0]
    po, ps, io, isz = struct.unpack_from("<4I", d, 0x40)
    return {"name": d[0x10:0x18].split(b"\0")[0].decode("ascii", "replace"), "w": 1 << lw, "h": 1 << lh,
            "fmt": fmt, "pal_off": po, "pal_size": ps, "img_off": io, "img_size": isz}


def unswizzle_clut(pal):
    if len(pal) != 256:
        return pal
    out = list(pal)
    for b in range(0, 256, 32):
        out[b + 8:b + 16], out[b + 16:b + 24] = pal[b + 16:b + 24], pal[b + 8:b + 16]
    return out


def palette(d, h):
    raw = d[h["pal_off"]:h["pal_off"] + h["pal_size"]]
    pal = [tuple(raw[i:i + 4]) for i in range(0, len(raw), 4)]
    pal = unswizzle_clut(pal)
    return [(r, g, b, min(255, a * 2)) for r, g, b, a in pal]


def indices(d, h):
    raw = d[h["img_off"]:h["img_off"] + h["img_size"]]
    if h["fmt"] == 0x14:
        out = bytearray(len(raw) * 2)
        out[0::2] = bytes(b & 15 for b in raw)
        out[1::2] = bytes(b >> 4 for b in raw)
        return bytes(out)
    return bytes(raw)


def to_image(d):
    h = parse(d)
    pal = palette(d, h)
    idx = indices(d, h)
    im = Image.new("RGBA", (h["w"], h["h"]))
    im.putdata([pal[i] if i < len(pal) else (0, 0, 0, 0) for i in idx[:h["w"] * h["h"]]])
    return im


def from_image(orig, im):
    """Re-encode im (RGBA, same size) into orig's palette by nearest colour."""
    h = parse(orig)
    pal = palette(orig, h)
    im = im.convert("RGBA")
    assert im.size == (h["w"], h["h"]), (im.size, h["w"], h["h"])
    cache = {}

    def nearest(px):
        if px not in cache:
            cache[px] = min(range(len(pal)), key=lambda i: sum((a - b) ** 2 for a, b in zip(pal[i], px)))
        return cache[px]
    idx = [nearest(px) for px in im.getdata()]
    out = bytearray(orig)
    if h["fmt"] == 0x14:
        packed = bytes((idx[i] & 15) | ((idx[i + 1] & 15) << 4) for i in range(0, len(idx), 2))
    else:
        packed = bytes(idx)
    out[h["img_off"]:h["img_off"] + len(packed)] = packed
    return bytes(out)


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "info":
        for f in a[1:]:
            print(f, parse(open(f, "rb").read()))
    elif a[0] == "topng":
        to_image(open(a[1], "rb").read()).save(a[2])
    elif a[0] == "dump":
        os.makedirs(a[2], exist_ok=True)
        n = 0
        for root, _, files in os.walk(a[1]):
            for f in files:
                p = os.path.join(root, f)
                d = open(p, "rb").read()
                if d[:4] != b"P2IG":
                    continue
                rel = os.path.relpath(p, a[1]).replace(os.sep, "__")[:-4]
                try:
                    to_image(d).save(os.path.join(a[2], f"{rel}__{parse(d)['name']}.png"))
                    n += 1
                except Exception as ex:      # noqa: BLE001
                    print("skip", p, ex)
        print(n, "images")
    elif a[0] == "frompng":
        open(a[3], "wb").write(from_image(open(a[1], "rb").read(), Image.open(a[2])))


if __name__ == "__main__":
    main()
