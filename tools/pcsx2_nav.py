"""Screen-aware navigation for scripted PCSX2 tests: wait until the screen matches a reference
screenshot before pressing anything (key presses sent during loads or movies get lost).

  similar(png_a, png_b)  -> 0..1 (1 = identical), on downscaled greyscale
  wait_for(ref_png, timeout, press=None, every=2.0) -> screenshot path or None
      take screenshots until one matches ref (optionally pressing `press` between tries)
"""
import os
import shutil
import sys
import time

from PIL import Image, ImageChops, ImageStat

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcsx2_input as k

SHOTS = os.path.join(os.path.expanduser("~"), "srwogg-work", "ref", "shots")


def _small(p, box=None):
    im = Image.open(p).convert("L")
    if box:
        im = im.crop(box)
    return im.resize((80, 56))


def similar(a, b, box=None):
    d = ImageChops.difference(_small(a, box), _small(b, box))
    return 1 - ImageStat.Stat(d).mean[0] / 255


def wait_for(ref, timeout=60, press=None, every=2.0, threshold=0.93, box=None, tag="nav"):
    t0 = time.time()
    while time.time() - t0 < timeout:
        p = os.path.join(SHOTS, f"_{tag}.png")
        try:
            shutil.copy(k.shot(), p)
        except RuntimeError:            # no frame yet (boot, mode switch)
            time.sleep(every)
            continue
        if similar(p, ref, box) >= threshold:
            return p
        if press:
            k.run(press)
        time.sleep(every)
    return None
