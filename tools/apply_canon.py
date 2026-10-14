"""Force glossary canon onto table names: every FIXH Strg name whose Japanese is a canon
glossary key gets the canon English (the glossary is authoritative; AI output is only a
proposal). Prints how many entries changed.

  apply_canon.py [GLOB]      default worksheets/FIXH_*_Strg.json
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import fitcheck

canon = {jp: en for jp, en, _ in fitcheck.load_glossary()}
pat = sys.argv[1] if len(sys.argv) > 1 else "worksheets/FIXH_*_Strg.json"
for path in glob.glob(os.path.join(REPO, pat)):
    ws = json.load(open(path, encoding="utf-8"))
    changed = 0
    for e in ws["strings"]:
        if e.get("kind") == "name" and e["jp"] in canon and e.get("en") != canon[e["jp"]]:
            e["en"] = canon[e["jp"]]
            e["source"] = "canon"
            changed += 1
    json.dump(ws, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    print(os.path.basename(path), changed, "set from canon")
