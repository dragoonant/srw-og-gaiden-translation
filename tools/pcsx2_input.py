"""Drive PCSX2 with the keyboard pad profile from pcsx2_pad.py, and take screenshots.

  pcsx2_input.py "O,wait2,DOWN,O" [--shot]

Buttons: O (Circle) X (Cross) Q (Square) T (Triangle) START SELECT L1 R1 UP DOWN LEFT RIGHT
waitN = sleep N seconds; TURBO toggles fast-forward (Tab). --shot presses PCSX2's own F8
screenshot hotkey and prints the new file (never desktop capture: it returns stale frames).
"""
import ctypes
import ctypes.wintypes
import os
import subprocess
import sys
import time

KEYS = {"O": 0x43, "X": 0x58, "Q": 0x5A, "T": 0x53, "START": 0x0D, "SELECT": 0x08, "L1": 0x31,
        "R1": 0x33, "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27, "F8": 0x77, "TURBO": 0x09}
EXTENDED = {0x25, 0x26, 0x27, 0x28}   # arrows must be extended keys or they read as numpad
u32 = ctypes.windll.user32


def _documents():
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)
    return buf.value


SNAPS = os.path.join(_documents(), "PCSX2", "snaps")


def _pids():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq pcsx2-qt.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return {int(l.split('","')[1]) for l in out.splitlines() if l.startswith('"pcsx2')}


def window():
    """PCSX2's main (largest visible) window."""
    pids, found = _pids(), []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        pid = ctypes.c_ulong()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and u32.IsWindowVisible(hwnd) and u32.GetWindowTextLengthW(hwnd) > 0:
            found.append(hwnd)
        return True
    u32.EnumWindows(cb, 0)
    if not found:
        raise RuntimeError("PCSX2 is not running")

    def area(h):
        r = ctypes.wintypes.RECT()
        u32.GetWindowRect(h, ctypes.byref(r))
        return (r.right - r.left) * (r.bottom - r.top)
    return max(found, key=area)


def focus():
    """Kept for callers; input no longer needs focus."""
    window()


def press(vk):
    """Post the key straight to PCSX2's window: no focus needed, and the key can never land in
    another program (synthetic global key events once went to Windows Search while the user
    was at the PC)."""
    hwnd = window()
    ext = 1 if vk in EXTENDED else 0
    sc = u32.MapVirtualKeyW(vk, 0)
    lp = 1 | (sc << 16) | (ext << 24)
    u32.PostMessageW(hwnd, 0x0100, vk, lp)                         # WM_KEYDOWN
    time.sleep(0.12)
    u32.PostMessageW(hwnd, 0x0101, vk, lp | (1 << 30) | (1 << 31))  # WM_KEYUP
    time.sleep(0.3)


def run(seq):
    for k in seq.split(","):
        k = k.strip().upper()
        if not k:
            continue
        if k.startswith("WAIT"):
            time.sleep(float(k[4:]))
        else:
            press(KEYS[k])


def shot():
    before = set(os.listdir(SNAPS))
    press(KEYS["F8"])
    for _ in range(40):
        time.sleep(0.25)
        new = set(os.listdir(SNAPS)) - before
        if new:
            time.sleep(0.4)
            return os.path.join(SNAPS, sorted(new)[-1])
    raise RuntimeError("no screenshot appeared")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "")
    if "--shot" in sys.argv:
        print(shot())
