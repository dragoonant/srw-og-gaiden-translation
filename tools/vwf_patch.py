"""Proportional (variable-width) English in the main text drawer.

The game draws text with FUN_0014fbe0 (dialogue and most UI). Per glyph it advances a fixed
20 px; a flag at font+0x40 enables a crude 14/20 mode. This patch sends every glyph through a
small routine in a code cave that looks codes 0x8140-0x819F and 0x8240-0x829F up in a width
table (advance, left bearing). For a hit it sets:
  $s1         advance = sprite quad width
  0xE0($sp)   texture U end = left + advance (kept inside the 18 px glyph cell)
  $fp         texture U start = left bearing
and otherwise returns to the original code, so Japanese text is unchanged.

The code lives in a cave at 0x13CB58 (see CAVE below).

  vwf_patch.py table                       print the width table
  vwf_patch.py live                        patch the running game over PINE
  vwf_patch.py unlive                      undo the live patch
  vwf_patch.py elf <in.elf> <out.elf>      patch an ELF file

Every original word is asserted before writing.
"""
import json
import os
import struct
import sys

ELF_BASE, ELF_OFF = 0x100000, 0x180          # file offset = addr - base + off (segment 0)
# One code cave: FUN_0013cb58 + FUN_0013cdd0, two adjacent GS upload helpers that nothing calls
# (no jal, j, branch, stored pointer or lui/addiu pair in the ELF, any overlay or a RAM dump).
# NOTE: acosf at 0x11EDE8 looked unused but is tail-called (j) from 0x122F94; using it hung
# the game at the start of the map phase.
CAVE = 0x13CB58
CAVE_LEN = 0x13D2A8 - 0x13CB58               # 1,868 bytes
CODE = CAVE                                   # width hook, 36 words
TABLE = 0x13CE20                              # 192 x (advance, U start)
HOOK = 0x14FCB4                               # beqz $v0, 0x14fd58  (flag test)
HOOK_ORIG = 0x10400028
RET_PLAIN = 0x14FD58                          # after the proportional block
RET_PROP = 0x14FCBC                           # original proportional block
CELL = 18                                     # glyph cell width in the font texture
GAP = 2
SPACE = 6                                     # advance of the full-width space

# Per-glyph [U start, advance] for the repainted Latin font (font_latin.py apply). Falls back to
# ink extents of the original glyphs measured in game (glyph_shots.py) if absent.
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
METRICS = os.path.join(DATA, "glyph_metrics.json")
INK = os.path.join(DATA, "glyph_ink.json")

# MIPS encoders (only what the routine needs)
R = dict(zero=0, at=1, v0=2, v1=3, a0=4, a1=5, a2=6, a3=7, t0=8, t1=9, t2=10, t3=11,
         sp=29, fp=30, ra=31, s1=17, s2=18, s4=20, s5=21)


def i_type(op, rs, rt, imm):
    return (op << 26) | (R[rs] << 21) | (R[rt] << 16) | (imm & 0xFFFF)


def lbu(rt, off, rs): return i_type(0x24, rs, rt, off)
def lw(rt, off, rs): return i_type(0x23, rs, rt, off)
def sw(rt, off, rs): return i_type(0x2B, rs, rt, off)
def addiu(rt, rs, imm): return i_type(0x09, rs, rt, imm)
def sltiu(rt, rs, imm): return i_type(0x0B, rs, rt, imm)
def lui(rt, imm): return i_type(0x0F, "zero", rt, imm)
def sll(rd, rt, sa): return (R[rt] << 16) | (R[rd] << 11) | (sa << 6)
def addu(rd, rs, rt): return (R[rs] << 21) | (R[rt] << 16) | (R[rd] << 11) | 0x21
def j(target): return (0x02 << 26) | ((target >> 2) & 0x3FFFFFF)
NOP = 0


def _rel(pc, target):
    off = (target - pc - 4) >> 2
    assert -0x8000 <= off < 0x8000, f"branch at {pc:#x} to {target:#x} out of range"
    return off


def beq(rs, rt, pc, target): return i_type(0x04, rs, rt, _rel(pc, target))
def bne(rs, rt, pc, target): return i_type(0x05, rs, rt, _rel(pc, target))
def sltu(rd, rs, rt): return (R[rs] << 21) | (R[rt] << 16) | (R[rd] << 11) | 0x2B
def sb(rt, off, rs): return i_type(0x28, rs, rt, off)
def bltz(rs, pc, target): return (0x01 << 26) | (R[rs] << 21) | (_rel(pc, target) & 0xFFFF)
def b(pc, target): return beq("zero", "zero", pc, target)
def jal(target): return (0x03 << 26) | ((target >> 2) & 0x3FFFFFF)
def jr(rs): return (R[rs] << 21) | 0x08
def lwc1(ft, off, rs): return i_type(0x31, rs, "zero", off) | (ft << 16)
def cvt_w_s(fd, fs): return 0x46000024 | (fs << 11) | (fd << 6)
def mfc1(rt, fs): return 0x44000000 | (R[rt] << 16) | (fs << 11)
def mtc1_w(fs, rt): return 0x44800000 | (R[rt] << 16) | (fs << 11)
def cvt_s_w(fd, fs): return 0x46800020 | (fs << 11) | (fd << 6)


def hi_lo(addr):
    lo = addr & 0xFFFF
    return ((addr + 0x8000) >> 16) & 0xFFFF, lo - 0x10000 if lo >= 0x8000 else lo


def routine():
    """Assemble the cave routine; returns list of words."""
    hi, lo = hi_lo(TABLE)
    # labels are word indices; branches patched after layout
    prog = [
        ("lbu", lambda pc: lbu("v1", 0, "s4")),           # 0 lead byte
        ("lbu", lambda pc: lbu("a0", 1, "s4")),           # 1 trail byte
        ("", lambda pc: addiu("v1", "v1", -0x81)),        # 2 lead - 0x81
        ("", lambda pc: sltiu("at", "v1", 2)),            # 3 lead in 0x81..0x82?
        ("", lambda pc: beq("at", "zero", pc, L["miss"])),
        ("", lambda pc: addiu("a0", "a0", -0x40)),        # 5 (delay) trail - 0x40
        ("", lambda pc: sltiu("at", "a0", 0x60)),         # 6 trail in 0x40..0x9F?
        ("", lambda pc: beq("at", "zero", pc, L["miss"])),
        ("", lambda pc: sll("v0", "v1", 5)),              # 8 (delay) lead*32
        ("", lambda pc: sll("v1", "v1", 6)),              # 9 lead*64
        ("", lambda pc: addu("v1", "v1", "v0")),          # 10 lead*0x60
        ("", lambda pc: addu("v1", "v1", "a0")),          # 11 + trail
        ("", lambda pc: sll("v1", "v1", 1)),              # 12 *2 bytes
        ("", lambda pc: lui("v0", hi)),                   # 13
        ("", lambda pc: addu("v0", "v0", "v1")),          # 14
        ("", lambda pc: lbu("a0", lo, "v0")),             # 15 advance
        ("", lambda pc: beq("a0", "zero", pc, L["miss"])),
        ("", lambda pc: lbu("v1", lo + 1, "v0")),         # 17 (delay) left bearing
        ("", lambda pc: addu("s1", "a0", "zero")),        # 18 advance -> $s1 (quad width)
        ("", lambda pc: addiu("v0", "zero", CELL)),       # 19
        ("", lambda pc: addu("a1", "v1", "a0")),          # 20 U end = left + adv
        ("", lambda pc: sltu("at", "v0", "a1")),          # 21 past the cell?
        ("", lambda pc: beq("at", "zero", pc, L["fits"])),
        ("", lambda pc: NOP),                             # 23
        ("", lambda pc: addu("a1", "v0", "zero")),        # 24 U end = CELL
        ("", lambda pc: (R["v0"] << 21) | (R["v1"] << 16) | (R["s1"] << 11) | 0x23),  # 25 subu s1, v0, v1: adv = CELL - left
        ("fits", lambda pc: sw("a1", 0xE0, "sp")),        # 26 U end (the drawer passes it as the sprite's U1)
        ("", lambda pc: j(RET_PLAIN)),                    # 27
        ("", lambda pc: addu("fp", "v1", "zero")),        # 28 (delay) crop offset = left
        ("miss", lambda pc: lw("v0", 0x40, "s5")),        # 29 original flag test
        ("", lambda pc: beq("v0", "zero", pc, L["plain"])),
        ("", lambda pc: NOP),                             # 31
        ("", lambda pc: j(RET_PROP)),                     # 32 flag set: original 14/20 block
        ("", lambda pc: NOP),                             # 33
        ("plain", lambda pc: j(RET_PLAIN)),               # 34
        ("", lambda pc: NOP),                             # 35
    ]
    global L
    L = {name: CODE + 4 * k for k, (name, _) in enumerate(prog) if name not in ("", "lbu")}
    return [f(CODE + 4 * k) for k, (_, f) in enumerate(prog)]


# ---------------------------------------------------------------- ASCII -> full-width

# English is stored as 1-byte ASCII (the engine's text handling already accepts bytes below
# 0x80; only this drawer needs 2-byte codes). The drawer's strlen call is redirected to CONV,
# which copies the string to BUF with ASCII turned into full-width codes, points $s4 at the
# copy and tail-calls strlen.
CONV = 0x13CCC0
A2S = 0x13CD60                                # 96 x u16 big-endian (0x20..0x7F)
BUF = 0x13CFA0
NUM_I = CAVE + CAVE_LEN - 0x80                # f230 number-drawer hook lives at the cave's end
BUF_END = NUM_I - 4                           # leave room for the NUL (buffer: 640 bytes)
STRLEN = 0x12CD58
HOOK2 = 0x14FC78                              # jal strlen
HOOK2_ORIG = 0x0C04B356


def a2s_table():
    out = bytearray()
    for c in range(0x20, 0x80):
        ch = {0x20: "　", 0x27: "’", 0x22: "”", 0x7F: "　"}.get(c) or chr(c + 0xFEE0)
        out += ch.encode("cp932")
    return bytes(out)


def converter():
    bh, bl = hi_lo(BUF)
    eh, el = hi_lo(BUF_END)
    th, tl = hi_lo(A2S)
    prog = [
        ("", lambda pc: lui("v1", bh)),
        ("", lambda pc: addiu("v1", "v1", bl)),           # v1 = dst
        ("", lambda pc: addu("s4", "v1", "zero")),        # drawer now reads the copy
        ("", lambda pc: lui("a1", eh)),
        ("", lambda pc: addiu("a1", "a1", el)),           # a1 = end of buffer
        ("", lambda pc: lui("a2", th)),
        ("", lambda pc: addiu("a2", "a2", tl)),           # a2 = ASCII table
        ("loop", lambda pc: sltu("at", "v1", "a1")),
        ("", lambda pc: beq("at", "zero", pc, L2["done"])),
        ("", lambda pc: lbu("v0", 0, "a0")),              # (delay) c
        ("", lambda pc: beq("v0", "zero", pc, L2["done"])),
        ("", lambda pc: sltiu("at", "v0", 0x80)),         # (delay)
        ("", lambda pc: beq("at", "zero", pc, L2["two"])),
        ("", lambda pc: addiu("t0", "v0", -0x20)),        # (delay) c - 0x20
        ("", lambda pc: bltz("t0", pc, L2["one"])),       # control byte: copy as is
        ("", lambda pc: sll("t0", "t0", 1)),              # (delay)
        ("", lambda pc: addu("t0", "a2", "t0")),
        ("", lambda pc: lbu("t1", 0, "t0")),
        ("", lambda pc: sb("t1", 0, "v1")),
        ("", lambda pc: lbu("t1", 1, "t0")),
        ("", lambda pc: sb("t1", 1, "v1")),
        ("", lambda pc: addiu("a0", "a0", 1)),
        ("", lambda pc: b(pc, L2["loop"])),
        ("", lambda pc: addiu("v1", "v1", 2)),            # (delay)
        ("one", lambda pc: sb("v0", 0, "v1")),
        ("", lambda pc: addiu("a0", "a0", 1)),
        ("", lambda pc: b(pc, L2["loop"])),
        ("", lambda pc: addiu("v1", "v1", 1)),            # (delay)
        ("two", lambda pc: sb("v0", 0, "v1")),            # Shift-JIS pair: copy both bytes
        ("", lambda pc: lbu("t1", 1, "a0")),
        ("", lambda pc: sb("t1", 1, "v1")),
        ("", lambda pc: addiu("a0", "a0", 2)),
        ("", lambda pc: b(pc, L2["loop"])),
        ("", lambda pc: addiu("v1", "v1", 2)),            # (delay)
        ("done", lambda pc: sb("zero", 0, "v1")),
        ("", lambda pc: j(STRLEN)),                       # strlen(copy), returns to the drawer
        ("", lambda pc: addu("a0", "s4", "zero")),        # (delay)
    ]
    global L2
    L2 = {name: CONV + 4 * k for k, (name, _) in enumerate(prog) if name}
    words = [f(CONV + 4 * k) for k, (_, f) in enumerate(prog)]
    code = struct.pack(f"<{len(words)}I", *words)
    assert CONV + len(code) <= A2S and A2S + 192 <= TABLE
    return code


# ---------------------------------------------------------------- measure

# FUN_0014e700(font, str) returns a string's width in px (89 callers: centring, fit-to-width).
# It is replaced outright by MEASURE, which sums the same width table the drawer uses. ASCII is
# looked up through the same full-width mapping, < > count as 0 (keyword tag brackets), codes
# outside the table count as the font size, and a NULL string returns -1 as before.
MEASURE = 0x13CBE8
HOOK3 = 0x14E700
HOOK3_ORIG = (0x27BDFFF0, 0x0000102D)        # addiu sp,sp,-0x10; move v0,zero (asserted)


def measure(base=None, as_float=False):
    """Integer version replaces FUN_0014e700 (returns v0); float version replaces FUN_0014e4e0
    (returns f0, -1.0 for NULL)."""
    base = base or MEASURE
    th, tl = hi_lo(TABLE)
    ah, al = hi_lo(A2S)
    prog = [
        ("", lambda pc: beq("a1", "zero", pc, L3["null"])),
        ("", lambda pc: addu("v0", "zero", "zero")),        # (delay) total = 0
        ("", lambda pc: lwc1(0, 8, "a0")),                  # font size
        ("", lambda pc: cvt_w_s(0, 0)),
        ("", lambda pc: mfc1("t3", 0)),                     # t3 = default advance
        ("", lambda pc: lui("t2", th)),
        ("", lambda pc: addiu("t2", "t2", tl)),             # t2 = width table
        ("", lambda pc: lui("a3", ah)),
        ("", lambda pc: addiu("a3", "a3", al)),             # a3 = ASCII table
        ("loop", lambda pc: lbu("t0", 0, "a1")),
        ("", lambda pc: beq("t0", "zero", pc, L3["done"])),
        ("", lambda pc: sltiu("at", "t0", 0x80)),           # (delay)
        ("", lambda pc: beq("at", "zero", pc, L3["two"])),
        ("", lambda pc: NOP),
        ("", lambda pc: addiu("t1", "t0", -0x23)),          # '#': colour code #NN or '##'
        ("", lambda pc: bne("t1", "zero", pc, L3["nohash"])),
        ("", lambda pc: lbu("t1", 1, "a1")),                # (delay) next byte
        ("", lambda pc: addiu("t1", "t1", -0x23)),
        ("", lambda pc: beq("t1", "zero", pc, L3["hash2"])),
        ("", lambda pc: NOP),
        ("", lambda pc: b(pc, L3["loop"])),
        ("", lambda pc: addiu("a1", "a1", 3)),              # (delay) #NN: no width
        ("hash2", lambda pc: b(pc, L3["loop"])),
        ("", lambda pc: addiu("a1", "a1", 2)),              # (delay) ##: no width
        ("nohash", lambda pc: addiu("t1", "t0", -0x3C)),    # '<'
        ("", lambda pc: beq("t1", "zero", pc, L3["skip"])),
        ("", lambda pc: addiu("t1", "t0", -0x3E)),          # (delay) '>'
        ("", lambda pc: beq("t1", "zero", pc, L3["skip"])),
        ("", lambda pc: addiu("t0", "t0", -0x20)),          # (delay) ASCII index
        ("", lambda pc: bltz("t0", pc, L3["skip"])),        # control byte
        ("", lambda pc: sll("t0", "t0", 1)),                # (delay)
        ("", lambda pc: addu("t0", "a3", "t0")),
        ("", lambda pc: lbu("t1", 0, "t0")),                # full-width lead
        ("", lambda pc: lbu("t0", 1, "t0")),                # full-width trail
        ("", lambda pc: b(pc, L3["lookup"])),
        ("", lambda pc: addiu("a1", "a1", 1)),              # (delay)
        ("two", lambda pc: addu("t1", "t0", "zero")),       # lead
        ("", lambda pc: lbu("t0", 1, "a1")),                # trail
        ("", lambda pc: addiu("a1", "a1", 2)),
        ("lookup", lambda pc: addiu("t1", "t1", -0x81)),
        ("", lambda pc: sltiu("at", "t1", 2)),
        ("", lambda pc: beq("at", "zero", pc, L3["deflt"])),
        ("", lambda pc: addiu("t0", "t0", -0x40)),          # (delay)
        ("", lambda pc: sltiu("at", "t0", 0x60)),
        ("", lambda pc: beq("at", "zero", pc, L3["deflt"])),
        ("", lambda pc: sll("v1", "t1", 5)),                # (delay)
        ("", lambda pc: sll("t1", "t1", 6)),
        ("", lambda pc: addu("t1", "t1", "v1")),
        ("", lambda pc: addu("t1", "t1", "t0")),
        ("", lambda pc: sll("t1", "t1", 1)),
        ("", lambda pc: addu("t1", "t2", "t1")),
        ("", lambda pc: lbu("v1", 0, "t1")),                # advance
        ("", lambda pc: bne("v1", "zero", pc, L3["add"])),
        ("", lambda pc: NOP),
        ("deflt", lambda pc: addu("v1", "t3", "zero")),
        ("add", lambda pc: b(pc, L3["loop"])),
        ("", lambda pc: addu("v0", "v0", "v1")),            # (delay)
        ("skip", lambda pc: b(pc, L3["loop"])),
        ("", lambda pc: addiu("a1", "a1", 1)),              # (delay)
    ]
    if as_float:
        prog += [
            ("done", lambda pc: mtc1_w(0, "v0")),
            ("", lambda pc: jr("ra")),
            ("", lambda pc: cvt_s_w(0, 0)),                 # (delay) f0 = float(v0)
            ("null", lambda pc: lui("v0", 0xBF80)),         # -1.0
            ("", lambda pc: jr("ra")),
            ("", lambda pc: mtc1_w(0, "v0")),               # (delay)
        ]
    else:
        prog += [
            ("done", lambda pc: jr("ra")),
            ("", lambda pc: NOP),
            ("null", lambda pc: jr("ra")),
            ("", lambda pc: addiu("v0", "zero", -1)),       # (delay)
        ]
    global L3
    L3 = {name: base + 4 * k for k, (name, _) in enumerate(prog) if name}
    words = [f(base + 4 * k) for k, (_, f) in enumerate(prog)]
    return struct.pack(f"<{len(words)}I", *words)


def measure_wrapper(float_measure):
    """FUN_0014e700 replacement: the float MEASURE, result converted to int (NULL -> -1)."""
    def sd(rt, off, rs): return i_type(0x3F, rs, rt, off)
    def ld(rt, off, rs): return i_type(0x37, rs, rt, off)
    words = [addiu("sp", "sp", -16), sd("ra", 0, "sp"), jal(float_measure), NOP,
             ld("ra", 0, "sp"), cvt_w_s(0, 0), mfc1("v0", 0), jr("ra"), addiu("sp", "sp", 16)]
    return struct.pack(f"<{len(words)}I", *words)


# ---------------------------------------------------------------- float drawer

# FUN_0014f6f0 is the float twin of the drawer (HUD names, some menus). Per glyph it keeps the
# advance in $f20, texture U start in $s2 and U end in $s1; the flag test at 0x14F7D8 is the
# hook, and its strlen call at 0x14F798 takes CONV like the integer drawer. Its measure
# FUN_0014e4e0 returns a float and is replaced by the float MEASURE. Code in a second cave:
# FUN_00119248, an unused SIF file-RPC wrapper (no jal, j, branch, pointer or lui/addiu pair).
CAVE_B = 0x119248
CAVE_B_LEN = 588
CODE_F = CAVE_B
HOOK_F = 0x14F7D8                             # beqz $v0, 0x14f868
HOOK_F_ORIG = 0x10400023
RET_F_PLAIN = 0x14F868
RET_F_PROP = 0x14F7E0
HOOK_F2 = 0x14F798                            # jal strlen
MEASURE_F_SITE = 0x14E4E0                     # mtc1 zero,f0; beql a1,zero,...
MEASURE_F_ORIG = (0x44800000, 0x50A0002C)


def routine_f():
    hi, lo = hi_lo(TABLE)
    prog = [
        ("", lambda pc: lbu("v1", 0, "s4")),
        ("", lambda pc: lbu("a0", 1, "s4")),
        ("", lambda pc: addiu("v1", "v1", -0x81)),
        ("", lambda pc: sltiu("at", "v1", 2)),
        ("", lambda pc: beq("at", "zero", pc, LF["miss"])),
        ("", lambda pc: addiu("a0", "a0", -0x40)),
        ("", lambda pc: sltiu("at", "a0", 0x60)),
        ("", lambda pc: beq("at", "zero", pc, LF["miss"])),
        ("", lambda pc: sll("v0", "v1", 5)),
        ("", lambda pc: sll("v1", "v1", 6)),
        ("", lambda pc: addu("v1", "v1", "v0")),
        ("", lambda pc: addu("v1", "v1", "a0")),
        ("", lambda pc: sll("v1", "v1", 1)),
        ("", lambda pc: lui("v0", hi)),
        ("", lambda pc: addu("v0", "v0", "v1")),
        ("", lambda pc: lbu("a0", lo, "v0")),              # advance
        ("", lambda pc: beq("a0", "zero", pc, LF["miss"])),
        ("", lambda pc: lbu("v1", lo + 1, "v0")),          # (delay) U start
        ("", lambda pc: addiu("v0", "zero", CELL)),
        ("", lambda pc: addu("a1", "v1", "a0")),           # U end
        ("", lambda pc: sltu("at", "v0", "a1")),
        ("", lambda pc: beq("at", "zero", pc, LF["fits"])),
        ("", lambda pc: NOP),
        ("", lambda pc: addu("a1", "v0", "zero")),         # U end = CELL
        ("", lambda pc: (R["v0"] << 21) | (R["v1"] << 16) | (R["a0"] << 11) | 0x23),  # subu a0, v0, v1
        ("fits", lambda pc: addu("s1", "a1", "zero")),     # U end
        ("", lambda pc: addu("s2", "v1", "zero")),         # U start
        ("", lambda pc: mtc1_w(20, "a0")),
        ("", lambda pc: j(RET_F_PLAIN)),
        ("", lambda pc: cvt_s_w(20, 20)),                  # (delay) f20 = advance
        ("miss", lambda pc: lw("v0", 0x40, "s5")),
        ("", lambda pc: beq("v0", "zero", pc, LF["plain"])),
        ("", lambda pc: NOP),
        ("", lambda pc: j(RET_F_PROP)),
        ("", lambda pc: NOP),
        ("plain", lambda pc: j(RET_F_PLAIN)),
        ("", lambda pc: NOP),
    ]
    global LF
    LF = {name: CODE_F + 4 * k for k, (name, _) in enumerate(prog) if name}
    words = [f(CODE_F + 4 * k) for k, (_, f) in enumerate(prog)]
    return struct.pack(f"<{len(words)}I", *words)


# ---------------------------------------------------------------- 1-byte number drawers

# FUN_0014ed50 (float x) and FUN_0014f230 (int x) draw 1-byte strings (numbers, "Lv", "%"),
# mapping each byte through the ASCII table at 0x2B1FE0. With the font flag set they squeeze
# digits into a 12/20 cell (U 2..16) and other codes into 14/20, which made the proportional
# Latin glyphs look thin and gappy. Each gets a hook at its flag test that applies the width
# table instead (same registers as its 2-byte twin), falling back to the original code.
# At the hook the glyph code is in $v1 (lead, masked) and $v0 (trail); only $a1-$a3 are free.
HOOK_E = 0x14EE4C                             # beqz $a0, 0x14eee0 (ed50, float)
HOOK_E_ORIG = 0x10800024
RET_E_PLAIN, RET_E_PROP = 0x14EEE0, 0x14EE54
HOOK_I = 0x14F328                             # beqz $a0, 0x14f3d0 (f230, int)
HOOK_I_ORIG = 0x10800029
RET_I_PLAIN, RET_I_PROP = 0x14F3D0, 0x14F330


def routine_num(base, as_float):
    hi, lo = hi_lo(TABLE)
    ret_plain, ret_prop = (RET_E_PLAIN, RET_E_PROP) if as_float else (RET_I_PLAIN, RET_I_PROP)
    L4 = {}
    prog = [
        ("", lambda pc: addiu("a1", "v1", -0x81)),
        ("", lambda pc: sltiu("a2", "a1", 2)),
        ("", lambda pc: beq("a2", "zero", pc, L4["miss"])),
        ("", lambda pc: addiu("a3", "v0", -0x40)),         # (delay) trail - 0x40
        ("", lambda pc: sltiu("a2", "a3", 0x60)),
        ("", lambda pc: beq("a2", "zero", pc, L4["miss"])),
        ("", lambda pc: sll("a2", "a1", 5)),               # (delay)
        ("", lambda pc: sll("a1", "a1", 6)),
        ("", lambda pc: addu("a1", "a1", "a2")),
        ("", lambda pc: addu("a1", "a1", "a3")),
        ("", lambda pc: sll("a1", "a1", 1)),
        ("", lambda pc: lui("a2", hi)),
        ("", lambda pc: addu("a2", "a2", "a1")),
        ("", lambda pc: lbu("a3", lo, "a2")),              # advance
        ("", lambda pc: beq("a3", "zero", pc, L4["miss"])),
        ("", lambda pc: lbu("a1", lo + 1, "a2")),          # (delay) U start
        ("", lambda pc: addu("a2", "a1", "a3")),           # U end
        ("", lambda pc: sltiu("at", "a2", CELL + 1)),
        ("", lambda pc: bne("at", "zero", pc, L4["fits"])),
        ("", lambda pc: NOP),
        ("", lambda pc: addiu("a2", "zero", CELL)),
        ("", lambda pc: (R["a2"] << 21) | (R["a1"] << 16) | (R["a3"] << 11) | 0x23),  # subu a3, a2, a1
    ]
    if as_float:
        prog += [
            ("fits", lambda pc: addu("s1", "a2", "zero")),     # U end
            ("", lambda pc: addu("s2", "a1", "zero")),         # U start
            ("", lambda pc: mtc1_w(20, "a3")),
            ("", lambda pc: j(ret_plain)),
            ("", lambda pc: cvt_s_w(20, 20)),                  # (delay) f20 = advance
        ]
    else:
        prog += [
            ("fits", lambda pc: sw("a2", 0xE0, "sp")),         # U end
            ("", lambda pc: addu("s1", "a3", "zero")),         # advance
            ("", lambda pc: j(ret_plain)),
            ("", lambda pc: addu("fp", "a1", "zero")),         # (delay) U start
        ]
    prog += [
        ("miss", lambda pc: bne("a0", "zero", pc, L4["prop"])),  # original flag test
        ("", lambda pc: NOP),
        ("", lambda pc: j(ret_plain)),                           # (the drawer is out of branch range)
        ("", lambda pc: NOP),
        ("prop", lambda pc: j(ret_prop)),
        ("", lambda pc: NOP),
    ]
    L4.update({name: base + 4 * k for k, (name, _) in enumerate(prog) if name})
    words = [f(base + 4 * k) for k, (_, f) in enumerate(prog)]
    return struct.pack(f"<{len(words)}I", *words)


# ---------------------------------------------------------------- spirit list alignment

# The spirit list (W1OL, call at 0x591CBC) draws each name with FUN_0016e560, which centres
# the string on the column. English reads better left-aligned: both calls are sent to a stub
# that sets the item's x offset (first short of the item struct in $a1) and tail-calls the
# left-aligned twin FUN_0016f4a0 (same arguments).
SPIRIT_STUB = CAVE_B + CAVE_B_LEN - 16
SPIRIT_X = -30                                # column centre -> left edge, px
DRAW_CENTRED, DRAW_LEFT = 0x16E560, 0x16F4A0
OVERLAY_CALLS = {"W1OL": (0x576B80, [0x591CBC])}         # found by logging callers live


def spirit_stub():
    words = [addiu("at", "zero", SPIRIT_X),
             (0x29 << 26) | (R["a1"] << 21) | (R["at"] << 16),   # sh $at, 0($a1)
             j(DRAW_LEFT),
             NOP]
    return struct.pack("<4I", *words)


def patch_overlay(name, data):
    """Redirect an overlay's centred spirit-name draws to the stub (asserting the old calls)."""
    if name not in OVERLAY_CALLS or os.environ.get("VWF_NO_SPIRIT") == "1":
        return data
    base, sites = OVERLAY_CALLS[name]
    out = bytearray(data)
    for va in sites:
        o = va - base
        assert struct.unpack_from("<I", out, o)[0] == jal(DRAW_CENTRED), hex(va)
        struct.pack_into("<I", out, o, jal(SPIRIT_STUB))
    return bytes(out)


def table():
    tab = bytearray(192 * 2)
    if os.path.exists(METRICS):
        for ch, (u0, adv) in json.load(open(METRICS, encoding="utf-8")).items():
            code = int.from_bytes(ch.encode("cp932"), "big")
            lead, trail = code >> 8, code & 0xFF
            if lead in (0x81, 0x82) and 0x40 <= trail < 0xA0:
                idx = (lead - 0x81) * 0x60 + trail - 0x40
                tab[2 * idx], tab[2 * idx + 1] = adv, u0
        return bytes(tab)
    ink = json.load(open(INK, encoding="utf-8"))
    for ch, v in ink.items():
        code = int.from_bytes(ch.encode("cp932"), "big")
        lead, trail = code >> 8, code & 0xFF
        if lead not in (0x81, 0x82) or not 0x40 <= trail < 0xA0:
            continue
        idx = (lead - 0x81) * 0x60 + trail - 0x40
        if ch == "　":
            adv, left = SPACE, 0
        elif v is None:
            continue
        else:
            left, right = v
            adv = right - left + 1 + GAP
        tab[2 * idx] = adv
        tab[2 * idx + 1] = left
    return bytes(tab)


def blob():
    words = routine()
    code = struct.pack(f"<{len(words)}I", *words)
    assert CODE + len(code) <= MEASURE
    tab = table()
    assert TABLE + len(tab) <= BUF
    return code, tab


def hook_word():
    return j(CODE)


def patch_bytes(read, write):
    """Apply through read(addr, n) / write(addr, bytes) callables."""
    assert struct.unpack("<I", read(HOOK, 4))[0] == HOOK_ORIG, "hook site changed"
    assert read(CAVE, 8) == ORIG_CAVE_HEAD, "cave not pristine"
    assert struct.unpack("<I", read(HOOK2, 4))[0] == HOOK2_ORIG, "strlen hook site changed"
    code, tab = blob()
    write(CODE, code)
    write(TABLE, tab)
    conv_on = os.environ.get("VWF_NO_CONV") != "1"
    if conv_on:
        write(CONV, converter())
        write(A2S, a2s_table())
    measure_on = os.environ.get("VWF_NO_MEASURE") != "1"
    assert struct.unpack("<2I", read(HOOK3, 8)) == HOOK3_ORIG, "measure entry changed"
    assert struct.unpack("<I", read(HOOK_F, 4))[0] == HOOK_F_ORIG, "float drawer hook site changed"
    assert struct.unpack("<I", read(HOOK_F2, 4))[0] == HOOK2_ORIG, "float drawer strlen site changed"
    assert struct.unpack("<2I", read(MEASURE_F_SITE, 8)) == MEASURE_F_ORIG, "float measure entry changed"
    assert read(CAVE_B, 8) == ORIG_CAVE_B_HEAD, "cave B not pristine"
    code_f = routine_f()
    mf_base = CODE_F + len(code_f)
    mf = measure(mf_base, as_float=True)
    assert mf_base + len(mf) <= CAVE_B + CAVE_B_LEN, "cave B overflow"
    write(CODE_F, code_f)
    write(mf_base, mf)
    if os.environ.get("VWF_NO_NUM") != "1":
        assert struct.unpack("<I", read(HOOK_E, 4))[0] == HOOK_E_ORIG, "ed50 hook site changed"
        assert struct.unpack("<I", read(HOOK_I, 4))[0] == HOOK_I_ORIG, "f230 hook site changed"
        e_base = mf_base + len(mf)
        ce = routine_num(e_base, True)
        assert e_base + len(ce) <= SPIRIT_STUB, f"cave B overflow ({e_base + len(ce) - CAVE_B} > {SPIRIT_STUB - CAVE_B})"
        write(SPIRIT_STUB, spirit_stub())
        i_base = NUM_I
        ci = routine_num(i_base, False)
        assert i_base + len(ci) <= CAVE + CAVE_LEN, "cave overflow (f230 hook)"
        write(e_base, ce)
        write(i_base, ci)
        write(HOOK_E, struct.pack("<I", j(e_base)))
        write(HOOK_I, struct.pack("<I", j(i_base)))
    write(HOOK_F, struct.pack("<I", j(CODE_F)))
    write(MEASURE_F_SITE, struct.pack("<2I", j(mf_base), NOP))
    if measure_on:
        write(MEASURE, measure_wrapper(mf_base))
    write(HOOK, struct.pack("<I", hook_word()))
    if conv_on:
        write(HOOK2, struct.pack("<I", jal(CONV)))
        write(HOOK_F2, struct.pack("<I", jal(CONV)))
    if measure_on:
        write(HOOK3, struct.pack("<2I", j(MEASURE), NOP))


ORIG_CAVE_HEAD = ORIG_CAVE_B_HEAD = None  # filled from the pristine ELF on first use


def _load_orig_head():
    global ORIG_CAVE_HEAD, ORIG_CAVE_B_HEAD
    elf = os.path.join(os.path.expanduser("~"), "srwogg-work", "ext", "SLPS_258.36")
    d = open(elf, "rb").read()
    ORIG_CAVE_HEAD = d[CAVE - ELF_BASE + ELF_OFF:CAVE - ELF_BASE + ELF_OFF + 8]
    ORIG_CAVE_B_HEAD = d[CAVE_B - ELF_BASE + ELF_OFF:CAVE_B - ELF_BASE + ELF_OFF + 8]
    return d


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    pristine = _load_orig_head()
    if a[0] == "table":
        tab = table()
        for idx in range(192):
            if tab[2 * idx]:
                code = bytes([0x81 + idx // 0x60, 0x40 + idx % 0x60])
                print(code.decode("cp932"), tab[2 * idx], tab[2 * idx + 1], end="  ")
        print()
    elif a[0] in ("live", "unlive"):
        sys.path.insert(0, os.path.dirname(__file__))
        from pine import Pine
        p = Pine()
        if a[0] == "live":
            patch_bytes(p.read, p.write)
            print("live patch applied")
        else:
            off = CAVE - ELF_BASE + ELF_OFF
            p.write(CAVE, pristine[off:off + CAVE_LEN])
            p.write(HOOK, struct.pack("<I", HOOK_ORIG))
            p.write(HOOK2, struct.pack("<I", HOOK2_ORIG))
            p.write(HOOK3, struct.pack("<2I", *HOOK3_ORIG))
            print("live patch removed")
    elif a[0] == "elf":
        d = bytearray(open(a[1], "rb").read())

        def rd(addr, n):
            o = addr - ELF_BASE + ELF_OFF
            return bytes(d[o:o + n])

        def wr(addr, b):
            o = addr - ELF_BASE + ELF_OFF
            d[o:o + len(b)] = b
        patch_bytes(rd, wr)
        open(a[2], "wb").write(d)
        print("wrote", a[2])


if __name__ == "__main__":
    main()
