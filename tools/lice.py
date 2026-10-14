"""LICE containers (all of /DATA and /DATA_SP).

Layout, as observed on SLPS-25836:
  0x00  "LICE"
  0x04  u32 header size H (0x800, 0x1000, ... ; the Wpbb table starts here)
  0x08  u32 entry count N
  0x0C  u32 id count M (ids map to entries through the u16 table)
  0x10  u16[M] entry index per id (0xFFFF = no entry); rest of the header is 0xFF
  H     "Wpbb", u32 N, then N x (u32 offset, u32 size), offsets relative to H
Entries are often LICE containers themselves.

  lice.py tree      <file> [depth]          print the tree
  lice.py extract   <file> <outdir>         write every leaf (path = entry indices) + manifest.json
  lice.py roundtrip <file>                  rebuild from parsed parts, compare bytes
"""
import json
import math
import os
import struct
import sys


def parse(buf, base=0, size=None):
    """Return a node: {'kind':'lice', 'hsize', 'ids', 'entries':[...]} or {'kind':'leaf'}."""
    if size is None:
        size = len(buf) - base
    if size < 16 or buf[base:base + 4] != b"LICE":
        return {"kind": "leaf", "off": base, "size": size}
    h, n, m = struct.unpack_from("<III", buf, base + 4)
    w = base + h
    if buf[w:w + 4] != b"Wpbb" or struct.unpack_from("<I", buf, w + 4)[0] != n:
        return {"kind": "leaf", "off": base, "size": size}
    ents = []
    for i in range(n):
        off, sz = struct.unpack_from("<II", buf, w + 8 + i * 8)
        ents.append(parse(buf, w + off, sz))
        ents[-1]["rel"] = off
    return {"kind": "lice", "off": base, "size": size, "hsize": h, "n": n, "m": m, "entries": ents}


def walk(node, path=()):
    yield path, node
    if node["kind"] == "lice":
        for i, e in enumerate(node["entries"]):
            yield from walk(e, path + (i,))


def rebuild(buf, node):
    """Rebuild a LICE from its parts; padding/header bytes copied from the original."""
    if node["kind"] == "leaf":
        return buf[node["off"]:node["off"] + node["size"]]
    b, h = node["off"], node["hsize"]
    out = bytearray(buf[b:b + h])  # LICE header + id table
    table_end = 8 + 8 * node["n"]
    wpbb = bytearray(buf[b + h:b + h + table_end])
    body = bytearray()
    first = node["entries"][0]["rel"] if node["entries"] else table_end
    gap = bytearray(buf[b + h + table_end:b + h + first])  # padding after table
    cur = first
    for i, e in enumerate(node["entries"]):
        data = rebuild(buf, e)
        if e["rel"] > cur:  # inter-entry padding, copied
            body += buf[b + h + cur:b + h + e["rel"]]
            cur = e["rel"]
        struct.pack_into("<II", wpbb, 8 + i * 8, cur, len(data))
        body += data
        cur += len(data)
    tail = buf[b + h + cur:b + node["size"]]
    return bytes(out + wpbb + gap + body + tail)


def alignment(node):
    """Entry alignment of a container: gcd of its entry offsets, capped at 0x800."""
    g = 0
    for e in node["entries"]:
        g = math.gcd(g, e["rel"])
    return min(1 << (g.bit_length() - 1), 0x800) if g else 0x800


def build(buf, node, repl, path=(), force=False):
    """Rebuild with replacement leaves {path tuple: bytes}. Untouched subtrees are copied
    verbatim; changed containers are repacked (entries at the container's alignment,
    zero padding, Wpbb table rewritten, header and id table kept)."""
    if path in repl:
        return repl[path]
    if node["kind"] == "leaf" or (not force and not any(p[:len(path)] == path for p in repl)):
        return buf[node["off"]:node["off"] + node["size"]]
    b, h, n = node["off"], node["hsize"], node["n"]
    al = alignment(node)
    head = bytearray(buf[b:b + h])
    table = bytearray(buf[b + h:b + h + 8 + 8 * n])
    first = node["entries"][0]["rel"] if n else len(table)
    body = bytearray(buf[b + h + len(table):b + h + first])  # padding after the table
    cur = first
    for i, e in enumerate(node["entries"]):
        data = build(buf, e, repl, path + (i,), force)
        aligned = -(-cur // al) * al
        body += b"\0" * (aligned - cur)
        cur = aligned
        struct.pack_into("<II", table, 8 + 8 * i, cur, len(data))
        body += data
        cur += len(data)
    if path:
        end = -(-(h + cur) // al) * al
    else:
        # a top-level file keeps its size while the content fits (MAP.BIN carries ~9.8 MB
        # of zero padding at the end, room for longer text without moving the file)
        end = max(-(-(h + cur) // 0x800) * 0x800, node["size"])
    out = bytes(head + table + body)
    return out + b"\0" * (end - len(out))


def write_top_level(src, replace, out, out_off):
    """Streamed rebuild of a big top-level container (BATTLE.BIN is 1.8 GB): top-level entries
    in `replace` {index: bytes} are swapped in, the others are copied in chunks, later entries
    shift if needed, and the file keeps its original size (it has to fit its slack).
    src: bytes-like (mmap); out: file opened r+b; out_off: where the file starts in `out`."""
    root = parse(src)
    h, n = root["hsize"], root["n"]
    al = alignment(root)
    head = bytearray(src[:h])
    table = bytearray(src[h:h + 8 + 8 * n])
    first = root["entries"][0]["rel"]
    plan, cur = [], first
    for i, e in enumerate(root["entries"]):
        size = len(replace[i]) if i in replace else e["size"]
        cur = -(-cur // al) * al
        plan.append((i, cur, size))
        struct.pack_into("<II", table, 8 + 8 * i, cur, size)
        cur += size
    total = -(-(h + cur) // 0x800) * 0x800
    if total > root["size"]:
        raise ValueError(f"container grew past its size: {total} > {root['size']}")
    out.seek(out_off)
    out.write(bytes(head + table))
    out.write(src[h + len(table):h + first])
    pos = h + first
    for i, rel, size in plan:
        tgt = h + rel
        if tgt > pos:
            out.write(b"\0" * (tgt - pos))
            pos = tgt
        if i in replace:
            out.write(replace[i])
        else:
            e = root["entries"][i]
            a = e["off"]
            for c in range(0, e["size"], 1 << 24):
                out.write(src[a + c:a + min(e["size"], c + (1 << 24))])
        pos += size
    left = root["size"] - pos
    while left:
        k = min(left, 1 << 24)
        out.write(b"\0" * k)
        left -= k


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    buf = open(a[1], "rb").read()
    root = parse(buf)
    if a[0] == "tree":
        depth = int(a[2]) if len(a) > 2 else 99
        for p, n in walk(root):
            if len(p) <= depth:
                tag = buf[n["off"]:n["off"] + 4]
                print(f"{'  ' * len(p)}{'/'.join(map(str, p)) or '.'} {n['kind']} "
                      f"off={n['off']:#x} size={n['size']:#x} {tag!r}"
                      + (f" n={n['n']} m={n['m']} h={n['hsize']:#x}" if n["kind"] == "lice" else ""))
    elif a[0] == "extract":
        out = a[2]
        man = []
        for p, n in walk(root):
            if n["kind"] == "leaf":
                name = "_".join(f"{i:04d}" for i in p) or "root"
                os.makedirs(out, exist_ok=True)
                with open(os.path.join(out, name + ".bin"), "wb") as f:
                    f.write(buf[n["off"]:n["off"] + n["size"]])
                man.append({"path": list(p), "file": name + ".bin", "off": n["off"], "size": n["size"]})
        json.dump(man, open(os.path.join(out, "manifest.json"), "w"), indent=0)
        print(f"{len(man)} leaves")
    elif a[0] == "repack":
        # force-repack every container from the packing rules and compare
        new = build(buf, root, {}, force=True)
        same = new == buf
        print(f"{a[1]}: repack {'identical' if same else 'DIFFERENT'} ({len(new)} vs {len(buf)})")
        if not same:
            d = next((i for i in range(min(len(new), len(buf))) if new[i] != buf[i]), None)
            print(f"  first difference at {d:#x}" if d is not None else "  length differs")
            sys.exit(1)
    elif a[0] == "roundtrip":
        new = rebuild(buf, root)
        ok = new == buf
        print(f"{a[1]}: {'identical' if ok else 'DIFFERENT'} ({len(new)} vs {len(buf)})")
        if not ok:
            d = next(i for i in range(min(len(new), len(buf))) if new[i] != buf[i])
            print(f"  first difference at {d:#x}")
            sys.exit(1)


if __name__ == "__main__":
    main()
