"""Public worksheets carry English only; the Japanese source text comes from your own disc.

  hydrate.py strip  SRC_DIR OUT_DIR     write English-only copies of worksheets/*.json
                                        (drops "jp" and "raw"; used to make the public repo)
  hydrate.py fill   [WORKSHEET_DIR]     put "jp"/"raw" back into English-only worksheets from
                                        the files extracted to ~/srwogg-work/ext (iso_tool.py
                                        extract), so build_ogg.py can run

Entries are matched by the same keys the extractors use: file offset (STR), pool + id (LOGO,
battle), id (FIXH), leaf + slot / leaf + segment (help).
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import battle_ogg
import fixh_ogg
import help_ogg
import lice
import script

EXT = os.path.join(os.path.expanduser("~"), "srwogg-work", "ext")
SECRET = ("jp", "raw")


def load(p):
    return json.load(open(p, encoding="utf-8"))


def save(p, ws):
    json.dump(ws, open(p, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)


def strip(src, out):
    os.makedirs(out, exist_ok=True)
    for p in sorted(glob.glob(os.path.join(src, "*.json"))):
        ws = load(p)
        for e in ws.get("strings", []):
            for k in SECRET:
                e.pop(k, None)
        save(os.path.join(out, os.path.basename(p)), ws)


def leaves_of(container):
    d = open(os.path.join(EXT, *container.split("/")), "rb").read()
    return d, {p: n for p, n in lice.walk(lice.parse(d)) if n["kind"] == "leaf"}


def fill_str(ws):
    fn = ws["file"] if ws["file"].startswith("OL/") else "SLPS_258.36"
    d = open(os.path.join(EXT, *fn.split("/")), "rb").read()
    for e in ws["strings"]:
        raw = d[e["off"]:d.index(b"\0", e["off"])]
        e["raw"] = raw.hex()
        e["jp"] = raw.decode("cp932")


def fill_logo(ws):
    d, leaves = leaves_of("DATA/MAP.BIN")
    n = leaves[tuple(ws["leaf"])]
    data = d[n["off"]:n["off"] + n["size"]]
    script.set_profile(data)
    jp = {(x["pool"], x["id"]): x["jp"] for x in script.logo_extract(data)}
    for e in ws["strings"]:
        e["jp"] = jp[(e.get("pool", "A"), e["id"])]


def fill_fixh(ws, cache={}):
    name, kind = ws["file"].split("/")[-1].replace("FIXH_", "").split(" ")
    if name not in cache:
        d, leaves = leaves_of(f"DATA/{name}.BIN")
        n = leaves[(3, 0)]
        cache[name] = fixh_ogg.extract(d[n["off"]:n["off"] + n["size"]], name)
    src = cache[name][0 if kind == "Strg" else 1]
    jp = {x["id"]: x["jp"] for x in src["strings"]}
    for e in ws["strings"]:
        e["jp"] = jp[e["id"]]


def fill_help(ws):
    name = ws["file"].split("/")[-1].split(" ")[0].replace("HELP_", "")
    d, leaves = leaves_of(f"DATA/{name}.BIN")
    for e in ws["strings"]:
        n = leaves[tuple(e["leaf"])]
        data = d[n["off"]:n["off"] + n["size"]]
        if ws["format"] == "HELP-SLOT":
            e["jp"] = help_ogg.read_slots(data, e["size"])[e["slot"]].decode("cp932")
        else:
            e["jp"] = help_ogg.page_segments(data)[e["seg"]][2]


def fill_battle(ws):
    import mmap
    with open(os.path.join(EXT, "DATA", "BATTLE.BIN"), "rb") as f:
        m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        e5 = lice.parse(m)["entries"][5]
        c5 = bytes(m[e5["off"]:e5["off"] + e5["size"]])
    node = lice.parse(c5)
    cache = {}
    for e in ws["strings"]:
        k = e["file"]
        if k not in cache:
            leaf = node["entries"][k]
            cache[k] = battle_ogg.parse(c5[leaf["off"]:leaf["off"] + leaf["size"]])["strings"]
        e["jp"] = cache[k][e["id"]].decode("cp932")


FILL = {"STRTAB": fill_str, "LOGO": fill_logo, "FIXH-Strg": fill_fixh, "FIXH-Expl": fill_fixh,
        "HELP-SLOT": fill_help, "HELP-PAGE": fill_help, "BATTLE": fill_battle}


def fill(wdir):
    for p in sorted(glob.glob(os.path.join(wdir, "*.json"))):
        ws = load(p)
        if ws.get("strings") and "jp" in ws["strings"][0]:
            continue
        FILL[ws["format"]](ws)
        save(p, ws)
        print("filled", os.path.basename(p))


def main():
    a = sys.argv[1:]
    if a and a[0] == "strip" and len(a) == 3:
        strip(a[1], a[2])
    elif a and a[0] == "fill":
        fill(a[1] if len(a) > 1 else os.path.join(REPO, "worksheets"))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
