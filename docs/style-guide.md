# Style guide: OG Gaiden (draft for evilgouki's review)

Carried over from the 2nd OG patch so the two read as one series; engine rules adapted for
OG Gaiden (PS2).

Sources: engine tests in `docs/rendering.md`, the OGs PS2 fan patch text
(decoded from `ogs.xdelta`), the camd11 OG Gaiden patch as observed in
`glossary/sources.md`, and the glossary. Items marked
**decide** need evilgouki's call.

## Hard rules (OG Gaiden engine; `tools/build_ogg.py` checks them)

- Plain ASCII English. The build turns it into the game's characters, converts ' and "
  into curly quotes, and word-wraps dialogue to the box (3 rows of about 42 characters).
- Do not type `@` (the row break) or ASCII `<` `>` except inside keyword tags. Keyword
  tags like `<特機>` stay tags with the English inside: `<Super Robot>`.
- Keep colour codes exactly: `#16` before and `##` after a highlighted item name, e.g.
  `#16Repair Kit## obtained.` Keep `?` placeholders where the Japanese has them.
- Dialogue: one paragraph, no manual line breaks; at most 115 characters including the
  speaker prefix. Lists (objectives, item messages) keep one line per Japanese line.
- Strings marked `keep` stay Japanese (engine labels, placeholders).
- No full-width Latin letters or digits in the English.

## Names and terms

- Basis: the English of the OGs PS2 fan patch, checked against Akurasu.
  `glossary/signoff.tsv` holds every data-table name with both forms;
  `deviations.md` lists where they disagree for evilgouki to decide. The build
  fails on a non-canonical form of a signed-off term.
- Given name first ("Masaki Andoh"). OG Gaiden writes the speaker inside the line
  (アルベロ「…」); the English is `Albero: ...` with the short name the game uses.
  ？？？ becomes `???`.
- Units: Title Case, model codes as written (`R-1`, `MP Gespenst Mk-II`).
- Attacks: Title Case, hyphenated prefixes (`T-Link Knuckle`). Translate
  Japanese-word attack names unless the canon keeps the romanization
  (`Shishioh Blade`, `Bakuraifu`).
- Spirit commands: canon names (Valor, Flash, Focus, ...). Where a menu has
  4-letter slots, use the canon abbreviations once the width check shows
  which menus need them.

## Dialogue

- Honorifics: none. Decided from the OGs patch, which has no -san, -kun,
  -chan or -sama in 53,168 dialogue lines. The one exception it keeps is
  "Rishu-sensei"; keep that where the Japanese has it. Ranks are written in
  full ("Captain", "Lieutenant", "Commander"), never "Lt.", plus "sir".
- Japanese quote brackets: spoken lines get no quotation marks (the `Name:` prefix
  shows the speaker); inner thoughts （…） stay in parentheses: `Hugo: (These things...)`. Decided from
  the OGs patch, which writes "Aya: Hey! It's that unit again!" and
  "Ryusei: (If I just had some better air...". Also saves two characters of
  width per line.
- Register: natural, contraction-heavy English. Keep each character's voice:
  Masaki brash, Shu cool and formal, Ryusei excited, Kyosuke terse,
  Excellen playful. Per-character notes grow in this file as the edit pass
  goes on.
- Ellipsis `...` (three periods, cheaper than `…` at current widths), em-dash
  as `--`, exclamation and question marks single unless the Japanese stacks
  them for effect (`!!` allowed, never more).
- Leave gender unspecified where the Japanese does (battle quotes aimed at
  "the enemy pilot").

## UI

- Menu labels in Title Case, status banners in ALL CAPS, stat labels
  abbreviated as in the OGG patch (Mob, Mel, Skl, Rng, Def, Acc, Eva).
- Victory and defeat conditions numbered as in the Japanese ("1. Destroy all
  enemies.").
- Empty slots stay as the Japanese dash runs.

## Battle quotes

- Short and punchy. 26,050 unique lines are reused across pilots, so keep a
  line neutral when the same Japanese serves several speakers.
- The `/` + U+3000 break must survive; at most 3 lines.
