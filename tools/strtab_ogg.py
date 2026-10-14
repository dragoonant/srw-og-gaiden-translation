"""Japanese strings inside the boot ELF and the code overlays (menus, system messages).

  strtab_ogg.py extract FILE OUT.json     every Japanese string with address, budget, references
  strtab_ogg.py roundtrip FILE            extract + build with no changes, compare

Files: SLPS_258.36 (MIPS ELF, segment 0 at file offset 0x180 = 0x100000) and OL/*.BIN
(MWo3 overlays, loaded whole at the address in their header). Strings are NUL-terminated
Shift-JIS starting on a 4-byte boundary. A string's budget is its slot: the bytes up to the
next non-zero byte after its terminator, minus one for the NUL. Replacement is in place
(pointers stay valid); English longer than the budget is refused.

build(data, ws) returns patched bytes (used by build_ogg.py).
"""
import json
import re
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SJIS = re.compile(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]|[\x20-\x7e]|[\xa1-\xdf]|\n)+\x00")
JP2 = re.compile(rb"[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]")


def layout(path, data):
    """(base_va, start, end) of the scannable region."""
    if data[:4] == b"\x7fELF":
        off, va, filesz = struct.unpack_from("<III", data, 0x34 + 4)[0], 0x100000, None
        p = struct.unpack_from("<I", data, 0x1C)[0]
        _, off, va, _, filesz = struct.unpack_from("<5I", data, p)
        return va - off, off, off + filesz
    if data[:4] == b"MWo3":
        base = struct.unpack_from("<I", data, 8)[0]
        return base, 0x40, len(data)
    raise ValueError("unknown file type")


def plausible(text):
    """Reject code bytes that happen to decode as Shift-JIS: real text has no half-width kana,
    uses ASCII only for format/colour codes, and is mostly kana, common kanji or punctuation."""
    if re.search(r"[｡-ﾟ]", text):
        return False
    # code bytes that decode as a few kanji plus a stray ASCII/Cyrillic/box character
    # (搬D隙, 精эB, 錬ｎ6): no kana, no format codes, short
    if (len(text) <= 5 and not re.search(r"[ぁ-んァ-ヶ%#]", text)
            and re.search(r"[!-~а-яёА-ЯЁ─-╿]|(?<![Ａ-Ｚａ-ｚ])[ａ-ｚ](?![ａ-ｚ．])", text)
            and re.search(r"[一-鿿]", text)):
        return False
    ascii_part = re.sub(r"%[-+0-9.]*[sdxXcuf]|#\d\d|##|\n", "", text)
    if re.search(r"[!-~]", re.sub(r"[ 0-9A-Za-z/()+\-:.,]", "", ascii_part)):
        return False
    wide = [c for c in text if ord(c) > 0x7F]
    if len(wide) < 2:
        return False
    def common(c):
        b = c.encode("cp932")
        if len(b) != 2:
            return False
        code = (b[0] << 8) | b[1]
        return 0x8140 <= code <= 0x84BE or 0x889F <= code <= 0x9872    # symbols/kana/Latin, kanji level 1
    if sum(common(c) for c in wide) / len(wide) < 0.75:
        return False
    if re.search(r"[A-Za-z]", ascii_part) and sum(common(c) for c in wide) < 2:
        return False
    return True


def slot_end(s, e, nxt):
    """End of the bytes a string at s (NUL ends at e-1) may use: the alignment boundary its start
    implies (8 or 4), or the next string for packed (unaligned) tables."""
    align = 8 if s % 8 == 0 else (4 if s % 4 == 0 else 1)
    if align == 1:
        return nxt
    return min(nxt, (e + align - 1) // align * align)


def find_strings(data, base, start, end):
    out = []
    for m in SJIS.finditer(data, start, end):
        s, e = m.start(), m.end()          # e is past the NUL
        # a string starts right after a NUL; packed tables put strings at any alignment, but a
        # match that does not follow a NUL is trimmed to a 4-aligned start that does
        if not (s > start and data[s - 1] == 0):
            while s % 4 and s < e:
                s += 1
            if s >= e - 1 or (s > start and data[s - 1] != 0):
                continue
        if s >= e - 1:
            continue
        body = data[s:e - 1]
        if len(JP2.findall(body)) < 1:
            continue
        try:
            text = body.decode("cp932")
        except UnicodeDecodeError:
            continue
        if not plausible(text):
            continue
        nxt = e
        while nxt < end and data[nxt] == 0:
            nxt += 1
        out.append({"off": s, "va": base + s, "jp": text, "raw": body.hex(),
                    # strings are 8-byte aligned: the slot ends at the next 8-byte boundary after
                    # the NUL. Zeros beyond it are other data (writing into them hung the
                    # Library screen through EXOL).
                    "budget": slot_end(s, e, nxt) - s - 1})
    return out


def count_refs(data, base, start, end, strings):
    words = {}
    for o in range(start - start % 4, end - 3, 4):
        w = struct.unpack_from("<I", data, o)[0]
        words.setdefault(w, 0)
        words[w] += 1
    for st in strings:
        st["refs"] = words.get(st["va"], 0)


def extract(path):
    data = open(path, "rb").read()
    base, start, end = layout(path, data)
    strings = find_strings(data, base, start, end)
    count_refs(data, base, start, end, strings)
    ws = {"file": path.replace("\\", "/").split("/ext/")[-1], "format": "STRTAB", "strings": []}
    for k, st in enumerate(strings):
        ws["strings"].append({"id": k, "va": hex(st["va"]), "off": st["off"], "raw": st["raw"],
                              "jp": st["jp"], "en": "", "budget": st["budget"], "refs": st["refs"],
                              "kind": "ui", "keep": False})
    return ws


def build(data, ws, encode):
    """encode(en) -> bytes. Refuses over-budget entries (returns them in a list)."""
    out = bytearray(data)
    over = []
    for e in ws["strings"]:
        if not e.get("en") or e.get("keep"):
            continue
        assert out[e["off"]:e["off"] + len(bytes.fromhex(e["raw"]))] == bytes.fromhex(e["raw"]), e["va"]
        if "en_raw" in e:                 # exact bytes (when the converter's pairing must not apply)
            b = e["en_raw"].encode("cp932")
        else:
            try:
                b = encode(e["en"], e["budget"])
            except TypeError:
                b = encode(e["en"])
        if len(b) > e["budget"]:
            over.append((e["id"], e["va"], len(b), e["budget"]))
            continue
        out[e["off"]:e["off"] + e["budget"] + 1] = b + b"\0" * (e["budget"] + 1 - len(b))
    return bytes(out), over


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "extract":
        ws = extract(a[1])
        json.dump(ws, open(a[2], "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
        n = len(ws["strings"])
        print(f"{a[1]}: {n} strings, {sum(1 for e in ws['strings'] if e['refs'])} with direct pointers")
    elif a[0] == "roundtrip":
        data = open(a[1], "rb").read()
        ws = extract(a[1])
        for e in ws["strings"]:
            e["en"] = e["jp"]
        new, over = build(data, ws, lambda s: bytes.fromhex(next(x["raw"] for x in ws["strings"] if x["jp"] == s)))
        print("identical" if new == data else "DIFFERENT", "over:", len(over))


if __name__ == "__main__":
    main()
