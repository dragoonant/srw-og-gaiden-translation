# Super Robot Taisen OG Gaiden: English translation

An English translation patch for *Super Robot Taisen OG Gaiden* (PlayStation 2, 2007,
SLPS-25836), by **evilgouki**. It follows the team's *2nd Super Robot Wars OG* patch, so the two
read as one series: same names, same style.

> **Status: v0.1, public playtest.** All game text is translated and the patch plays from the
> title screen through the stages we have tested. **No editing pass has been done.** The first
> translation was machine-assisted (AI) and checked automatically for fit, line breaks and
> consistent names, but no human has read the script end to end. Expect awkward lines,
> occasional mistranslations and inconsistent terms. Reports are very welcome; see
> [Reporting problems](#reporting-problems).

## What's translated

| Part | Entries |
|---|---|
| Story and stage scripts (all 43) | 20,613 |
| Battle quotes (341 pilots) | 48,121 |
| Unit, weapon, pilot, skill and part names | 3,847 |
| Database and help descriptions | 4,395 |
| Tutorials and help pages | 2,450 |
| Menus and system messages | ~4,100 |
| Terrain names | 150 |

Picture text is English too: title logo, warning screen, menu titles, map and battle labels,
command badges, Special Disk menus, and the Shuffle Battler card art and labels.

English is drawn with a proportional font (Fira Sans) through a small patch to the game's text
renderer. The backlog (Triangle) works. Terrain ranks use small icons (cloud, mountains, waves,
planet) in place of the kanji.

## How to apply

You need your own copy of the Japanese disc as an ISO, matching:

| | |
|---|---|
| Size | 4,666,294,272 bytes |
| MD5 | `cb7dc4485f46f220c46095c966a3aad0` |
| SHA-1 | `2891231bc85603d420c35cda55285d5ecb781f1b` |

Download the `.xdelta` file from [Releases](../../releases) and apply it with
[xdelta UI](https://www.romhacking.net/utilities/598/), Delta Patcher, or xdelta3:

```
xdelta3 -d -s "Super Robot Taisen - Original Generation Gaiden [J].iso" OG_Gaiden_EN_v0.1.xdelta OG_Gaiden_EN_v0.1.iso
```

Play the patched ISO in **PCSX2** (tested with 2.8.2). Real PS2 hardware has not been tested.
Start a new game or load a memory-card save. Save states from other versions of the patch keep
the old text loaded until the next screen change, so prefer memory-card saves when updating.

## Known issues

- **No editing pass** (see above).
- Names of units, weapons and characters that are new to OG Gaiden are proposals and may change.
  The ability names unique to Shuffle Battler (Gale, Decoy, Deathblow ...) are ours.
- Still in Japanese: the Shuffle Battler gallery card sheets, and eight Shuffle Battler unit
  cards whose art is a battle screenshot with a dialogue window in it.
- Shuffle Battler has only been checked in previews, not played.
- Most of the game past the opening stages has only been checked by tools, not played. Some
  screens may still have overlapping or clipped text.

## Reporting problems

Open an [issue](../../issues) with:

- a screenshot (PCSX2: F8 saves one),
- where you are: stage number (shown on the Intermission screen and the objective window) or
  the menu path,
- what is wrong: untranslated text, clipped or overlapping text, a wrong name, a bad line.

Suggested rewrites of lines are just as welcome. See [docs/playtesting.md](docs/playtesting.md).

## Building from source

The repository holds the tools, the English text and the glossary, but **no game data and no
Japanese text**. To build an ISO yourself:

1. Python 3.12 with Pillow, NumPy and `opencv-python-headless`.
2. Extract your disc: `python tools/iso_tool.py extract YOUR.iso ~/srwogg-work/ext`
3. Put the Japanese source text back into the worksheets from your disc:
   `python tools/hydrate.py fill`
4. Fonts: Fira Sans and Fira Sans Condensed (SIL OFL) in `~/srwogg-work/fonts`.
5. `python tools/build_ogg.py --iso OUT.iso` (the original ISO next to the repo, or set the path
   in `tools/build_ogg.py`).

The English title logo is built from `~/srwogg-work/assets/title_logo_src.webp`, which is not in
the repository; without it the Japanese logo is kept. See [docs/](docs/) for the file formats
and the renderer patch.

## Credits

- **evilgouki**: project lead, translation direction, title logo, testing.
- Tools and AI-assisted first translation pass: built for this project (see `tools/`).
- Font: Fira Sans (SIL Open Font License, `data/FONT-LICENSE-FiraSans-OFL.txt`).
- Names follow the community canon of the OGs and 2nd OG fan patches; English terms researched
  on the [Akurasu wiki](https://akurasu.net/wiki/Super_Robot_Wars) (see `glossary/sources.md`).

## License

The tools and documentation in this repository are MIT licensed (`LICENSE`). The game, its
text and its data belong to their owners; this repository contains no game data.
