# OG Gaiden (SLPS-25836) file formats

Everything here was confirmed on our own dump. Tools are named per section.

## Disc (`tools/iso_tool.py`)

Plain ISO9660, 35 files. `iso_tool.py write` replaces a file in place (same LBA), so a patched
image stays a drop-in replacement as long as each file fits its sectors.

| Path | Size | Content |
|---|---|---|
| `SLPS_258.36` | 2.1 MB | Boot ELF (MIPS R5900) |
| `OL/*.BIN` (7) | 0.35–1.0 MB | Code overlays, magic `MWo3` |
| `IRX/*` | | IOP modules (keep) |
| `DATA/MAP.BIN` | 155 MB | LICE: stage data; **entry 14 = story scripts (LOGO)** |
| `DATA/BATTLE.BIN` | 1.8 GB | LICE: battle data; entry 5 holds battle quotes |
| `DATA/GRAPHIC.BIN` | 185 MB | LICE: graphics |
| `DATA/SHARED.BIN`, `DATA/IM.BIN` | 2.4 MB | LICE: tables, help text (entry 8/4 = tutorial/help pages) |
| `DATA/WINDOW.BIN` | 1.4 MB | LICE: windows |
| `DATA_SP/*.BIN` | | LICE: special mode (Shuffle Battler etc.) |
| `DATA/SQ2.BIN` | 231 MB | Sound (`IECSsreV`) |
| `DATA/STRM.BIN`, `DATA/PSS.BIN` | | Audio streams, movies |

## LICE container (`tools/lice.py`)

```
0x00 "LICE"
0x04 u32 header size H (0x800, 0x1000, 0x1800, 0x2800, ...)
0x08 u32 entry count N
0x0C u32 id count M
0x10 u16[M] entry index per id (0xFFFF = none); rest of the header 0xFF
H    "Wpbb" u32 N, then N x (u32 offset, u32 size), offsets relative to H
```
Entries nest (a LICE inside a LICE). All 11 containers rebuild byte-identical.

## LOGO stage script (`tools/script.py`)

Same layout as 2nd OG's LOGO, but **little-endian and Shift-JIS**. `script.py` picks the
profile per file. 43 files (`MAP.BIN` 14/0..42), 20,721 strings, all round-trip byte-identical.

- Pool A is empty; pool B holds every string.
- Dialogue strings: `Speaker「body」`, speaker inline (no name box). Line break `@　`
  (`@` + U+3000). Each file opens with labels (`S0_00_00_00`), placeholder `エラー` lines and the
  shared defeat quotes, then the stage's own scenes.
- File 0 is the quit/end message chat (Kusuha and Brit); files 1–12 and 13–42 look like two
  scenario sets. Stage 1 (Albero's opening) is most likely file 1 or file 4.

## Overlays (`OL/*.BIN`, magic `MWo3`)

Header: `MWo3`, u32 id, u32 load address, u32 text size, u32 data size, u32 bss size, ...,
name at 0x20. The **whole file, header included, loads at the load address** (file offset =
address − base). During story dialogue on the map, MPOL (0x422000), MMOL (0x4E7D00) and
W1OL (0x576B80) are resident.

## Dialogue at runtime (from a RAM dump at Albero's first line)

- The stage script (LOGO) is loaded around 0x1080000.
- The current line is split at `@` into rows of 0x80 bytes. Two copies exist: 0x87D340
  (not drawn) and **0xE29044 + 0x80·row (drawn live every frame**: writing bytes there over
  PINE changes the screen at once).
- Shift-JIS glyph lookups live in the ELF at 0x14E000–0x152000: read two bytes, `(b0<<8)|b1`,
  range checks against 0x824F/0x8259 (digits), 0x989F (kanji level 2), etc.

## Rendering (first test, 2026-10-12)

Same-length ASCII bodies in every story line (ISO patched in place): the opening Albero line
showed our text as **garbage glyphs**. The dialogue renderer reads 2 bytes per glyph, so ASCII
needs a renderer patch (or full-width Latin cells). The font does have full-width Latin
(system messages show `ＯＲＩＧＩＮＡＬ ＧＥＮＥＲＡＴＩＯＮＳ`).

## Data tables: Vers/Fixh (`tools/fixh_ogg.py`)

SHARED.BIN and IM.BIN leaf (3,0), two slightly different versions. `Vers` header, then `Fixh`
with 29 absolute table offsets. Each table: tag, byte size, count, ...; 4-byte aligned, zero
padding. Text tables:
- `Strg` (2,043 / 1,806): every short name (units, weapons, pilots, skills, episode titles,
  specs). u32 offsets at +12 relative to the tag, then NUL-terminated Shift-JIS.
- `Sent` (5,200): description display lines, same layout.
- `Expl` (2,337): offsets to records `u16 n, u16 sent_index[n]` (a description's lines).
Unit/Weap/Plot/KeyW/... reference these by index. cp932 maps some IBM/NEC duplicate kanji to
one character, so untouched strings are written back from their raw bytes.

## Help text (`tools/help_ogg.py`)

- SHARED/IM leaves 8/1-8/3: 128-byte slots; 8/4: 2,048-byte slots (tutorial pages).
  `#` = line break, `<C=n>...</C>` = colour.
- Leaves 10/0-54: help pages (3,976 bytes each) in layout markup
  `<X=..><Y=..><W=..><H=..>text</H></W></Y></X>` joined by `#`.

## Executable strings (`tools/strtab_ogg.py`)

NUL-terminated Shift-JIS on 4-byte boundaries in the ELF and overlays; a string's budget is its
slot up to the next non-zero byte. About 4,050 real strings after a plausibility filter (code
bytes that decode as Shift-JIS are rejected). Replaced in place.

## Battle quotes (`tools/battle_ogg.py`)

BATTLE.BIN entry 5: 341 files (one per pilot). Header u16[16] section offsets; `h[13]..h[14]`
u16 offsets into the string pool (one per quote slot), `h[14]..h[15]` (u16 quote id, u16 1)
per slot, `h[15]..` the pool of `「...」` strings. 48,128 slots, 21,496 unique strings. No `@`
breaks: the battle window wraps by itself (Japanese lines run to 47 characters).
BATTLE.BIN has 27.8 MB of root slack; `lice.write_top_level` streams a rebuilt top-level
container into the image without loading 1.8 GB.
