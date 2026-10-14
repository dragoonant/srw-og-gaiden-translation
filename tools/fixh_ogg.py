"""OG Gaiden data tables: the "Vers/Fixh" file in SHARED.BIN and IM.BIN (LICE leaf (3, 0)).

Layout (little-endian):
  0x00 "Vers" u32 0x10 u32 2 u32 0
  0x10 "Fixh" u32 size (0x7C)  then u32 offsets of 29 tables (absolute, 4-aligned)
  table: tag[4] u32 byte_size u32 count ... ; tables padded with zeros to 4 bytes
  Strg (names) and Sent (description lines): u32 offsets[count] at +12, relative to the tag,
       then NUL-terminated Shift-JIS strings, back to back
  Expl (descriptions): u32 offsets[count] at +12, relative to the tag; each record is
       u16 n, u16 sent_index[n] (the description's display lines, in order)
Other tables (Unit, Weap, Plot, KeyW, ...) reference Strg and Expl by index and are kept.

  fixh_ogg.py tables    LEAF                      list tables
  fixh_ogg.py extract   LEAF OUT_PREFIX           worksheets OUT_PREFIX_Strg.json, _Expl.json
  fixh_ogg.py roundtrip LEAF                      rebuild from parsed parts, compare bytes

build(leaf, strg_ws, expl_ws, wrap) returns new leaf bytes (used by build_ogg.py).
"""
import json
import struct
import sys

N_TABLES = 29


def tables(d):
    assert d[:4] == b"Vers" and d[0x10:0x14] == b"Fixh"
    n = (struct.unpack_from("<I", d, 0x14)[0] - 8) // 4
    assert n == N_TABLES
    offs = list(struct.unpack_from(f"<{n}I", d, 0x18))
    out = []
    for k, o in enumerate(offs):
        size = struct.unpack_from("<I", d, o + 4)[0]
        end = offs[k + 1] if k + 1 < n else len(d)
        out.append({"tag": d[o:o + 4].decode("ascii"), "off": o, "size": size, "span": end - o})
    return out


def get_table(d, tag):
    t = next(t for t in tables(d) if t["tag"] == tag)
    return d[t["off"]:t["off"] + t["size"]]


def parse_raw(tb):
    """Strings as raw bytes (cp932 maps some IBM/NEC duplicate kanji to one character, so
    untouched strings are written back byte for byte)."""
    count = struct.unpack_from("<I", tb, 8)[0]
    offs = struct.unpack_from(f"<{count}I", tb, 12)
    return [tb[o:tb.index(b"\0", o)] for o in offs]


def parse_strings(tb):
    return [b.decode("cp932") for b in parse_raw(tb)]


def build_strings(tag, strings, tail_merge=False):
    """String table bytes. tail_merge: a string that is the ending of a longer one points into
    it (strings are read up to their NUL, so this saves space without changing what is read)."""
    count = len(strings)
    head = 12 + 4 * count
    raw = [(s if isinstance(s, bytes) else s.encode("cp932")) for s in strings]
    if not tail_merge:
        blobs, offs, pos = [], [], head
        for b in raw:
            offs.append(pos)
            blobs.append(b + b"\0")
            pos += len(b) + 1
        return struct.pack(f"<4sII{count}I", tag.encode("ascii"), pos, count, *offs) + b"".join(blobs)
    # place longest-first in reverse-sorted order so suffixes follow the string that contains them
    uniq = sorted(set(raw), key=lambda b: b[::-1], reverse=True)
    where, pool, prev = {}, bytearray(), None
    for b in uniq:
        if prev is not None and prev.endswith(b):
            where[b] = where[prev] + len(prev) - len(b)
            continue
        where[b] = len(pool)
        pool += b + b"\0"
        prev = b
    offs = [head + where[b] for b in raw]
    return struct.pack(f"<4sII{count}I", tag.encode("ascii"), head + len(pool), count, *offs) + bytes(pool)


def parse_expl(tb):
    count = struct.unpack_from("<I", tb, 8)[0]
    offs = struct.unpack_from(f"<{count}I", tb, 12)
    out = []
    for o in offs:
        n = struct.unpack_from("<H", tb, o)[0]
        out.append(list(struct.unpack_from(f"<{n}H", tb, o + 2)))
    return out


def build_expl(records):
    count = len(records)
    head = 12 + 4 * count
    blobs, offs, pos = [], [], head
    for r in records:
        b = struct.pack(f"<H{len(r)}H", len(r), *r)
        offs.append(pos)
        blobs.append(b)
        pos += len(b)
    return struct.pack(f"<4sII{count}I", b"Expl", pos, count, *offs) + b"".join(blobs)


def assemble(d, replace):
    """Rebuild the file with some tables replaced {tag: bytes (unpadded)}."""
    ts = tables(d)
    out = bytearray(d[:ts[0]["off"]])
    offs = []
    for t in ts:
        body = replace.get(t["tag"], d[t["off"]:t["off"] + t["size"]])
        offs.append(len(out))
        if t["tag"] in replace:
            out += body + b"\0" * (-len(body) % 4)
        else:
            out += d[t["off"]:t["off"] + t["span"]]     # original bytes, padding included
    struct.pack_into(f"<{N_TABLES}I", out, 0x18, *offs)
    return bytes(out)


def extract(d, prefix):
    strg = parse_strings(get_table(d, "Strg"))
    sent = parse_strings(get_table(d, "Sent"))
    expl = parse_expl(get_table(d, "Expl"))
    ws_s = {"file": prefix + " Strg", "format": "FIXH-Strg",
            "strings": [{"id": k, "jp": s, "en": "", "kind": "name", "keep": not s.strip()}
                        for k, s in enumerate(strg)]}
    ws_e = {"file": prefix + " Expl", "format": "FIXH-Expl",
            "strings": [{"id": k, "jp": "\n".join(sent[i] for i in r), "en": "", "kind": "desc",
                         "lines": len(r), "keep": not any(sent[i].strip() for i in r)}
                        for k, r in enumerate(expl)]}
    return ws_s, ws_e


def build(d, strg_ws=None, expl_ws=None, wrap=None):
    """New file bytes from worksheets. wrap(en) -> list of display lines for a description."""
    rep = {}
    if strg_ws:
        strg = parse_raw(get_table(d, "Strg"))
        for e in strg_ws["strings"]:
            if e.get("en") and not e.get("keep"):
                strg[e["id"]] = e["en_game"] if "en_game" in e else e["en"]
        rep["Strg"] = build_strings("Strg", strg, tail_merge=True)
    if expl_ws:
        # The game loads this file into a buffer of its original size, so Sent must not grow:
        # new English lines take over the slots of Japanese lines that no untranslated
        # description uses any more, leftover dead slots are emptied, and indices stay stable.
        sent = parse_raw(get_table(d, "Sent"))
        expl = parse_expl(get_table(d, "Expl"))
        new_recs = {}
        for e in expl_ws["strings"]:
            if e.get("en") and not e.get("keep"):
                lines = wrap(e["en"]) if wrap else e["en"].split("\n")
                new_recs[e["id"]] = [ln if isinstance(ln, bytes) else ln.encode("cp932") for ln in lines]
        kept = {i for k, r in enumerate(expl) if k not in new_recs for i in r}
        free = [i for i in range(len(sent)) if i not in kept]
        index = {sent[i]: i for i in sorted(kept)}
        for k, lines in new_recs.items():
            rec = []
            for ln in lines:
                if ln not in index:
                    slot = free.pop(0) if free else None
                    if slot is None:
                        slot = len(sent)
                        sent.append(ln)
                    else:
                        sent[slot] = ln
                    index[ln] = slot
                rec.append(index[ln])
            expl[k] = rec
        for i in free:
            sent[i] = b""
        rep["Sent"] = build_strings("Sent", sent, tail_merge=True)
        rep["Expl"] = build_expl(expl)
    return assemble(d, rep)


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    d = open(a[1], "rb").read()
    if a[0] == "tables":
        for t in tables(d):
            print(f"{t['tag']} off={t['off']:#x} size={t['size']:#x} span={t['span']:#x}")
    elif a[0] == "extract":
        ws_s, ws_e = extract(d, a[2])
        for suffix, ws in (("_Strg.json", ws_s), ("_Expl.json", ws_e)):
            json.dump(ws, open(a[2] + suffix, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
            print(a[2] + suffix, len(ws["strings"]))
    elif a[0] == "roundtrip":
        rep = {"Strg": build_strings("Strg", parse_raw(get_table(d, "Strg"))),
               "Sent": build_strings("Sent", parse_raw(get_table(d, "Sent"))),
               "Expl": build_expl(parse_expl(get_table(d, "Expl")))}
        for tag, body in rep.items():
            orig = get_table(d, tag)
            print(tag, "identical" if body == orig else f"DIFFERENT ({len(body)} vs {len(orig)})")
        new = assemble(d, rep)
        print("file", "identical" if new == d else f"DIFFERENT ({len(new)} vs {len(d)})")


if __name__ == "__main__":
    main()
