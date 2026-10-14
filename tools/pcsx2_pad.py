"""Switch PCSX2's Pad1 between the user's own bindings and a keyboard profile for scripted tests.

  pcsx2_pad.py keyboard   save the current [Pad1] section, write keyboard bindings
  pcsx2_pad.py restore    put the saved [Pad1] section back
  pcsx2_pad.py status

Run only while PCSX2 is closed (it rewrites PCSX2.ini on exit). Always restore before leaving.
"""
import ctypes
import ctypes.wintypes
import os
import re
import sys


def documents():
    buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
    ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)  # CSIDL_PERSONAL
    return buf.value


INI = os.path.join(documents(), "PCSX2", "inis", "PCSX2.ini")
SAVED = INI + ".pad1-user"

KEYBOARD = """[Pad1]
Type = DualShock2
Up = Keyboard/Up
Right = Keyboard/Right
Down = Keyboard/Down
Left = Keyboard/Left
Triangle = Keyboard/S
Circle = Keyboard/C
Cross = Keyboard/X
Square = Keyboard/Z
Select = Keyboard/Backspace
Start = Keyboard/Return
L1 = Keyboard/1
R1 = Keyboard/3

"""


def split(text):
    m = re.search(r"^\[Pad1\]\r?\n.*?(?=^\[|\Z)", text, re.S | re.M)
    if not m:
        sys.exit("no [Pad1] section in " + INI)
    return text[:m.start()], m.group(), text[m.end():]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    text = open(INI, encoding="utf-8").read()
    pre, sec, post = split(text)
    if cmd == "keyboard":
        if not os.path.exists(SAVED):
            open(SAVED, "w", encoding="utf-8", newline="").write(sec)
        open(INI, "w", encoding="utf-8", newline="").write(pre + KEYBOARD + post)
        print("Pad1 = keyboard (user bindings saved)")
    elif cmd == "restore":
        if not os.path.exists(SAVED):
            sys.exit("nothing saved; Pad1 left as is")
        open(INI, "w", encoding="utf-8", newline="").write(pre + open(SAVED, encoding="utf-8").read() + post)
        os.remove(SAVED)
        print("Pad1 restored to the user's bindings")
    else:
        print("keyboard profile active" if os.path.exists(SAVED) else "user bindings active")


if __name__ == "__main__":
    main()
