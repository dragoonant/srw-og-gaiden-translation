#!/usr/bin/env python3
"""AI translation pass for OG Gaiden through the Anthropic Message Batches API.

  submit GLOB... [--model claude-opus-5-5] [--effort medium] [--chunk 80] [--cap 60] [--dry-run]
  status BATCH_ID
  collect BATCH_ID
  check [GLOB...]        list English that breaks the build gates (rows, bytes, codes)
  retry [GLOB...]        clear failing English, keeping the failure as feedback

Adapted from the 2nd OG translate_batch.py. Per request the model sees the style guide (cached
system prompt), up to CHUNK untranslated lines in script order with their kind and a length
budget, the glossary terms that occur in them, and the lines just before for context. It
returns JSON {"translations":[{"key","en"}]}. Identical Japanese is translated once
(translation memory, translations/tm_ogg.json) and filled everywhere.

Spend: every collected batch's cost goes to translations/spent.json; submit refuses when the
estimate (with a 30% margin) would take the total past --cap.
"""
import glob
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import fitcheck  # noqa: E402  (glossary loader)
import ogg_text  # noqa: E402

STATE_DIR = os.path.join(REPO, "translations", "batches")
TM_PATH = os.path.join(REPO, "translations", "tm_ogg.json")
SPENT_PATH = os.path.join(REPO, "translations", "spent.json")
# Batch prices, $ per million tokens (50% of standard). Cache writes 1.25x input, reads 0.05x.
PRICES = {"claude-opus-5-5": {"in": 2.0, "out": 10.0}, "claude-sonnet-5-5": {"in": 1.0, "out": 5.0}}
COST_PER_CHAR = 0.26 / 40944    # 2nd OG chapter 1 (Opus 5.5, batch): $ per char of request text
MAX_TOKENS = 32000
DIALOGUE_CHARS = 115
BUDGET = {"dialogue": DIALOGUE_CHARS, "thought": DIALOGUE_CHARS, "objective": 48, "location": 40,
          "sysmsg": 48, "text": 60, "name": 28, "desc": 46, "battle": 90}


def reference_names():
    """Akurasu wiki pairs (reference only, never canon): jp -> [en forms]."""
    import csv
    ref = {}
    for f in ("akurasu_ogg.tsv", "akurasu_og2nd.tsv"):
        p = os.path.join(REPO, "glossary", f)
        if os.path.exists(p):
            for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="	"):
                ref.setdefault(r["jp"], [])
                if r["en"] not in ref[r["jp"]]:
                    ref[r["jp"]].append(r["en"])
    return ref

SCHEMA = {
    "type": "object",
    "properties": {"translations": {"type": "array", "items": {
        "type": "object",
        "properties": {"key": {"type": "string"}, "en": {"type": "string"}},
        "required": ["key", "en"], "additionalProperties": False}}},
    "required": ["translations"], "additionalProperties": False,
}


def system_prompt():
    guide = open(os.path.join(REPO, "docs", "style-guide.md"), encoding="utf-8").read()
    return (
        "You translate the Japanese PS2 game Super Robot Taisen OG Gaiden (2007) into English for "
        "a fan translation. It follows the same team's 2nd Super Robot Wars OG patch, and the two "
        "must read as one series. The project's style guide follows; apply it exactly.\n\n"
        + guide + "\n\n"
        "Working rules for every request:\n"
        "- Translate each item's jp into natural, idiomatic English that keeps the speaker's voice "
        "and the scene's tone. Do not add or drop information. No translator notes.\n"
        "- kind=dialogue: jp is Speaker「line」. Write 'Speaker: line' with the speaker's short "
        "English name (glossary form), no quotation marks. ？？？ is '???'. kind=thought: "
        "Speaker（thought） becomes 'Speaker: (thought)'.\n"
        "- The @ marks in jp are the Japanese line layout only. For dialogue and thoughts write one "
        "paragraph with no line breaks; the build wraps it. For objectives, system messages and "
        "lists, keep one line per Japanese line and join them with \\n.\n"
        "- Stay within max_chars characters per item (per line for lists). Rephrase to fit rather "
        "than cutting meaning.\n"
        "- kind=location: a scene banner, places joined by an ideographic space. Write "
        "'Place - Sub-place' in Title Case.\n"
        "- kind=objective: victory/defeat/skill-point conditions. Keep the numbering ('1. ...') "
        "and bullets ('- ' for ・), short and precise. ・無し is '- None.'\n"
        "- Keep colour codes #NN and ## exactly around the same words, and keep a ? placeholder "
        "where the Japanese has one.\n"
        "- Keyword tags like <特機> stay tags with the English term inside (<Super Robot>), used "
        "at most as often as in the Japanese.\n"
        "- Use the glossary forms given in the request for every name and term, exactly. For a "
        "name not in the glossary, use the official or most common English romanization, with "
        "long vowels dropped as in Kota and Lune.\n"
        "- Never write @, or < > outside keyword tags. Plain ASCII only (no full-width letters).\n"
        "- kind=name: a name from the game's data tables (unit, weapon, pilot, part, skill, "
        "episode title...). Give the English name only, in Title Case, as the official or fan "
        "canon writes it. Prefer the glossary; reference_names (Akurasu wiki) are hints, not canon.\n"
        "- kind=ui: a menu label, option or system message from the game's code. It replaces "
        "the Japanese in place, so max_chars is a hard limit; use short, standard game-UI English "
        "(e.g. Move, Parts, Spirit, Status, Attack, Wait, End Turn) and keep printf codes (%s, %d) "
        "in the same order.\n"
        "- kind=battle: a pilot's battle quote (attack, dodge, damage, defeat...). All items of one "
        "file belong to the same pilot: keep that voice consistent. Drop the 「」 brackets, write "
        "one line (the battle window wraps it), punchy and natural. Leave the enemy's gender "
        "unspecified unless the Japanese is explicit.\n"
        "- kind=help: a tutorial text. '#' is a line break: keep about the same number of lines, "
        "each at most 40 characters, and keep <C=n>...</C> colour tags around the matching words. "
        "## (an empty line) stays where it is.\n"
        "- kind=help_line: one display line of a help page. Consecutive help_line items of the same "
        "page are running text split across lines: split your English across the same keys, in "
        "order, so each line reads naturally and the sentences continue. Never move text to a "
        "different page.\n"
        "- kind=desc: a help or database description. Translate as clear, compact prose; the jp "
        "line breaks are layout only; write one paragraph (the build re-wraps it).\n"
        "- Return every key you were given, once, in the JSON format required."
    )


def load_json(p, default):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def save_json(p, obj, indent=1):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(obj, open(p, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=indent)


def api_key():
    k = os.environ.get("ANTHROPIC_API_KEY")
    if not k and sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
                k = winreg.QueryValueEx(h, "ANTHROPIC_API_KEY")[0]
        except OSError:
            k = None
    if not k:
        sys.exit("ANTHROPIC_API_KEY is not set")
    return k


def client():
    import anthropic
    return anthropic.Anthropic(api_key=api_key())


def key_of(e):
    return f"{e.get('pool', '')}{e['id']}"


def worksheets(pats):
    return sorted({p for pat in pats for p in glob.glob(os.path.join(REPO, pat))})


def load_terms():
    """Canon glossary first, then the unsigned name proposals (glossary/ogg_proposals.tsv) so
    every name gets one spelling everywhere until evilgouki signs the list."""
    import csv
    terms = fitcheck.load_glossary()
    have = {jp for jp, _, _ in terms}
    p = os.path.join(REPO, "glossary", "ogg_proposals.tsv")
    if os.path.exists(p):
        kata = "゠-ヿ"
        for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="	"):
            if len(r["jp"]) >= 2 and r["en"] and r["jp"] not in have:
                rx = re.compile("(?<![%s])%s(?![%s])" % (kata, re.escape(r["jp"]), kata))
                terms.append((r["jp"], r["en"], rx))
    terms.sort(key=lambda t: -len(t[0]))
    return terms


def build_requests(paths, model, effort, chunk, tm):
    glossary = load_terms()
    refs = reference_names()
    sysmsg = [{"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}]
    requests, plan, prefilled, queued = [], {}, 0, set()
    for path in paths:
        rel = os.path.relpath(path, REPO).replace("\\", "/")
        ws = json.load(open(path, encoding="utf-8"))
        todo, changed = [], False
        for e in ws["strings"]:
            if e.get("keep") or e.get("en"):
                continue
            if e["jp"] in tm:
                e["en"] = tm[e["jp"]]
                prefilled += 1
                changed = True
                continue
            if e["jp"] in queued:
                continue        # duplicate in this submission: filled from memory on collect
            queued.add(e["jp"])
            todo.append(e)
        if changed:
            save_json(path, ws)
        order = {key_of(e): k for k, e in enumerate(ws["strings"])}
        for c in range(0, len(todo), chunk):
            part = todo[c:c + chunk]
            first = order[key_of(part[0])]
            prev = [x["jp"] for x in ws["strings"][max(0, first - 6):first]
                    if x.get("kind") in ("dialogue", "thought", "battle") and x.get("pool") == part[0].get("pool")]
            items, terms, hints = [], {}, {}
            for e in part:
                budget = BUDGET.get(e["kind"], 60)
                if e["kind"] == "desc":     # re-wrapped by the build: a total, from the Japanese length
                    budget = max(40, round(len(e["jp"].replace("\n", "")) * 1.9))
                if e.get("budget"):         # in-place executable string: hard byte limit
                    budget = min(e["budget"], 2 * len(e["jp"]) + 4)
                if e["kind"] == "help":
                    budget = min(e["size"] - 1, max(40, round(len(e["jp"]) * 1.9)))
                if e["kind"] == "help_line":
                    budget = max(12, round(len(e["jp"]) * 1.9))
                item = {"key": key_of(e), "kind": e["kind"], "jp": e["jp"], "max_chars": budget}
                if e.get("retry_note"):
                    item["previous_attempt_failed"] = e["retry_note"]
                items.append(item)
                for gjp, gen, rx in glossary:
                    if gjp in e["jp"] and rx.search(e["jp"]):
                        terms[gjp] = gen
                if e["kind"] == "name" and e["jp"] in refs and e["jp"] not in terms:
                    hints[e["jp"]] = refs[e["jp"]]
            payload = {"file": rel, "glossary": terms, "previous_lines_for_context": prev, "items": items}
            if hints:
                payload["reference_names"] = hints
            cid = "r%05d" % len(requests)
            requests.append({"custom_id": cid, "params": {
                "model": model, "max_tokens": MAX_TOKENS, "system": sysmsg,
                "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}},
                "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}})
            plan[cid] = {"path": rel, "keys": [key_of(e) for e in part]}
    return requests, plan, prefilled


def cmd_submit(argv):
    opt = lambda k, d: argv[argv.index(k) + 1] if k in argv else d
    model, effort = opt("--model", "claude-opus-5-5"), opt("--effort", "medium")
    chunk, cap = int(opt("--chunk", "80")), float(opt("--cap", "60"))
    skip = {opt(k, None) for k in ("--model", "--effort", "--chunk", "--cap")}
    pats = [a for a in argv[2:] if not a.startswith("--") and a not in skip]
    tm = load_json(TM_PATH, {})
    requests, plan, prefilled = build_requests(worksheets(pats), model, effort, chunk, tm)
    chars = sum(len(r["params"]["messages"][0]["content"]) for r in requests) + 9000 * len(requests)
    estimate = chars * COST_PER_CHAR * (0.5 if "sonnet" in model else 1.0)
    spent = load_json(SPENT_PATH, {"total": 0.0, "batches": {}})["total"]
    items = sum(len(p["keys"]) for p in plan.values())
    print(f"{len(requests)} request(s), {items} entries, {prefilled} prefilled from memory")
    print(f"estimated cost ${estimate:.2f}; spent so far ${spent:.2f}; cap ${cap:.2f}")
    if "--dry-run" in argv or not requests:
        return 0
    if spent + estimate * 1.3 > cap:
        print("refusing: estimate with margin would exceed the cap")
        return 1
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    batch = client().messages.batches.create(requests=[
        Request(custom_id=r["custom_id"], params=MessageCreateParamsNonStreaming(**r["params"])) for r in requests])
    save_json(os.path.join(STATE_DIR, batch.id + ".json"),
              {"batch_id": batch.id, "model": model, "effort": effort, "created": time.time(), "plan": plan})
    print("submitted batch", batch.id, batch.processing_status)
    return 0


def cmd_status(argv):
    b = client().messages.batches.retrieve(argv[2])
    print(b.processing_status, dict(b.request_counts))


def cmd_collect(argv):
    bid = argv[2]
    state = load_json(os.path.join(STATE_DIR, bid + ".json"), None)
    c = client()
    b = c.messages.batches.retrieve(bid)
    if b.processing_status != "ended":
        print("not finished:", b.processing_status, dict(b.request_counts))
        return 1
    tm = load_json(TM_PATH, {})
    usage = {"in": 0, "cw": 0, "cr": 0, "out": 0}
    sheets, filled, problems = {}, 0, []
    for res in c.messages.batches.results(bid):
        plan = state["plan"].get(res.custom_id)
        if res.result.type != "succeeded":
            problems.append(f"{res.custom_id}: {res.result.type}")
            continue
        msg = res.result.message
        u = msg.usage
        usage["in"] += u.input_tokens or 0
        usage["cw"] += getattr(u, "cache_creation_input_tokens", 0) or 0
        usage["cr"] += getattr(u, "cache_read_input_tokens", 0) or 0
        usage["out"] += u.output_tokens or 0
        if msg.stop_reason != "end_turn":
            problems.append(f"{res.custom_id}: stop_reason {msg.stop_reason}")
            continue
        text = next((blk.text for blk in msg.content if blk.type == "text"), "")
        try:
            got = {t["key"]: t["en"] for t in json.loads(text)["translations"]}
        except (ValueError, KeyError) as ex:
            problems.append(f"{res.custom_id}: bad JSON ({ex})")
            continue
        path = os.path.join(REPO, plan["path"])
        ws = sheets.setdefault(path, json.load(open(path, encoding="utf-8")))
        bykey = {key_of(e): e for e in ws["strings"]}
        for k in plan["keys"]:
            en = got.get(k)
            if en is None:
                problems.append(f"{res.custom_id}: {k} missing")
                continue
            e = bykey[k]
            if not e.get("keep") and not e.get("en"):
                e["en"] = en.strip()
                e.pop("retry_note", None)
                tm[e["jp"]] = e["en"]
                filled += 1
    for path, ws in sheets.items():
        save_json(path, ws)
    save_json(TM_PATH, tm, indent=0)
    pr = PRICES.get(state["model"], PRICES["claude-opus-5-5"])
    cost = (usage["in"] * pr["in"] + usage["cw"] * pr["in"] * 1.25 + usage["cr"] * pr["in"] * 0.05
            + usage["out"] * pr["out"]) / 1e6
    sp = load_json(SPENT_PATH, {"total": 0.0, "batches": {}})
    if bid not in sp["batches"]:
        sp["batches"][bid] = round(cost, 4)
        sp["total"] = round(sum(sp["batches"].values()), 4)
        save_json(SPENT_PATH, sp)
    print(f"filled {filled} entries in {len(sheets)} worksheet(s)")
    print(f"tokens: input {usage['in']}, cache write {usage['cw']}, cache read {usage['cr']}, output {usage['out']}")
    print(f"cost: ${cost:.2f} ({state['model']}, batch); total spent ${sp['total']:.2f}")
    for p in problems:
        print("problem:", p)
    return 0


def check_entry(e):
    """Reasons the English breaks a build gate, or []."""
    en = e.get("en") or ""
    if not en or e.get("keep"):
        return []
    out = []
    try:
        game = ogg_text.wrap(en, keep_q="?" in e["jp"])
        game.encode("cp932")
    except Exception as ex:      # noqa: BLE001
        return [f"cannot encode ({ex})"]
    if e.get("kind") in ("desc", "battle"):     # wrapped by the build / the game: encoding only
        if e.get("kind") == "battle" and ("「" in en or "」" in en):
            out.append("brackets kept")
        return out
    if e.get("kind") in ("help", "help_line"):
        n = len(ogg_text.to_game(en).encode("cp932"))
        if e.get("size") and n >= e["size"]:
            out.append(f"{n} bytes, slot holds {e['size'] - 1}")
        # colour tags only need to be balanced (English may split or merge highlighted phrases);
        # icon/sprite tags (<I=n>, <S=n>) must all be kept, in order
        icons = lambda s: re.findall(r"<[IS]=-?\d+>", s)
        if icons(e["jp"]) != icons(en):
            out.append("icon tags differ from the Japanese")
        depth = 0
        for t in re.findall(r"<C=\d+>|</C>", en):
            depth += 1 if t != "</C>" else -1
            if depth not in (0, 1):
                break
        same_as_jp = re.findall(r"<C=\d+>|</C>", en) == re.findall(r"<C=\d+>|</C>", e["jp"])
        if depth != 0 and not same_as_jp:     # a few Japanese texts have stray </C> themselves
            out.append("unbalanced colour tags")
        rest = re.sub(r"<[A-Za-z/][^<>]*>", "", en)
        if "<" in rest or ">" in rest:
            out.append("stray < or >")
        return out
    if e.get("budget") is not None:     # executable string, replaced in place
        n = len(ogg_text.to_game(en, end_pair=False).encode("cp932"))
        if n > e["budget"]:
            out.append(f"{n} bytes over the in-place budget of {e['budget']}")
        if re.findall(r"%[-+0-9.]*[sdxXcuf]", e["jp"]) != re.findall(r"%[-+0-9.]*[sdxXcuf]", en):
            out.append("printf codes differ from the Japanese")
        return out
    rows = game.split("@")
    maxrows = 3 if e["kind"] in ("dialogue", "thought") else max(3, e["jp"].count("@") + 1)
    if len(rows) > maxrows:
        out.append(f"{len(rows)} rows (max {maxrows})")
    for r in rows:
        if len(r.encode("cp932")) > 60:
            out.append(f"row of {len(r.encode('cp932'))} bytes (max 60)")
    if re.findall(r"#\d\d|##", e["jp"]) != re.findall(r"#\d\d|##", en):
        out.append("colour codes differ from the Japanese")
    if re.search(r"[＀-￯]", en):
        out.append("full-width characters")
    if "@" in en or re.sub(r"<[^<>]*>", "", en).count("<") or re.sub(r"<[^<>]*>", "", en).count(">"):
        out.append("stray @ or < >")
    return out


def cmd_check(argv, clear=False):
    pats = argv[2:] or ["worksheets/MAP_14_*.json"]
    tm = load_json(TM_PATH, {})
    n = 0
    for path in worksheets(pats):
        ws = json.load(open(path, encoding="utf-8"))
        changed = False
        for e in ws["strings"]:
            why = check_entry(e)
            if not why:
                continue
            n += 1
            print(f"{os.path.basename(path)} {key_of(e)}: {'; '.join(why)} | {e['en'][:70]}")
            if clear:
                e["retry_note"] = f"{e['en']!r} failed: {'; '.join(why)}"
                tm.pop(e["jp"], None)
                e["en"] = ""
                changed = True
        if changed:
            save_json(path, ws)
    if clear:
        save_json(TM_PATH, tm, indent=0)
    print(f"{n} failing entr{'y' if n == 1 else 'ies'}" + (" cleared for re-translation" if clear else ""))
    return 1 if n and not clear else 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "submit":
        return cmd_submit(argv)
    if cmd == "status":
        return cmd_status(argv)
    if cmd == "collect":
        return cmd_collect(argv)
    if cmd == "check":
        return cmd_check(argv)
    if cmd == "retry":
        return cmd_check(argv, clear=True)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv) or 0)
