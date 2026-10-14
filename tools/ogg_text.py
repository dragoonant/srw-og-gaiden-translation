"""English text for OG Gaiden: worksheet text -> game bytes, and pixel widths.

English is stored as 1-byte ASCII (half the bytes of full-width, so it fits the backlog's
64-byte rows and fixed name fields). The vwf_patch converter turns ASCII into full-width
codes just before drawing, and the width table spaces them proportionally.

  - letters, digits, punctuation, space  -> kept as ASCII
  - ' and "                              -> ’ and “ ” (2-byte; the font has no straight quotes)
  - --                                   -> ―
  - newline                              -> @ (the script's row break)
  - < >                                  -> keyword tags like <Super Robot>, parsed by the engine
"""
import json
import re
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
ROW_PX = 440          # usable width of a dialogue row
DEFAULT_ADV = 20      # glyphs without a table entry draw at the font size

_adv = None
EXTRA_LETTERS = {"ä": "¢", "ö": "£", "ü": "§", "Ä": "¨", "Ü": "´", "é": "℃"}


def advances():
    global _adv
    if _adv is None:
        import sys
        sys.path.insert(0, _HERE)
        import vwf_patch
        tab = vwf_patch.table()
        _adv = {}
        for idx in range(192):
            if tab[2 * idx]:
                ch = bytes([0x81 + idx // 0x60, 0x40 + idx % 0x60]).decode("cp932")
                _adv[ch] = tab[2 * idx]
    return _adv


def to_game(text, end_pair=True, keep_q=False):
    """Worksheet English -> the Unicode string the game should get (encode with cp932).
    end_pair: also put the terminating NUL on a pair boundary (costs a byte on odd lengths;
    in-place UI strings drop it when the slot is full).
    keep_q: keep ASCII '?' (the engine's number placeholder, as in ・?ターン以内に...); otherwise
    question marks are written full-width, as the Japanese does (an ASCII '?' in a map-phase
    message became '0' and threw the row breaks off)."""
    out = []
    dq_open = True
    i = 0
    while i < len(text):
        c = text[i]
        if text.startswith("--", i):
            out.append("―")
            i += 2
            continue
        if c == "\n":
            out.append("@")
        elif c in EXTRA_LETTERS:
            out.append(EXTRA_LETTERS[c])   # umlauts drawn in spare symbol cells (font_latin.EXTRA)
        elif c == "?" and not keep_q:
            out.append("？")
        elif c == "'":
            out.append("’")
        elif c == '"':
            out.append("“" if dq_open else "”")
            dq_open = not dq_open
        else:
            out.append(c)          # ASCII, or already a game character (…, ’, Japanese)
        i += 1
    return align_pairs("".join(out), end_pair)


def align_pairs(s, end_pair=True):
    """Some engine routines (the backlog, the row splitter) scan text in 2-byte steps, so a
    row break, tag bracket or 2-byte character must start at an even byte offset counted from
    the previous @, < or > (the scanner steps 1 byte over those). When one would land on an odd
    offset, store the ASCII character before it as its full-width twin (drawn the same)."""
    out = []
    pos = 0
    # tokens the scanner steps over as a unit: @ < > and the colour codes #NN / ##
    # (a lone # is the line break in help text, ## an empty line or the colour reset)
    for tok in re.findall(r"#\d\d|##|.", s, re.S):
        special = tok in "@<>#" or tok.startswith("#") and len(tok) == 3 or tok == "##"
        n = len(tok.encode("cp932"))
        if (n == 2 and not special or special) and pos % 2 == 1:
            prev = out[-1]
            assert len(prev.encode("cp932")) == 1, "odd offset after a 2-byte char"
            out[-1] = _drawn(prev)
            pos += 1
        out.append(tok)
        pos = 0 if special else pos + n   # the scanner takes specials as a unit, 2 bytes otherwise
    if end_pair and pos % 2 == 1 and out:
        # the terminating NUL must sit on a pair boundary too, or 2-byte copy loops step over it
        out[-1] = _drawn(out[-1])
    return "".join(out)


def _drawn(ch):
    """The full-width character the converter draws for a stored character."""
    if ch == " ":
        return "　"
    if "!" <= ch <= "~":
        return chr(ord(ch) + 0xFEE0)
    return ch


def row_widths(game_text):
    """Pixel width of each row of a game string (tags count by their inner text)."""
    return [width(row) for row in game_text.split("@")]


def width(game_text):
    adv = advances()
    game_text = re.sub(r"#\d\d|##", "", game_text)     # colour codes are not drawn
    return sum(adv.get(_drawn(ch), DEFAULT_ADV) for ch in game_text if ch not in "<>")


def wrap(text, row_px=ROW_PX, keep_q=False):
    """Greedy word wrap of worksheet English to rows of row_px; explicit newlines kept.
    Returns the game string (rows joined with @)."""
    return to_game("\n".join(split_rows(text, row_px)), keep_q=keep_q)   # one pass: “ ” pair up


def wrap_rows(text, row_px, end_pair=True):
    """Like wrap, but returns separate game strings (one per display line), each aligned on
    its own: for tables that store every line as its own NUL-terminated string."""
    return [to_game(r, end_pair) for r in split_rows(text, row_px, max_bytes=10 ** 6)]


MAX_ROW_BYTES = 60     # the backlog copies at most 64 bytes per row


def row_bytes(text):
    return len(to_game(text).encode("cp932"))


def split_rows(text, row_px, max_bytes=MAX_ROW_BYTES):
    """Greedy word wrap of worksheet English into rows (still worksheet text): a row ends when
    the next word would pass row_px pixels or max_bytes stored bytes."""
    rows = []
    space = width(to_game(" "))
    for para in text.split("\n"):
        cur, cur_w = [], 0
        for word in para.split(" "):
            w = width(to_game(word))
            if cur and (cur_w + space + w > row_px or row_bytes(" ".join(cur + [word])) > max_bytes):
                rows.append(" ".join(cur))
                cur, cur_w = [word], w
            else:
                cur_w += (space if cur else 0) + w
                cur.append(word)
        rows.append(" ".join(cur))
    return rows


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, _HERE)
    s = " ".join(sys.argv[1:]).replace("\\n", "\n")
    g = wrap(s)
    print(g, row_widths(g), len(g.encode("cp932")), "bytes")
