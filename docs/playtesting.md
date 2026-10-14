# Playtesting guide

Thanks for helping. This is a first public build: the whole game is translated, but **no
editing pass has been done**. The first translation was machine-assisted and only checked by
tools, so plenty of lines will read stiffly or get something wrong. That is exactly what we
want to hear about.

## What to look for

1. **Japanese left on screen**: text, labels or pictures.
2. **Layout**: text running past a box, overlapping a number or icon, or cut off.
3. **Names**: a character, unit, weapon or attack named differently in two places, or differently
   from the OGs / 2nd OG patches.
4. **Lines**: wrong meaning, wrong speaker voice, awkward English. A suggested rewrite helps a lot.
5. **Crashes or freezes**: note exactly what you did just before.

## How to report

Open an issue on GitHub, one problem per issue if you can (several related lines from one scene
can go together). Include:

- a screenshot (PCSX2: **F8**; the file goes to `Documents/PCSX2/snaps`),
- the stage number (Intermission screen, or the objective window on the map) or the menu path,
  for example *Intermission > Pilot List > Triangle (Stats) > Pilot Stats*,
- for dialogue: the line as shown, and your suggested English if you have one.

## Setup tips

- Use **PCSX2 2.x**. Upscaling is fine; the text is drawn by the game, not as a texture.
- Memory-card saves carry over between patch versions. Save states from an older version keep
  the old text loaded until the next screen change, so load a memory-card save after updating.
- The backlog (Triangle during dialogue) shows earlier lines, handy for screenshots of a line
  you skipped past.

## Style we are aiming for

- Names and terms follow the 2nd OG patch (see `glossary/`).
- Speech should sound like the character: Albero clipped and military, Kouta loud, and so on.
- Menus favour short words; many boxes are narrow, so abbreviations like *Sup. Atk.* are on
  purpose.
