"""Draw glyphs in the live dialogue buffer (monospace) and screenshot each page.

Needs PCSX2 running at the dialogue box (state with the row buffers at ROWS), PINE on,
the keyboard pad profile, and ScreenshotSize = 2 (internal resolution) for exact pixels.
Writes ~/srwogg-work/glyphs/page_NN.png and pages.json (which code is in which cell).
"""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from pine import Pine

ROWS = 0xE29044          # live row buffers, stride 0x80
PER_ROW = 18             # glyphs per row (fits the box in monospace)
OUT = os.path.join(os.path.expanduser("~"), "srwogg-work", "glyphs")
def _documents():
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)  # CSIDL_PERSONAL
    return buf.value


SNAPS = os.path.join(_documents(), "PCSX2", "snaps")

# Full-width ASCII range plus the punctuation English needs.
CODES = [chr(c + 0xFEE0) for c in range(0x21, 0x7F)] + list("　、。・…―‐’”“‘")


def _pcsx2_window():
    u = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        pid = ctypes.c_ulong()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if u.IsWindowVisible(hwnd) and pid.value in PIDS and u.GetWindowTextLengthW(hwnd) > 0:
            found.append(hwnd)
        return True
    u.EnumWindows(cb, 0)
    return found[0] if found else None


PIDS = set()


def shot():
    """Press PCSX2's screenshot hotkey (F8) and return the new file."""
    if not PIDS:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq pcsx2-qt.exe", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True).stdout
        PIDS.update(int(l.split('","')[1]) for l in out.splitlines() if l.startswith('"pcsx2'))
    u = ctypes.windll.user32
    hwnd = _pcsx2_window()
    if hwnd:
        u.SetForegroundWindow(hwnd)
        time.sleep(0.3)
    before = set(os.listdir(SNAPS))
    u.keybd_event(0x77, 0, 0, 0)
    time.sleep(0.12)
    u.keybd_event(0x77, 0, 2, 0)
    for _ in range(40):
        time.sleep(0.25)
        new = set(os.listdir(SNAPS)) - before
        if new:
            time.sleep(0.4)
            return os.path.join(SNAPS, sorted(new)[-1])
    raise RuntimeError("no screenshot appeared")


def main():
    os.makedirs(OUT, exist_ok=True)
    p = Pine()
    pages = []
    per_page = PER_ROW * 3
    for n in range(0, len(CODES), per_page):
        cells = CODES[n:n + per_page]
        for r in range(3):
            row = "".join(cells[r * PER_ROW:(r + 1) * PER_ROW])
            p.write(ROWS + 0x80 * r, (row.encode("cp932") + b"\0").ljust(0x7C, b"\0"))
        time.sleep(0.3)
        src = shot()
        dst = os.path.join(OUT, f"page_{len(pages):02d}.png")
        shutil.copy(src, dst)
        pages.append({"png": os.path.basename(dst), "cells": cells})
        print(dst, "".join(cells))
    json.dump({"per_row": PER_ROW, "pages": pages}, open(os.path.join(OUT, "pages.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
