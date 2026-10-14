"""ISO9660 tool for the OG Gaiden DVD image.

  iso_tool.py list    <iso>                    files with LBA and size
  iso_tool.py extract <iso> <outdir> [names]   extract all files (or only those named)
  iso_tool.py inventory <iso> <out.json>       list + magic + sha1 per file
  iso_tool.py write   <iso> <path> <file>      overwrite a file in place (must fit its sectors)

Plain ISO9660 (no Joliet/UDF needed for PS2 discs). Writing in place keeps every LBA,
so a patched image stays a drop-in replacement and xdelta stays small.
"""
import hashlib
import json
import os
import struct
import sys

SECTOR = 2048


def read_dir(f, lba, size, prefix=""):
    f.seek(lba * SECTOR)
    data = f.read(size)
    pos = 0
    while pos < len(data):
        n = data[pos]
        if n == 0:
            # records never span sectors: skip to the next one
            pos = (pos // SECTOR + 1) * SECTOR
            continue
        rec = data[pos:pos + n]
        ext_lba = struct.unpack_from("<I", rec, 2)[0]
        ext_size = struct.unpack_from("<I", rec, 10)[0]
        flags = rec[25]
        name_len = rec[32]
        name = rec[33:33 + name_len]
        pos += n
        if name in (b"\x00", b"\x01"):
            continue
        name = name.decode("ascii").split(";")[0]
        path = prefix + "/" + name
        if flags & 2:
            yield from read_dir(f, ext_lba, ext_size, path)
        else:
            yield {"path": path, "lba": ext_lba, "size": ext_size,
                   "rec_off": lba * SECTOR + pos - n}


def entries(iso):
    with open(iso, "rb") as f:
        f.seek(16 * SECTOR)
        pvd = f.read(SECTOR)
        assert pvd[1:6] == b"CD001", "not an ISO9660 image"
        root = pvd[156:156 + 34]
        lba = struct.unpack_from("<I", root, 2)[0]
        size = struct.unpack_from("<I", root, 10)[0]
        return sorted(read_dir(f, lba, size), key=lambda e: e["lba"])


def cmd_list(iso):
    for e in entries(iso):
        print(f"{e['lba']:>8}  {e['size']:>11}  {e['path']}")


def copy_out(f, e, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    f.seek(e["lba"] * SECTOR)
    left = e["size"]
    h = hashlib.sha1()
    with open(dst, "wb") as o:
        while left:
            chunk = f.read(min(left, 1 << 22))
            h.update(chunk)
            o.write(chunk)
            left -= len(chunk)
    return h.hexdigest()


def cmd_extract(iso, outdir, names):
    with open(iso, "rb") as f:
        for e in entries(iso):
            if names and e["path"].lstrip("/") not in names and os.path.basename(e["path"]) not in names:
                continue
            copy_out(f, e, os.path.join(outdir, e["path"].lstrip("/")))
            print(e["path"])


def cmd_inventory(iso, out):
    rows = []
    with open(iso, "rb") as f:
        for e in entries(iso):
            f.seek(e["lba"] * SECTOR)
            head = f.read(min(16, e["size"]))
            h = hashlib.sha1()
            f.seek(e["lba"] * SECTOR)
            left = e["size"]
            while left:
                chunk = f.read(min(left, 1 << 22))
                h.update(chunk)
                left -= len(chunk)
            rows.append({**{k: e[k] for k in ("path", "lba", "size")},
                         "magic": head.hex(), "sha1": h.hexdigest()})
            print(f"{e['lba']:>8}  {e['size']:>11}  {head[:8].hex()}  {e['path']}")
    with open(out, "w", encoding="utf-8") as o:
        json.dump(rows, o, indent=1)


def cmd_write(iso, path, src):
    e = next((e for e in entries(iso) if e["path"].lstrip("/") == path.lstrip("/")), None)
    if not e:
        sys.exit(f"{path}: not in image")
    data = open(src, "rb").read()
    room = -(-e["size"] // SECTOR) * SECTOR
    with open(iso, "r+b") as f:
        if len(data) <= room:
            lba = e["lba"]
            f.seek(lba * SECTOR)
            f.write(data + b"\0" * (room - len(data)))
        else:
            # does not fit: move the file to the end of the image (the game opens files by
            # name through the ISO directory, so only the directory record changes)
            f.seek(0, 2)
            lba = -(-f.tell() // SECTOR)
            f.seek(lba * SECTOR)
            f.write(data + b"\0" * (-len(data) % SECTOR))
            total = f.tell() // SECTOR
            f.seek(16 * SECTOR + 80)                      # PVD volume space size
            f.write(struct.pack("<I", total) + struct.pack(">I", total))
            f.seek(e["rec_off"] + 2)
            f.write(struct.pack("<I", lba) + struct.pack(">I", lba))
        if len(data) != e["size"]:
            # update both-endian size in the directory record
            f.seek(e["rec_off"] + 10)
            f.write(struct.pack("<I", len(data)) + struct.pack(">I", len(data)))
    print(f"{path}: wrote {len(data)} bytes at LBA {lba}" + ("" if lba == e["lba"] else " (moved to the end)"))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "list":
        cmd_list(a[1])
    elif a[0] == "extract":
        cmd_extract(a[1], a[2], set(a[3:]))
    elif a[0] == "inventory":
        cmd_inventory(a[1], a[2])
    elif a[0] == "write":
        cmd_write(a[1], a[2], a[3])
    else:
        sys.exit(__doc__)
