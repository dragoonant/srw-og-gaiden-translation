# Rendering English in OG Gaiden

## How the game draws text

`FUN_0014fbe0` (ELF) is the main text drawer: dialogue and most UI text (97 call sites).
`FUN_0014e700` measures a string the same way (89 call sites). Other drawers exist
(`FUN_0014f6f0`, float version, 11 call sites in menus; `FUN_0014ed50`, `FUN_0014f230` in EXOL,
`FUN_001513c0`) and will need the same treatment as their screens are reached.

Per glyph, `FUN_0014fbe0`:
1. reads two bytes (Shift-JIS; there is **no 1-byte path**, which is why plain ASCII shows
   garbage);
2. sets the advance `$s1` = font size (20) and, if the flag at font+0x40 is set, narrows it
   (digits 12/20, other non-kanji 14/20);
3. gets the glyph's UVs (`FUN_0014e1b0`) and uploads a 64-byte palette chosen by the lead byte
   (`FUN_00150f20`; the font packs 1-bit glyph planes into a 4-bit texture);
4. draws one sprite (`FUN_001501b0`) with quad `x .. x+$s1` and texture **U0 = `$fp`,
   U1 = `0xE0($sp)`** (absolute U, not a width), V0 = 0, V1 = 0x12.

Glyph cells are 18 px wide; the font is 20 px (advance 20 in monospace). The dialogue box
holds three rows of about 440 px. Rows are split at `@` by the script; the drawer never wraps.

## The patch (`tools/vwf_patch.py`)

English is stored as **full-width** Shift-JIS (`Ａ`..`ｚ`, `０`..`９`, `、。！？` etc.), which the font
already has. The drawer's flag test at 0x14FCB4 jumps to a routine in a code cave (0x13CB58,
see below) that looks codes 0x8140–0x819F and 0x8240–0x829F up in a width table:
advance = ink width + 2 px, U0 = left bearing, U1 = left + advance (clipped to the cell, with
the advance shrunk to match so nothing is scaled). Other codes take the original path.

The table comes from `data/glyph_ink.json`: each glyph's first and last ink column, measured
in game by `tools/glyph_shots.py` (monospace rows, native-resolution screenshots).

Verified live on 2026-10-12 (PINE patch on the running game): proportional English with
correct glyph shapes. Notes:
- The font has no `＂` or `＇`: the build must use `”`/`“` and `’`/`‘`.
- `FUN_0014e700` (measure) still uses the old widths; patch it the same way before relying on
  centring or the drawer's squeeze-to-fit path.
- The backlog and battle text use their own paths; check each.

## Byte cost

Two bytes per English character. A dialogue row buffer is 0x80 bytes (63 glyphs + NUL); a
440 px row holds about 40–45 proportional characters, so rows fit. Script strings grow, but
LOGO pools are rebuilt freely. Fixed-size buffers (backlog, names, data tables) need byte
budgets in `fitcheck`.

## Backlog finding and the next design step (2026-10-12)

The backlog opens without crashing on our pilot build, but it stores each line as a record
every 0xCC bytes (12-byte header + 192 bytes of text) and copies **at most 64 bytes (32 glyphs)
per row**. Full-width English (2 bytes per letter) loses words there ("...all units. your
status."). Fixed-size name fields in the data tables will have the same problem.

Next step: store English as **1-byte ASCII** in the data. The engine already treats bytes
below 0x80 as single characters (`@` row breaks and `<tag>` brackets live inside Shift-JIS
text, and `FUN_0014e700` has a 1-byte path); only the drawer needs 2 bytes. Plan: hook the
drawer's `strlen` call at 0x14FC78 with a cave routine that copies the string to a scratch
buffer (unreferenced `0x13CDD0`, 1,240 bytes), turning ASCII into full-width codes, and points
`$s4` at the copy. The width table then applies unchanged. Patch `FUN_0014e700` to use the
same widths. Repaint the Latin glyphs in the font texture with an open-licensed font (the
game's own full-width Latin is a placeholder).

## 1-byte English: done and verified (2026-10-12)

- `vwf_patch.py` now also hooks the drawer's `strlen` call (0x14FC78) with `CONV` in cave 2
  (0x13CDD0): ASCII is copied to a buffer as full-width codes, multi-byte characters are copied
  as they are, and the drawer reads the copy.
- English is stored as ASCII (`ogg_text.to_game`); only ’ “ ” ― are 2-byte.
- **Pair alignment rule** (found in the backlog): engine text scanners consume 1 byte for
  `@`, `<`, `>` and 2 bytes for anything else. So every `@`, `<`, `>` and 2-byte character must
  sit at an even offset counted from the previous `@`/`<`/`>` (or the string start).
  `ogg_text.align_pairs` widens the preceding ASCII letter to its full-width twin when needed
  (drawn identically).
- Verified in PCSX2 on the stage 1 pilot: dialogue, keyword tag line, and the backlog all show
  complete lines with correct breaks. Build gates: 3 rows, 60 bytes per row.

## Code cave (2026-10-12, corrected)

All patch code and tables live in **0x13CB58-0x13D2A8** (1,868 bytes): `FUN_0013cb58` and
`FUN_0013cdd0`, two adjacent GS texture-upload helpers that nothing reaches: no `jal`, no `j`,
no branch, no stored pointer and no `lui`/`addiu` pair in the ELF, any overlay or a RAM dump.

The first choice, `acosf` at 0x11EDE8, had no `jal` or pointer but **is tail-called by
`j 0x11EDE8` at 0x122F94**; overwriting it froze the game at the start of the map phase (the
camera uses it). Any cave check must include `j` tail calls and branches, then a play test
past the first map load.

Layout: width hook 0x13CB58, measure 0x13CBE8, converter 0x13CCC0, ASCII table 0x13CD60,
width table 0x13CE20, scratch buffer 0x13CFA0 (772 bytes). Debug switches for bisecting:
`VWF_NO_MEASURE=1`, `VWF_NO_CONV=1`; `build_ogg.py --only map,elf,font`.

Verified 2026-10-12: stage 1 pilot plays from the opening dialogue into the player phase
(HUD, unit names with repainted Latin glyphs).

## Status-screen findings (2026-10-13)

- **Number drawers.** `FUN_0014ed50` (float x) and `FUN_0014f230` (int x) draw 1-byte strings
  (numbers, `%`, `Lv`) through the ASCII table at 0x2B1FE0, squeezing digits into 12/20 cells.
  Both are hooked at their flag tests (0x14EE4C, 0x14F328) and use the width table.
- **Measure and colour codes.** The replacement measure skips `#NN` and `##`; counting them as
  glyphs made coloured strings measure far too wide, so squeeze-to-fit crushed them. The integer
  measure is now a wrapper around the float one, which is the one place the logic lives.
- **Row routine `FUN_0016f620`.** It reads text in 2-byte units, and `#`, `+`, `&` and `/` are
  control codes only at even offsets. Every unit is drawn as one glyph, so a row built from
  ASCII pairs fails; the spirit legend rows are blanked for that reason. This is also why an
  ASCII `+` broke lines.
- **Finding a caller live.** `calllog`: point the function's first two instructions at a stub
  that saves `$ra` into a ring in the converter buffer, read the ring over PINE, then put the
  instructions back. That is how the spirit-name draw (W1OL 0x591CBC) was found.
- **One-character strings.** The extractor skipped them, and `Lv` formats such as `%sＬ%s` and
  `L%d` too. The 2026-10-13 sweep added them. Worksheet entries can set `en_raw` (exact bytes)
  where the converter's pairing must not apply.
