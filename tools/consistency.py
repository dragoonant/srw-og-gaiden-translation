"""Term consistency report: where a glossary term (canon or proposal) appears in the Japanese,
is its English in the translation? Lists terms with misses and the most common English used
instead, so drift (Clywolves vs Cry Wolves) is caught before release.

  consistency.py [--min N] [--top K]
"""
import collections
import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import translate_ogg

minimum = int(sys.argv[sys.argv.index("--min") + 1]) if "--min" in sys.argv else 5
top = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 40
terms = [(jp, en, rx) for jp, en, rx in translate_ogg.load_terms() if len(jp) >= 3]
entries = []
for p in glob.glob(os.path.join(REPO, "worksheets", "*.json")):
    entries += [e for e in json.load(open(p, encoding="utf-8"))["strings"] if e.get("en") and not e.get("keep")]
report = []
for jp, en, rx in terms:
    hits = [e for e in entries if jp in e["jp"] and rx.search(e["jp"])]
    if len(hits) < minimum:
        continue
    miss = [e for e in hits if en.lower() not in e["en"].lower()]
    if miss and len(miss) / len(hits) > 0.15:
        words = collections.Counter()
        for e in miss:
            for w in re.findall(r"[A-Z][\w'-]+(?: [A-Z][\w'-]+)*", e["en"]):
                words[w] += 1
        report.append((len(miss), len(hits), jp, en, words.most_common(4)))
report.sort(reverse=True)
for m, h, jp, en, w in report[:top]:
    print(f"{m:4}/{h:<4} {jp} -> {en} | instead: {w}")
print(f"{len(report)} terms with >15% misses (of {len(terms)} terms)")
