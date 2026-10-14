"""Battle quotes: BATTLE.BIN entry 5, one file per pilot (341 files).

File layout (little-endian):
  0x00 u16[16] section offsets (0xFFFF = none)
  h[13]..h[14]  u16 offsets[n], relative to the string pool (n quote slots)
  h[14]..h[15]  n x (u16 quote id, u16 1)
  h[15]..end    string pool: NUL-terminated Shift-JIS quotes 「...」 (slots may share a string)
Strings are reached only through the offsets, so the pool is rebuilt at the end of the file
(the u16 offsets allow up to 64 KB).

  battle_ogg.py extract LEAVES_DIR OUT.json   one worksheet for all files (pool = "fNNNN_")
  battle_ogg.py roundtrip LEAVES_DIR

build(data, entries, encode) returns the new file bytes.
"""
import glob
import json
import os
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def parse(d):
    h = struct.unpack_from("<16H", d, 0)
    pool, offsec, idsec = h[15], h[13], h[14]
    n = (idsec - offsec) // 2
    offs = list(struct.unpack_from(f"<{n}H", d, offsec))
    strings, index = [], {}
    for o in offs:
        if o not in index:
            index[o] = len(strings)
            strings.append(d[pool + o:d.index(b"\0", pool + o)])
    slots = [index[o] for o in offs]
    return {"pool": pool, "offsec": offsec, "n": n, "strings": strings, "slots": slots}


def build(d, entries, encode):
    p = parse(d)
    strings = list(p["strings"])
    for e in entries:
        if e.get("en") and not e.get("keep"):
            strings[e["id"]] = encode(e["en"])
    pool, offs = bytearray(), []
    for s in strings:
        offs.append(len(pool))
        pool += s + b"\0"
    if len(pool) > 0xFFFF:
        raise ValueError("pool over 64 KB")
    out = bytearray(d[:p["pool"]])
    struct.pack_into(f"<{p['n']}H", out, p["offsec"], *[offs[i] for i in p["slots"]])
    out += pool
    # keep the original tail alignment (files end on a 4-byte boundary)
    out += b"\0" * (-len(out) % 4)
    return bytes(out)


def extract(leaves_dir):
    ws = {"file": "BATTLE.BIN/5 battle quotes", "format": "BATTLE", "strings": []}
    for path in sorted(glob.glob(os.path.join(leaves_dir, "0005_*.bin"))):
        fno = int(os.path.basename(path)[5:9])
        p = parse(open(path, "rb").read())
        for k, s in enumerate(p["strings"]):
            ws["strings"].append({"pool": f"f{fno:04d}_", "id": k, "file": fno, "jp": s.decode("cp932"),
                                  "en": "", "kind": "battle", "keep": False})
    return ws


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "extract":
        ws = extract(a[1])
        json.dump(ws, open(a[2], "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=0)
        print(a[2], len(ws["strings"]))
    elif a[0] == "roundtrip":
        bad = 0
        for path in sorted(glob.glob(os.path.join(a[1], "0005_*.bin"))):
            d = open(path, "rb").read()
            if build(d, [], None) != d:
                bad += 1
                print("DIFFERENT", os.path.basename(path))
        print("roundtrip:", "all identical" if not bad else f"{bad} different")


if __name__ == "__main__":
    main()
