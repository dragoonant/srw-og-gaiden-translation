"""Help and tutorial text in SHARED.BIN / IM.BIN.

Two shapes, both fixed-size so English (1 byte a letter) always has room:
  slot files  (leaves 8/1, 8/2, 8/3: 128-byte slots; 8/4: 2048-byte slots) - one NUL-terminated
              Shift-JIS string per slot; '#' is a line break, <C=n>...</C> colours a phrase
  page files  (leaves 10/0..54, 3,976 bytes) - one help page in layout markup:
              <X=..><Y=..>[<C=..>]<W=..><H=..>text</H></W>[</C>]</Y></X> elements joined by '#';
              only the text between the tags is translated, tags and order are kept

  help_ogg.py extract CONTAINER_LEAVES_DIR PREFIX     worksheets PREFIX_slots.json, PREFIX_pages.json

build_slot(data, slot, entries, encode) / build_page(data, entries, encode) return new leaf bytes.
"""
import json
import os
import re
import sys

SLOT_FILES = {(8, 1): 128, (8, 2): 128, (8, 3): 128, (8, 4): 2048}
PAGE_RANGE = range(0, 55)          # leaves (10, n)
TEXT = re.compile(r">([^<>]+)<")


def read_slots(data, size):
    out = []
    for k in range(len(data) // size):
        raw = data[k * size:(k + 1) * size].split(b"\0", 1)[0]
        out.append(raw)
    return out


def page_segments(data):
    """[(start, end, text)] byte spans of translatable text in a page (Shift-JIS decoded)."""
    body = data.split(b"\0", 1)[0]
    segs = []
    for m in re.finditer(rb">([^<>]+)<", body):
        raw = m.group(1)
        if re.fullmatch(rb"[#\s]*", raw):
            continue
        try:
            txt = raw.decode("cp932")
        except UnicodeDecodeError:
            continue
        if not re.search(r"[^\x00-\x7f]", txt):
            continue
        segs.append((m.start(1), m.end(1), txt))
    return segs


def build_slot(data, size, entries, encode):
    out = bytearray(data)
    for e in entries:
        if not e.get("en") or e.get("keep"):
            continue
        b = encode(e["en"])
        if len(b) >= size:
            raise ValueError(f"slot {e['id']}: {len(b)} bytes > {size - 1}")
        out[e["id"] * size:(e["id"] + 1) * size] = b + b"\0" * (size - len(b))
    return bytes(out)


def build_page(data, entries, encode):
    body = data.split(b"\0", 1)[0]
    segs = page_segments(data)
    by = {e["id"]: e for e in entries}
    parts, pos = [], 0
    for k, (s, e_, _txt) in enumerate(segs):
        parts.append(body[pos:s])
        ent = by.get(k)
        parts.append(encode(ent["en"]) if ent and ent.get("en") and not ent.get("keep") else body[s:e_])
        pos = e_
    parts.append(body[pos:])
    new = b"".join(parts)
    if len(new) >= len(data):
        raise ValueError(f"page grew past {len(data)} bytes")
    return new + b"\0" * (len(data) - len(new))


def extract(leaves_dir, prefix):
    slots = {"file": prefix + " help slots", "format": "HELP-SLOT", "strings": []}
    pages = {"file": prefix + " help pages", "format": "HELP-PAGE", "strings": []}
    n = 0
    for (a, b), size in SLOT_FILES.items():
        p = os.path.join(leaves_dir, f"{a:04d}_{b:04d}.bin")
        if not os.path.exists(p):
            continue
        for k, raw in enumerate(read_slots(open(p, "rb").read(), size)):
            if not raw.strip():
                continue
            try:
                jp = raw.decode("cp932")
            except UnicodeDecodeError:
                continue
            slots["strings"].append({"id": n, "leaf": [a, b], "slot": k, "size": size, "jp": jp, "en": "",
                                     "kind": "help", "keep": not re.search(r"[^\x00-\x7f]", jp)})
            n += 1
    n = 0
    for k in PAGE_RANGE:
        p = os.path.join(leaves_dir, f"0010_{k:04d}.bin")
        if not os.path.exists(p):
            continue
        for s, (_a, _b, txt) in enumerate(page_segments(open(p, "rb").read())):
            pages["strings"].append({"id": n, "leaf": [10, k], "seg": s, "jp": txt, "en": "",
                                     "kind": "help_line", "keep": False})
            n += 1
    return slots, pages


def main():
    a = sys.argv[1:]
    if not a or a[0] != "extract":
        sys.exit(__doc__)
    slots, pages = extract(a[1], a[2])
    for suffix, ws in (("_slots.json", slots), ("_pages.json", pages)):
        json.dump(ws, open(a[2] + suffix, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
        print(a[2] + suffix, len(ws["strings"]))


if __name__ == "__main__":
    main()
