"""Find sprite boxes in a texture: connected ink regions (alpha > 0) merged when close together,
drawn on an enlarged copy with numbered boxes, and printed as [x0, y0, x1, y1] (x1/y1 exclusive).

  tex_boxes.py PNG OUT.png [gap]
"""
import sys

from PIL import Image, ImageDraw


def boxes(im, gap=3):
    a = im.split()[-1].point(lambda v: 255 if v > 24 else 0)
    w, h = im.size
    px = a.load()
    seen = [[False] * w for _ in range(h)]
    out = []
    for y in range(h):
        for x in range(w):
            if px[x, y] and not seen[y][x]:
                stack = [(x, y)]
                seen[y][x] = True
                x0 = x1 = x
                y0 = y1 = y
                while stack:
                    cx, cy = stack.pop()
                    x0, x1, y0, y1 = min(x0, cx), max(x1, cx), min(y0, cy), max(y1, cy)
                    for nx in range(max(0, cx - gap), min(w, cx + gap + 1)):
                        for ny in range(max(0, cy - 1), min(h, cy + 2)):
                            if px[nx, ny] and not seen[ny][nx]:
                                seen[ny][nx] = True
                                stack.append((nx, ny))
                out.append([x0, y0, x1 + 1, y1 + 1])
    return sorted(out, key=lambda b: (b[1] // 8, b[0]))


def main():
    src, dst = sys.argv[1], sys.argv[2]
    gap = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    im = Image.open(src).convert("RGBA")
    bs = boxes(im, gap)
    s = 3
    big = Image.new("RGBA", (im.width * s, im.height * s), (50, 50, 50, 255))
    big.alpha_composite(im.resize((im.width * s, im.height * s), Image.NEAREST))
    d = ImageDraw.Draw(big)
    for k, (x0, y0, x1, y1) in enumerate(bs):
        d.rectangle([x0 * s, y0 * s, x1 * s - 1, y1 * s - 1], outline=(255, 0, 0, 255))
        d.text((x0 * s + 1, y0 * s + 1), str(k), fill=(255, 255, 0, 255))
    big.save(dst)
    for k, b in enumerate(bs):
        if (b[2] - b[0]) * (b[3] - b[1]) >= 20:
            print(k, b)


if __name__ == "__main__":
    main()
