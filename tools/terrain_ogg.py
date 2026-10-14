"""Terrain names (MAP.BIN leaf (12,0), "MPTI").

MPTI: "MPTI", u32 count, then count x 52-byte entries. Each entry starts with a 32-byte
Shift-JIS name field "<shown name>@<developer note>" (the game shows the part before '@'),
followed by 20 bytes of terrain data. English from glossary/terrain_ogg.tsv replaces the name
field (ASCII, NUL-padded); the data bytes are untouched.

  terrain_ogg.py list            every distinct shown name with its English
patch(map_bytes) -> new MAP.BIN bytes (same size; used by build_ogg.py)
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import lice

LEAF = (12, 0)
ENTRY, NAME = 52, 32
GLOSSARY = os.path.join(REPO, "glossary", "terrain_ogg.tsv")


def names():
    out = {}
    for line in open(GLOSSARY, encoding="utf-8"):
        if "\t" in line:
            jp, en = line.rstrip("\n").split("\t")[:2]
            out[jp] = en
    return out


def entries(d):
    assert d[:4] == b"MPTI"
    for k in range(struct.unpack_from("<I", d, 4)[0]):
        o = 8 + k * ENTRY
        yield o, d[o:o + NAME].split(b"\0")[0].decode("cp932").split("@")[0]


def patch(src):
    root = lice.parse(src)
    n = dict(lice.walk(root))[LEAF]
    d = bytearray(src[n["off"]:n["off"] + n["size"]])
    en = names()
    missing = set()
    for o, jp in entries(bytes(d)):
        if not jp:
            continue
        if jp not in en:
            missing.add(jp)
            continue
        b = en[jp].encode("ascii")
        assert len(b) < NAME, en[jp]
        d[o:o + NAME] = b + b"\0" * (NAME - len(b))
    assert not missing, f"terrain names without English: {sorted(missing)}"
    out = bytearray(src)
    out[n["off"]:n["off"] + n["size"]] = d
    return bytes(out)


def main():
    if sys.argv[1:] != ["list"]:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")
    src = open(os.path.join(os.path.expanduser("~"), "srwogg-work", "ext", "DATA", "MAP.BIN"), "rb").read()
    n = dict(lice.walk(lice.parse(src)))[LEAF]
    en = names()
    for jp in sorted({jp for _, jp in entries(src[n["off"]:n["off"] + n["size"]]) if jp}):
        print(jp, "\t", en.get(jp, "?"))


if __name__ == "__main__":
    main()
