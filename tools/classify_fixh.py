"""Classify the data-table worksheets and fill the mechanical entries.

  classify_fixh.py         worksheets/FIXH_*_Strg.json and FIXH_*_Expl.json

Strg kinds: number (heights/weights like ３６．０ｔ, converted to ASCII here), filler (－－－,
？？？, converted here), name (translated). Expl entries are kind desc. Existing English is kept.
"""
import glob
import json
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def to_ascii(s):
    return "".join(chr(ord(c) - 0xFEE0) if "！" <= c <= "～" else c for c in s)


def main():
    for path in glob.glob(os.path.join(REPO, "worksheets", "FIXH_*_Strg.json")):
        ws = json.load(open(path, encoding="utf-8"))
        counts = {}
        for e in ws["strings"]:
            jp = e["jp"]
            if re.fullmatch(r"[０-９．，]+[ｍｔ]?", jp):
                e["kind"] = "number"
                e["en"] = e.get("en") or to_ascii(jp)
            elif re.fullmatch(r"[－？]+", jp):
                e["kind"] = "filler"
                e["en"] = e.get("en") or to_ascii(jp)
            elif not e.get("keep"):
                e["kind"] = "name"
            counts[e["kind"]] = counts.get(e["kind"], 0) + 1
        json.dump(ws, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
        print(os.path.basename(path), counts)


if __name__ == "__main__":
    main()
