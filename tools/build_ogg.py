"""Build the English OG Gaiden image from the pristine extract and the worksheets.

  build_ogg.py [--iso OUT.iso] [--only map,elf,font]

Steps:
  1. MAP.BIN: every worksheets/MAP_14_*.json (LOGO stage scripts) is applied to its leaf;
     English is word-wrapped to the dialogue row width and stored as 1-byte ASCII
     (ogg_text). MAP.BIN is repacked (lice.build) and keeps its size while it fits.
  2. SLPS_258.36: the proportional-width patch (vwf_patch).
  2b. SHARED.BIN / IM.BIN: the font leaf with repainted Latin glyphs (font_latin).
  3. ISO: a copy of the pristine image with both files written in place (iso_tool).

Gates: a dialogue line may not exceed MAX_ROWS rows or MAX_ROW_BYTES bytes per row.
Failures abort the build.
"""
import glob
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import iso_tool
import lice
import fixh_ogg
import font_latin
import battle_ogg
import help_ogg
import ogg_text
import script
import p2ig
import strtab_ogg
import tex_text_ogg
import fullscreen_ogg
import title_logo
import terrain_ogg
import terrain_icons
import spirit_tiles
import vwf_patch

WORK = os.path.join(os.path.expanduser("~"), "srwogg-work")
REPO = os.path.dirname(HERE)
MAX_ROWS = 3
MAX_ROW_BYTES = 60    # the backlog copies at most 64 bytes per row


def find_pristine_iso():
    for p in glob.glob(os.path.join(REPO, "*", "*.iso")) + glob.glob(os.path.join(WORK, "pristine", "*.iso")):
        if os.path.getsize(p) == 4666294272:
            return p
    sys.exit("pristine ISO not found")


def build_map():
    src = open(os.path.join(WORK, "ext", "DATA", "MAP.BIN"), "rb").read()
    root = lice.parse(src)
    leaves = {p: n for p, n in lice.walk(root) if n["kind"] == "leaf"}
    repl, errors, count = {}, [], 0
    for wsp in sorted(glob.glob(os.path.join(REPO, "worksheets", "MAP_14_*.json"))):
        ws = json.load(open(wsp, encoding="utf-8"))
        path = tuple(ws["leaf"])
        n = leaves[path]
        orig = src[n["off"]:n["off"] + n["size"]]
        entries = []
        for e in ws["strings"]:
            e = dict(e)
            if e.get("en"):
                game = ogg_text.wrap(e["en"], keep_q="?" in e["jp"])
                rows = ogg_text.row_widths(game)
                if len(rows) > MAX_ROWS:
                    errors.append(f"{os.path.basename(wsp)} {e['pool']}{e['id']}: {len(rows)} rows")
                for r in game.split("@"):
                    if len(r.encode("cp932")) > MAX_ROW_BYTES:
                        errors.append(f"{os.path.basename(wsp)} {e['pool']}{e['id']}: row of {len(r.encode('cp932'))} bytes")
                e["en"] = game
                count += 1
            entries.append(e)
        script.detect(orig)
        repl[path] = script.logo_build(orig, entries)
    if errors:
        sys.exit("build gate failed:\n  " + "\n  ".join(errors))
    out = lice.build(src, root, repl)
    if len(out) != len(src):
        sys.exit(f"MAP.BIN grew past its slack: {len(out)} > {len(src)}")
    print(f"MAP.BIN: {count} English strings in {len(repl)} scripts")
    return out


JP_ADV = 20      # advance of a Japanese glyph: description lines keep the Japanese width


def build_shared(container, parts=("font", "tables")):
    """SHARED.BIN / IM.BIN: font leaf (0,0) with repainted Latin glyphs, and the data tables
    leaf (3,0) rebuilt from worksheets FIXH_<NAME>_Strg/_Expl."""
    src = open(os.path.join(WORK, "ext", "DATA", container), "rb").read()
    root = lice.parse(src)
    leaves = dict(lice.walk(root))
    repl, notes = {}, []
    spec_path = os.path.join(REPO, "data", "font_latin.json")
    if "font" in parts and os.path.exists(spec_path):
        spec = json.load(open(spec_path, encoding="utf-8"))
        leaf = leaves[(0, 0)]
        assert leaf["kind"] == "leaf" and leaf["size"] == 0xC0800, leaf
        repl[(0, 0)] = spirit_tiles.repaint(terrain_icons.repaint(font_latin.repaint(src[leaf["off"]:leaf["off"] + leaf["size"]], spec)))
        notes.append(f"Latin glyphs ({spec['font']}) + terrain icons + spirit tiles")
    name = container.split(".")[0]
    sp = os.path.join(REPO, "worksheets", f"FIXH_{name}_Strg.json")
    ep = os.path.join(REPO, "worksheets", f"FIXH_{name}_Expl.json")
    if "tables" in parts and os.path.exists(sp):
        leaf = leaves[(3, 0)]
        orig = src[leaf["off"]:leaf["off"] + leaf["size"]]
        strg = json.load(open(sp, encoding="utf-8"))
        expl = json.load(open(ep, encoding="utf-8")) if os.path.exists(ep) else None
        n_names = 0
        for e in strg["strings"]:
            if e.get("en") and not e.get("keep"):
                e["en_game"] = ogg_text.to_game(e["en"])
                n_names += 1
        widths = {}
        if expl:
            for e in expl["strings"]:
                # 0.9 x the Japanese width: safe inside the window, and (with tail merging) keeps
                # SHARED.BIN within its original size
                widths[e["id"]] = int(0.9 * max([len(l) * JP_ADV for l in e["jp"].split("\n")] + [200]))
        n_desc = 0
        if expl:
            # each description is wrapped to its own Japanese width, one string per line
            for e in expl["strings"]:
                if e.get("en") and not e.get("keep"):
                    e["en"] = "\n".join(ogg_text.wrap_rows(e["en"], widths[e["id"]], end_pair=False))
                    n_desc += 1
        repl[(3, 0)] = fixh_ogg.build(orig, strg, expl)
        notes.append(f"{n_names} names, {n_desc} descriptions")
    hs = os.path.join(REPO, "worksheets", f"HELP_{name}_slots.json")
    hp = os.path.join(REPO, "worksheets", f"HELP_{name}_pages.json")
    if "tables" in parts and os.path.exists(hs):
        n_help = 0
        by_leaf = {}
        for e in json.load(open(hs, encoding="utf-8"))["strings"]:
            by_leaf.setdefault(tuple(e["leaf"]), []).append(e)
        for lf, ents in by_leaf.items():
            leaf = leaves[lf]
            data = src[leaf["off"]:leaf["off"] + leaf["size"]]
            todo = [dict(e, id=e["slot"]) for e in ents if e.get("en") and not e.get("keep")]
            if todo:
                repl[lf] = help_ogg.build_slot(data, ents[0]["size"], todo, encode_ui)
                n_help += len(todo)
        by_page = {}
        if os.path.exists(hp):
            for e in json.load(open(hp, encoding="utf-8"))["strings"]:
                by_page.setdefault(tuple(e["leaf"]), []).append(e)
        for lf, ents in by_page.items():
            todo = [dict(e, id=e["seg"]) for e in ents if e.get("en") and not e.get("keep")]
            if todo:
                leaf = leaves[lf]
                repl[lf] = help_ogg.build_page(src[leaf["off"]:leaf["off"] + leaf["size"]], todo, encode_ui)
                n_help += len(todo)
        notes.append(f"{n_help} help texts")
    if not repl:
        return None
    out = lice.build(src, root, repl)
    if len(out) > len(src):
        # the game loads these whole into a buffer of the original size: growing them crashed
        # the game at boot (TLB miss at 0x12B23C)
        sys.exit(f"{container}: grew from {len(src)} to {len(out)} bytes; it must not grow")
    print(f"{container}: " + "; ".join(notes))
    return out


def encode_ui(en, budget=None):
    b = ogg_text.to_game(en).encode("cp932")
    if budget is not None and len(b) > budget:
        b = ogg_text.to_game(en, end_pair=False).encode("cp932")   # full slot: skip the pad byte
    return b


def apply_strings(name, data):
    """In-place executable strings from worksheets/STR_<name>.json. Over-budget entries abort."""
    p = os.path.join(REPO, "worksheets", f"STR_{name}.json")
    skip = os.environ.get("NO_STR", "").split(",")      # debug: NO_STR=W2OL,SLPS_258
    if not os.path.exists(p) or name in skip or "all" in skip:
        return data, 0
    ws = json.load(open(p, encoding="utf-8"))
    rng = os.environ.get("STR_RANGE", "")                # debug: STR_RANGE=EXOL:0-188
    if rng.startswith(name + ":"):
        lo, hi = map(int, rng.split(":")[1].split("-"))
        ws["strings"] = [e for e in ws["strings"] if lo <= e["id"] <= hi]
    out, over = strtab_ogg.build(data, ws, encode_ui)
    if over:
        sys.exit(f"{name}: strings over their in-place budget: {over[:5]}")
    return out, sum(1 for e in ws["strings"] if e.get("en") and not e.get("keep"))


def build_overlays():
    files = {}
    for path in sorted(glob.glob(os.path.join(WORK, "ext", "OL", "*.BIN"))):
        name = os.path.basename(path)[:-4]
        data = open(path, "rb").read()
        new, n = apply_strings(name, data)
        new = vwf_patch.patch_overlay(name, new)        # code tweaks (spirit list alignment)
        if n or new != data:
            files["OL/" + os.path.basename(path)] = new
            print(f"OL/{name}.BIN: {n} strings")
    return files


def build_elf():
    src = open(os.path.join(WORK, "ext", "SLPS_258.36"), "rb").read()
    strings, n = apply_strings("SLPS_258", src)
    # no string slot may overlap the code caves
    ws_p = os.path.join(REPO, "worksheets", "STR_SLPS_258.json")
    if os.path.exists(ws_p):
        caves = [(vwf_patch.CAVE, vwf_patch.CAVE + vwf_patch.CAVE_LEN),
                 (vwf_patch.CAVE_B, vwf_patch.CAVE_B + vwf_patch.CAVE_B_LEN)]
        for e in json.load(open(ws_p, encoding="utf-8"))["strings"]:
            va = int(e["va"], 16)
            assert not any(lo < va + e["budget"] + 1 and va < hi for lo, hi in caves), e["va"]
    d = bytearray(strings)
    vwf_patch._load_orig_head()

    def rd(addr, k):
        o = addr - vwf_patch.ELF_BASE + vwf_patch.ELF_OFF
        return bytes(d[o:o + k])

    def wr(addr, b):
        o = addr - vwf_patch.ELF_BASE + vwf_patch.ELF_OFF
        d[o:o + len(b)] = b
    vwf_patch.patch_bytes(rd, wr)
    print(f"SLPS_258.36: proportional text patch, {n} strings")
    return bytes(d)


TEXTURE_CONTAINERS = ["DATA/WINDOW.BIN", "DATA/GRAPHIC.BIN", "DATA/MAP.BIN", "DATA_SP/WINDOW1.BIN",
                      "DATA_SP/GRAPHIC2.BIN", "DATA_SP/MAPSB.BIN", "DATA_SP/SBBATTLE.BIN"]


def build_textures(built=None):
    """Repaint picture text (textures/*.json) in every P2IG leaf with a matching name."""
    specs = tex_text_ogg.load_specs()
    files = {}
    if not specs:
        return files
    for c in TEXTURE_CONTAINERS:
        # start from this build's version of the file if an earlier step changed it (MAP.BIN
        # carries the story text; re-reading the pristine copy here once dropped it)
        src = (built or {}).get(c) or open(os.path.join(WORK, "ext", *c.split("/")), "rb").read()
        root = lice.parse(src)
        repl, names = {}, set()
        for p, n in lice.walk(root):
            if n["kind"] != "leaf" or src[n["off"]:n["off"] + 4] != b"P2IG":
                continue
            d = src[n["off"]:n["off"] + n["size"]]
            name = p2ig.parse(d)["name"]
            spec = tex_text_ogg.spec_for(specs, name, d)
            if spec:
                repl[p] = tex_text_ogg.apply(d, spec)
                names.add(name)
        if c == "DATA_SP/WINDOW1.BIN" and os.path.exists(title_logo.SRC):
            logo = title_logo.build(src, root)      # English title logo + its layout records
            repl.update(logo)
            names.add("title logo")
        if c == "DATA/GRAPHIC.BIN":
            full = fullscreen_ogg.build(src)       # full-screen pictures (warning screen)
            repl.update(full)
            names.update("fullscreen " + "_".join(map(str, p)) for p in full)
        if repl:
            out = lice.build(src, root, repl)
            assert len(out) == len(src), c
            files[c] = out
            print(f"{c}: picture text in {len(repl)} textures ({', '.join(sorted(names))})")
    return files


def build_battle(out_iso):
    """BATTLE.BIN entry 5 (battle quotes) rebuilt from worksheets/BATTLE_quotes.json and
    streamed into the image in place (the 1.8 GB file keeps its size and position)."""
    import mmap
    wp = os.path.join(REPO, "worksheets", "BATTLE_quotes.json")
    if not os.path.exists(wp):
        return
    by_file = {}
    for e in json.load(open(wp, encoding="utf-8"))["strings"]:
        if e.get("en") and not e.get("keep"):
            by_file.setdefault(e["file"], []).append(e)
    if not by_file:
        return
    src_p = os.path.join(WORK, "ext", "DATA", "BATTLE.BIN")
    with open(src_p, "rb") as f:
        m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        root = lice.parse(m)
        e5 = root["entries"][5]
        c5 = bytes(m[e5["off"]:e5["off"] + e5["size"]])
        node = lice.parse(c5)
        repl = {}
        for k, leaf in enumerate(node["entries"]):
            if k in by_file:
                d = c5[leaf["off"]:leaf["off"] + leaf["size"]]
                repl[(k,)] = battle_ogg.build(d, by_file[k], encode_ui)
        new5 = lice.build(c5, node, repl)
        entry = next(x for x in iso_tool.entries(out_iso) if x["path"] == "/DATA/BATTLE.BIN")
        with open(out_iso, "r+b") as out:
            lice.write_top_level(m, {5: new5}, out, entry["lba"] * iso_tool.SECTOR)
    print(f"DATA/BATTLE.BIN: {sum(len(v) for v in by_file.values())} quotes in {len(repl)} files "
          f"(entry 5: {len(c5)} -> {len(new5)} bytes)")


def main():
    out_iso = sys.argv[sys.argv.index("--iso") + 1] if "--iso" in sys.argv else os.path.join(WORK, "build", "ogg_en.iso")
    os.makedirs(os.path.dirname(out_iso), exist_ok=True)
    only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else {"map", "elf", "font", "tables", "battle", "tex"}
    files = {}
    if "map" in only:
        files["DATA/MAP.BIN"] = terrain_ogg.patch(build_map())   # story text + terrain names
    if "elf" in only:
        files["SLPS_258.36"] = build_elf()
        files.update(build_overlays())
    if only & {"font", "tables"}:
        for c in ("SHARED.BIN", "IM.BIN"):
            f = build_shared(c, tuple(only & {"font", "tables"}))
            if f:
                files["DATA/" + c] = f
    story = files.get("DATA/MAP.BIN")
    if "tex" in only:
        files.update(build_textures(files))
    if story is not None:
        # gate: every script leaf the story step changed must survive the later steps
        pristine = open(os.path.join(WORK, "ext", "DATA", "MAP.BIN"), "rb").read()
        final = files["DATA/MAP.BIN"]
        a, b, c = (dict(lice.walk(lice.parse(x))) for x in (pristine, story, final))
        changed = [p for p, n in b.items() if n["kind"] == "leaf" and
                   story[n["off"]:n["off"] + n["size"]] != pristine[a[p]["off"]:a[p]["off"] + a[p]["size"]]]
        lost = [p for p in changed if final[c[p]["off"]:c[p]["off"] + c[p]["size"]] != story[b[p]["off"]:b[p]["off"] + b[p]["size"]]
                and not final[c[p]["off"]:c[p]["off"] + 4] == b"P2IG"]
        assert changed and not lost, f"MAP.BIN story text lost in a later step: {lost[:5]}"
        print(f"MAP.BIN: story text intact in {len(changed)} leaves")
    tmp = os.path.join(WORK, "build", "files")
    os.makedirs(tmp, exist_ok=True)
    print("copying pristine ISO ...")
    shutil.copyfile(find_pristine_iso(), out_iso)
    for name, data in files.items():
        p = os.path.join(tmp, os.path.basename(name))
        open(p, "wb").write(data)
        iso_tool.cmd_write(out_iso, name, p)
    if "battle" in only:
        build_battle(out_iso)
    print("built", out_iso)


if __name__ == "__main__":
    main()
