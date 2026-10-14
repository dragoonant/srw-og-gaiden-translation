"""Create or refresh worksheets for the OG Gaiden stage scripts (MAP.BIN entry 14, LOGO).

  classify_ogg.py            write worksheets/MAP_14_NNNN.json for all 43 scripts

Existing English in a worksheet is kept (matched by pool and id, and only while the Japanese
is unchanged). Each entry gets a kind:
  label        engine label like S0_00_00_00                   keep
  placeholder  エラー (shown only on a script error)             keep
  dialogue     Speaker「line」
  thought      Speaker（thought）
  objective    victory/defeat/skill-point conditions (１． / ・ lines)
  location     scene banner, place names joined by U+3000
  sysmsg       system messages (skill points, items obtained; may carry #NN colour codes)
  text         anything else
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import script

LEAVES = os.path.join(os.path.expanduser("~"), "srwogg-work", "leaves", "DATA_MAP")


def kind_of(jp):
    if re.fullmatch(r"[A-Z0-9_]+", jp):
        return "label"
    if jp == "エラー":
        return "placeholder"
    if re.match(r"^[^「（]{1,24}「", jp):
        return "dialogue"
    if re.match(r"^[^「（]{1,24}（", jp):
        return "thought"
    if re.match(r"^(１|２|３|４|５|・)", jp):
        return "objective"
    if "#" in jp or "獲得しました" in jp or "入手" in jp:
        return "sysmsg"
    if len(jp) <= 30 and "@" not in jp and not re.search(r"[。、！？]", jp):
        return "location"
    return "text"


def main():
    n_files = n_strings = 0
    for i in range(43):
        src = os.path.join(LEAVES, f"0014_{i:04d}.bin")
        ws = script.extract(src)
        ws["file"] = f"MAP.BIN/14/{i}"
        ws["leaf"] = [14, i]
        out = os.path.join(REPO, "worksheets", f"MAP_14_{i:04d}.json")
        old = {}
        if os.path.exists(out):
            for e in json.load(open(out, encoding="utf-8"))["strings"]:
                old[(e["pool"], e["id"])] = e
        for e in ws["strings"]:
            e["kind"] = kind_of(e["jp"])
            e["keep"] = e["kind"] in ("label", "placeholder")
            prev = old.get((e["pool"], e["id"]))
            if prev and prev["jp"] == e["jp"] and prev.get("en") and not e["keep"]:
                e["en"] = prev["en"]
        json.dump(ws, open(out, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
        n_files += 1
        n_strings += len(ws["strings"])
    print(f"{n_files} worksheets, {n_strings} strings")


if __name__ == "__main__":
    main()
