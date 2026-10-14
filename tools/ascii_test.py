"""Test build: ASCII body text in every story line, same byte length, MAP.BIN patched in place."""
import sys, os, json, re
sys.path.insert(0, "tools"); import script
W = os.path.expanduser("~/srwogg-work")  
mapbin = bytearray(open(f"{W}/ext/DATA/MAP.BIN", "rb").read())
man = json.load(open(f"{W}/leaves/DATA_MAP/manifest.json"))
FILL = "The quick brown fox jumps over the lazy dog. Pack my box with five dozen liquor jugs! 0123456789 " * 4
n = 0
for m in man:
    if m["path"][0] != 14: continue
    leaf = bytes(mapbin[m["off"]:m["off"] + m["size"]])
    ws = script.extract(os.path.join(W, "leaves/DATA_MAP", m["file"]))
    for e in ws["strings"]:
        mt = re.match(r"^(.+?「)(.*)(」)$", e["jp"], re.S)
        if not mt: continue
        head, body, tail = mt.groups()
        parts = body.split("@　")
        blen = len(body.encode("cp932"))
        if len(parts) > 1:
            l1 = len(parts[0].encode("cp932")); rest = blen - l1 - 3
            new = FILL[:l1] + "@　" + FILL[l1:l1 + rest]
        else:
            new = FILL[:blen]
        assert len(new.encode("cp932")) == blen
        e["en"] = head + new + tail; n += 1
    out = script.build(os.path.join(W, "leaves/DATA_MAP", m["file"]), ws)
    assert len(out) == m["size"], (m["file"], len(out), m["size"])
    mapbin[m["off"]:m["off"] + m["size"]] = out
open(f"{W}/build/MAP.BIN", "wb").write(mapbin)
print("patched lines:", n)
