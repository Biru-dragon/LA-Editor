"""Arrows map editor (pygame): infinite 2D world, zoom down to 1/8 px per cell.

Usage: python editeur.py [file.json]   (default file: World.json)
Dependencies: pygame, arrows.py (your library), Arrows.png and Keys.png in the same folder.
"""
import base64
import colorsys
import json
import math
import sys
import time
from pathlib import Path

import pygame

from arrows import (Map, Arrow, ArrowType, Direction, Instrument, INSTRUMENT_RANGES,
                    Color, COLORED_TYPES, Key, KEYBOARD_TYPES,
                    TEXT_TYPES, TEXT_FLAG, MAX_TEXT_BYTES, LOGGER_MAGIC, LOGGER_DEFAULT_FLAG,
                    WallColor, WALL_TYPES, WALL_COLOR_SHIFT, WALL_INLINE_MAX, WALL_LETTER_FIRST, WALL_LETTER_LAST,
                    wall_letter_char)

HERE = Path(__file__).resolve().parent

SPRITE = 256                 # size of one sprite in Arrows.png and Keys.png
CHUNK = 16
ZOOMS = [1 / 8, 1 / 4, 1 / 2, 1, 2, 4, 8, 16, 32, 64, 128]   # pixels per cell
DIRECT_DRAW_MIN = 32         # from this zoom on, draw cell by cell (no chunk cache)
ICON, PAD, PALETTE_COLS = 48, 4, 4
PANEL_W = PALETTE_COLS * (ICON + PAD) + PAD

# Sprite indexing in Arrows.png:
#   None -> automatic detection (empty cell 0 => index = id; otherwise index = id - 1)
#   0    -> index = ArrowType id (cell 0 is Empty_cell's, left blank)
#   -1   -> index = id - 1 (the first cell is directly "Arrow")
SHEET_ID_OFFSET = None

# Keys.png: the key sprite is drawn ON TOP of the Key base sprite (Arrows.png).
# There is no sprite for NotDefined: the first sprite in Keys.png is "A" (index = Key value - 1).
# True: the key follows the arrow's orientation / flip; False: it stays upright (like the "B" / "N" of Displays).
KEY_FOLLOWS_DIRECTION = False

DRAWABLE = [t for t in ArrowType if t != ArrowType.Empty_cell and not t.name.startswith('TODO')]

BG = (22, 22, 27)
GRID_CELL = (38, 38, 46)
GRID_CHUNK = (62, 62, 78)
GRID_AXIS = (120, 70, 70)


def ipx(v: float) -> int:
    return int(math.floor(v + 0.5))


# --------------------------------------------------------------------------- notes

PITCH_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
NOTE_INSTRUMENTS = list(INSTRUMENT_RANGES)       # display order in the notes panel
NOTE_LABEL_MIN = 32                              # minimum cell size to show the note text
NP_PAD, NP_GAP = 8, 4
NP_INST_W, NP_INST_H, NP_BTN_H = 104, 22, 26
NP_INNER = 2 * NP_INST_W + NP_GAP
NP_W = NP_INNER + 2 * NP_PAD


# --------------------------------------------------------------------------- colors (Light_bulb1 / Light_bulb2)

COLOR_LIST = list(Color)                         # Undefined + 6 colors = 7 states
COLOR_LABELS = {Color.Undefined: 'Undefined', Color.Red: 'Red', Color.Blue: 'Blue', Color.Yellow: 'Yellow',
                Color.Green: 'Green', Color.Orange: 'Orange', Color.Purple: 'Purple'}
COLOR_RGB = {Color.Undefined: (150, 150, 160), Color.Red: (235, 50, 50), Color.Blue: (60, 100, 245),
             Color.Yellow: (245, 225, 50), Color.Green: (60, 205, 80), Color.Orange: (250, 150, 30),
             Color.Purple: (165, 70, 225)}


def display_rgb(color: int, bright: bool = False) -> tuple[int, int, int]:
    """Background color of a Light_bulb1 cell (same in Normal and Bright: Bright = letter B, Normal = letter N)."""
    try:
        return COLOR_RGB[Color(int(color))]
    except ValueError:
        return COLOR_RGB[Color.Undefined]


def display_text(color: int, bright: bool) -> str:
    try:
        name = COLOR_LABELS[Color(int(color))]
    except ValueError:
        name = f'#{int(color)}'
    return f'{name} {"Bright" if bright else "Normal"}'


# --------------------------------------------------------------------------- keys (Key)

KEY_LIST = list(Key)                             # 60 states, in Keys.png order (index = key value)
KP_COLS = 4


def key_label(k: int) -> str:
    try:
        name = Key(int(k)).name
    except ValueError:
        return f'#{int(k)}'
    if name == 'NotDefined':
        return 'None'
    return name[3:] if name.startswith('Num') else name


# --------------------------------------------------------------------------- walls (Wall: color + letter / digit)

WALL_COLOR_LIST = list(WallColor)                # 8 colors (white = default color)
WALL_LABELS = {WallColor.White: 'White', WallColor.Red: 'Red', WallColor.Blue: 'Blue', WallColor.Yellow: 'Yellow',
               WallColor.Green: 'Green', WallColor.Orange: 'Orange', WallColor.Purple: 'Purple', WallColor.Black: 'Black'}
WALL_RGB = {WallColor.White: (240, 240, 245), WallColor.Red: (235, 50, 50), WallColor.Blue: (60, 100, 245),
            WallColor.Yellow: (245, 225, 50), WallColor.Green: (60, 205, 80), WallColor.Orange: (250, 150, 30),
            WallColor.Purple: (165, 70, 225), WallColor.Black: (25, 25, 30)}
WALL_TINT_ALPHA = 170                            # opacity of the tint drawn over the wall sprite (out of 255)
WALL_LETTER_LIST = list(range(WALL_LETTER_FIRST, WALL_LETTER_LAST + 1))   # A to Z then 0 to 9
WP_COLS = 6                                      # columns of the panel's letter grid


def wall_rgb(color: int) -> tuple[int, int, int] | None:
    """Display color of a wall; None if the value is unknown (imported map)."""
    try:
        return WALL_RGB[WallColor(int(color))]
    except ValueError:
        return None


def wall_text(color: int, letter: int) -> str:
    """Label of a wall: color + letter (e.g. Red "A", Blue no letter)."""
    try:
        name = WALL_LABELS[WallColor(int(color))]
    except ValueError:
        name = f'#{int(color)}'
    ch = wall_letter_char(int(letter))
    if ch:
        return f'{name} "{ch}"'
    return f'{name} no letter' if not int(letter) else f'{name} letter #{int(letter)}'


# --------------------------------------------------------------------------- text (Source / Target / Script_block / Message)

TEXT_LABEL_MIN = 32                              # minimum cell size to show a text preview
TEXT_MAX_BYTES = MAX_TEXT_BYTES - (len(LOGGER_MAGIC) + 1)   # same limit as Arrow.text() (margin for the Message header)
TP_W = 440
TP_INNER = TP_W - 2 * NP_PAD
TP_BOX_H, TP_LINE_H = 288, 18
TP_VIS = (TP_BOX_H - 8) // TP_LINE_H             # number of lines visible in the input area
TP_WRAP_W = TP_INNER - 8 - 8                     # usable width of a line (pixels), minus the scrollbar; the gutter comes off it


def text_preview(txt: str, limit: int = 40) -> str:
    one = txt.replace('\n', ' / ')
    return one if len(one) <= limit else one[:limit - 3] + '...'


def clean_text(s: str) -> str:
    """Normalizes line endings, replaces tabs with 2 spaces, strips control characters."""
    s = s.replace('\r\n', '\n').replace('\r', '\n').replace('\t', '  ')
    return ''.join(c for c in s if c == '\n' or (c >= ' ' and c != '\x7f'))


# Types whose text is JavaScript (highlighting + .js import / export). The Message stays plain text.
JS_TYPES = frozenset({ArrowType.Source, ArrowType.Target, ArrowType.Script_block})
(JS_DEFAULT, JS_KEYWORD, JS_STRING, JS_COMMENT, JS_NUMBER, JS_LITERAL, JS_FUNCTION, JS_PUNCT) = range(8)
JS_COLORS = [(235, 235, 240), (197, 134, 192), (206, 145, 120), (106, 153, 85),
             (181, 206, 168), (86, 156, 214), (220, 220, 170), (160, 160, 175)]
JS_KEYWORDS = frozenset(("break case catch class const continue debugger default delete do else export extends "
                         "finally for function if import in instanceof let new of return static super switch "
                         "throw try typeof var void while with yield async await").split())
JS_LITERALS = frozenset("true false null undefined NaN Infinity this".split())
JS_PUNCT_CHARS = frozenset("{}()[];,.:+-*/%=<>!&|?^~")


def js_highlight(text: str) -> bytearray:
    """Color code (JS_*) of each character of `text`: comments, strings, numbers, keywords..."""
    n = len(text)
    out = bytearray(n)

    def fill(i: int, j: int, code: int):
        out[i:j] = bytes([code]) * (j - i)

    i = 0
    while i < n:
        c = text[i]
        if text.startswith('//', i):
            j = text.find('\n', i)
            j = n if j < 0 else j
            fill(i, j, JS_COMMENT)
        elif text.startswith('/*', i):
            j = text.find('*/', i + 2)
            j = n if j < 0 else j + 2
            fill(i, j, JS_COMMENT)
        elif c in ('"', "'", '`'):
            j = i + 1
            while j < n:
                ch = text[j]
                if ch == '\\':
                    j += 2
                    continue
                if ch == c:
                    j += 1
                    break
                if ch == '\n' and c != '`':
                    break
                j += 1
            j = min(j, n)
            fill(i, j, JS_STRING)
        elif c.isdigit() or (c == '.' and i + 1 < n and text[i + 1].isdigit()):
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] in '._'):
                j += 1
            fill(i, j, JS_NUMBER)
        elif c.isalpha() or c in '_$':
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] in '_$'):
                j += 1
            word = text[i:j]
            if word in JS_KEYWORDS:
                fill(i, j, JS_KEYWORD)
            elif word in JS_LITERALS:
                fill(i, j, JS_LITERAL)
            else:
                k = j
                while k < n and text[k] in ' \t':
                    k += 1
                if k < n and text[k] == '(':
                    fill(i, j, JS_FUNCTION)
        else:
            j = i + 1
            if c in JS_PUNCT_CHARS:
                out[i] = JS_PUNCT
        i = j
    return out


def instrument_name(i: int) -> str:
    try:
        return Instrument(int(i)).name
    except ValueError:
        return f'#{int(i)}'


def instrument_range(i: int) -> tuple[int, int]:
    return INSTRUMENT_RANGES.get(int(i), (0, 15))


def note_name(pitch: int, octave: int) -> str:
    return f"{PITCH_NAMES[pitch] if 0 <= pitch < 12 else '?'}{octave}"


def note_text(note) -> str:
    instrument, pitch, octave = note
    return f'{instrument_name(instrument)} {note_name(int(pitch), int(octave))}'


# --------------------------------------------------------------------------- text buffer (editing logic of the text panel)


class TextBuffer:
    """Text of the text panel with cursor, selection and undo / redo history. No pygame: easy to test."""

    HISTORY_MAX = 300
    PAIRS = {'(': ')', '[': ']', '{': '}'}

    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes
        self.text = ''
        self.cursor = 0
        self.anchor: int | None = None           # selection anchor (None = no selection)
        self.limit_hit = False                   # the last edit was cut short / refused by the byte limit
        self.goal_col: int | None = None         # sticky column for vertical moves
        self.first_no: list[int] = []            # line number of each visual line (0 = wrapped continuation)
        self._undo: list = []
        self._redo: list = []
        self._group = None                       # kind of the last edit (merges consecutive typing / deletions)
        self._lines_cache = None
        self._match_cache = None

    # ---- content and selection -----------------------------------------

    def load(self, text: str, cursor: int | None = None):
        """Replaces the whole content without history (new text: right click, eyedropper...)."""
        self.text = text
        self.cursor = len(text) if cursor is None else max(0, min(len(text), cursor))
        self.anchor = self.goal_col = None
        self._undo.clear()
        self._redo.clear()
        self._group = None

    @property
    def selection(self) -> tuple[int, int] | None:
        if self.anchor is None or self.anchor == self.cursor:
            return None
        return min(self.anchor, self.cursor), max(self.anchor, self.cursor)

    def selected_text(self) -> str:
        sel = self.selection
        return self.text[sel[0]:sel[1]] if sel else ''

    def line_start(self, i: int) -> int:
        return self.text.rfind('\n', 0, i) + 1

    def line_end(self, i: int) -> int:
        e = self.text.find('\n', i)
        return len(self.text) if e < 0 else e

    def line_at(self, i: int) -> tuple[int, int]:
        """Whole line containing `i`, including its newline."""
        return self.line_start(i), min(self.line_end(i) + 1, len(self.text))

    @staticmethod
    def _cls(c: str) -> int:
        if c == '\n':
            return 3
        if c.isspace():
            return 0
        return 1 if (c.isalnum() or c in '_$') else 2

    def word_left(self, i: int) -> int:
        t = self.text
        while i > 0 and t[i - 1].isspace():
            i -= 1
        if i > 0:
            c = self._cls(t[i - 1])
            while i > 0 and self._cls(t[i - 1]) == c:
                i -= 1
        return i

    def word_right(self, i: int) -> int:
        t, n = self.text, len(self.text)
        while i < n and t[i].isspace():
            i += 1
        if i < n:
            c = self._cls(t[i])
            while i < n and self._cls(t[i]) == c:
                i += 1
        return i

    def word_at(self, i: int) -> tuple[int, int]:
        """Word (or run of spaces / symbols) under `i`, for a double click."""
        t, n = self.text, len(self.text)
        if n == 0:
            return 0, 0
        i = max(0, min(n, i))
        j = i if i < n else i - 1
        if t[j] == '\n' and j > 0 and t[j - 1] != '\n':
            j -= 1
        c = self._cls(t[j])
        if c == 3:                                   # a newline is never grouped with its neighbours
            return j, j + 1
        s, e = j, j + 1
        while s > 0 and self._cls(t[s - 1]) == c:
            s -= 1
        while e < n and self._cls(t[e]) == c:
            e += 1
        return s, e

    # ---- cursor movement ---------------------------------------------------

    def cursor_line(self, lines) -> int:
        i = self.cursor
        for n, (s, e, last) in enumerate(lines):
            if s <= i < e or (i == e and last):
                return n
        return len(lines) - 1

    def move_to(self, index: int, extend: bool = False):
        index = max(0, min(len(self.text), index))
        if extend:
            if self.anchor is None:
                self.anchor = self.cursor
        else:
            self.anchor = None
        self.cursor = index
        self.goal_col = None
        self._group = None

    def move_left(self, word: bool = False, extend: bool = False):
        sel = self.selection
        if sel and not extend and not word:
            self.move_to(sel[0])
        else:
            self.move_to(self.word_left(self.cursor) if word else self.cursor - 1, extend)

    def move_right(self, word: bool = False, extend: bool = False):
        sel = self.selection
        if sel and not extend and not word:
            self.move_to(sel[1])
        else:
            self.move_to(self.word_right(self.cursor) if word else self.cursor + 1, extend)

    def move_vertical(self, d: int, lines, extend: bool = False):
        """`d` visual lines up (< 0) or down (> 0), keeping the column; past the ends goes to the start / end."""
        n = self.cursor_line(lines)
        col = self.goal_col if self.goal_col is not None else self.cursor - lines[n][0]
        m = n + d
        if m < 0:
            target = 0
        elif m >= len(lines):
            target = len(self.text)
        else:
            s, e, last = lines[m]
            target = s + min(col, e - s)
            if not last and target == e and e > s:
                target = e - 1
        self.move_to(target, extend)
        self.goal_col = col

    def home_end(self, home: bool, lines, extend: bool = False, doc: bool = False):
        if doc:
            idx = 0 if home else len(self.text)
        else:
            s, e, last = lines[self.cursor_line(lines)]
            idx = s if home else (e if last or not self.text[e - 1:e].isspace() else e - 1)
        self.move_to(idx, extend)

    def select_all(self):
        self.select_range(0, len(self.text))

    def select_range(self, a: int, b: int):
        n = len(self.text)
        self.anchor, self.cursor = max(0, min(n, a)), max(0, min(n, b))
        self.goal_col = None
        self._group = None

    # ---- editing -------------------------------------------------------------

    def _snapshot(self):
        return self.text, self.cursor, self.anchor

    def _record(self, group):
        if group is None or group != self._group or not self._undo:
            self._undo.append(self._snapshot())
            if len(self._undo) > self.HISTORY_MAX:
                del self._undo[0]
        self._group = group
        self._redo.clear()

    def replace(self, start: int, end: int, new: str, group=None, cursor: int | None = None) -> bool:
        """Replaces text[start:end] by `new`, cut to fit the byte limit. True if the text changed.
        `group` merges consecutive edits of the same kind into one undo step."""
        n = len(self.text)
        start, end = max(0, min(n, start)), max(0, min(n, end))
        if end < start:
            start, end = end, start
        self.limit_hit = False
        room = self.max_bytes - len(self.text.encode('utf-8')) + len(self.text[start:end].encode('utf-8'))
        out = ''
        for c in new:
            size = len(c.encode('utf-8'))
            if size > room:
                self.limit_hit = True
                break
            out += c
            room -= size
        if out == self.text[start:end]:
            return False
        self._record(group)
        self.text = self.text[:start] + out + self.text[end:]
        self.cursor = start + len(out) if cursor is None else max(0, min(len(self.text), cursor))
        self.anchor = None
        self.goal_col = None
        return True

    def replace_all(self, text: str, cursor: int | None = None) -> bool:
        return self.replace(0, len(self.text), text, cursor=cursor)

    def insert(self, s: str, group=None) -> bool:
        """Inserts `s` at the cursor, replacing the selection."""
        s = clean_text(s)
        if not s:
            return False
        sel = self.selection
        if sel:
            return self.replace(sel[0], sel[1], s)
        return self.replace(self.cursor, self.cursor, s, group)

    def type_text(self, s: str, js: bool = False) -> bool:
        """Typed text (TEXTINPUT). A single character merges into the previous typing step;
        in JavaScript, a closing bracket typed after indentation only dedents by one level."""
        s = clean_text(s)
        if len(s) == 1 and s != '\n':
            if js and s in '}])' and self.selection is None:
                prefix = self.text[self.line_start(self.cursor):self.cursor]
                if len(prefix) >= 2 and not prefix.strip(' '):
                    return self.replace(self.cursor - 2, self.cursor, s, 'type')
            return self.insert(s, 'type')
        return self.insert(s)

    def newline(self, js: bool = False) -> bool:
        """Enter. In JavaScript: keeps the indentation, indents after { ( [ and opens a pair {|} on 3 lines."""
        sel = self.selection
        a, b = sel if sel else (self.cursor, self.cursor)
        ins = '\n'
        if js:
            before = self.text[self.line_start(a):a]
            indent = before[:len(before) - len(before.lstrip(' '))]
            opener = before.rstrip()[-1:]
            if opener in self.PAIRS and self.text[b:b + 1] == self.PAIRS[opener]:
                mid = indent + '  '
                return self.replace(a, b, '\n' + mid + '\n' + indent, cursor=a + 1 + len(mid))
            ins += indent + ('  ' if opener in self.PAIRS else '')
        return self.replace(a, b, ins)

    def _block(self) -> tuple[int, int]:
        """Whole lines touched by the selection (or the cursor line), without the final newline."""
        sel = self.selection
        a, b = sel if sel else (self.cursor, self.cursor)
        if sel and b > a and self.text[b - 1] == '\n':
            b -= 1
        return self.line_start(a), self.line_end(b)

    def _replace_block(self, s: int, e: int, lines: list[str], had_sel: bool, old_cursor: int, old_first: str) -> bool:
        block = '\n'.join(lines)
        if not self.replace(s, e, block):
            return False
        if had_sel:
            self.anchor = s                          # the modified block stays selected
        else:
            self.cursor = max(s, min(s + len(lines[0]), old_cursor + len(lines[0]) - len(old_first)))
        return True

    def tab(self, shift: bool = False) -> bool:
        """JavaScript: Tab inserts spaces up to the next 2-column stop, or indents the selected lines;
        Shift+Tab dedents the selected lines (or the current one)."""
        sel = self.selection
        multi = sel is not None and '\n' in self.text[sel[0]:sel[1]]
        if not shift and not multi:
            a, b = sel if sel else (self.cursor, self.cursor)
            return self.replace(a, b, ' ' * (2 - (a - self.line_start(a)) % 2))
        s, e = self._block()
        old = self.text[s:e].split('\n')
        if shift:
            new = [l[min(2, len(l) - len(l.lstrip(' '))):] for l in old]
        else:
            new = ['  ' + l if l.strip() else l for l in old]
        return self._replace_block(s, e, new, sel is not None, self.cursor, old[0])

    def toggle_comment(self) -> bool:
        """JavaScript: comments / uncomments the selected lines (or the current one) with //."""
        s, e = self._block()
        old = self.text[s:e].split('\n')
        work = [l for l in old if l.strip()]
        if not work:
            return False
        if all(l.lstrip(' ').startswith('//') for l in work):
            new = []
            for l in old:
                ind = len(l) - len(l.lstrip(' '))
                rest = l[ind:]
                if rest.startswith('//'):
                    rest = rest[3:] if rest.startswith('// ') else rest[2:]
                new.append(l[:ind] + rest)
        else:
            ind = min(len(l) - len(l.lstrip(' ')) for l in work)
            new = [l[:ind] + '// ' + l[ind:] if l.strip() else l for l in old]
        return self._replace_block(s, e, new, self.selection is not None, self.cursor, old[0])

    def delete_back(self, word: bool = False) -> bool:
        sel = self.selection
        if sel:
            return self.replace(sel[0], sel[1], '')
        if self.cursor == 0:
            return False
        start = self.word_left(self.cursor) if word else self.cursor - 1
        return self.replace(start, self.cursor, '', 'back')

    def delete_forward(self, word: bool = False) -> bool:
        sel = self.selection
        if sel:
            return self.replace(sel[0], sel[1], '')
        if self.cursor >= len(self.text):
            return False
        end = self.word_right(self.cursor) if word else self.cursor + 1
        return self.replace(self.cursor, end, '', 'forward')

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self.text, self.cursor, self.anchor = self._undo.pop()
        self._group = self.goal_col = None
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self.text, self.cursor, self.anchor = self._redo.pop()
        self._group = self.goal_col = None
        return True

    # ---- layout and brackets -------------------------------------------------

    def lines(self, width: int, cw, key=None) -> list:
        """Visual lines (start, end, paragraph end), word wrapping in `width` pixels (`cw` = width of a character).
        Also fills first_no (line number of each visual line, 0 for wrapped continuations)."""
        ck = (self.text, width, key)
        if self._lines_cache is not None and self._lines_cache[0] == ck:
            return self._lines_cache[1]
        t = self.text
        lines, firsts, no, pos = [], [], 0, 0
        for para in t.split('\n'):
            no += 1
            start, cur, w, brk, first = pos, pos, 0, None, True
            for ch in para:
                c = cw(ch)
                while w + c > width and cur > start and not (ch == ' ' and t[cur - 1] != ' '):   # one trailing space may hang
                    cut = brk if (brk is not None and brk > start) else cur
                    lines.append((start, cut, False))
                    firsts.append(no if first else 0)
                    first = False
                    start, w, brk = cut, sum(cw(x) for x in t[cut:cur]), None
                w += c
                cur += 1
                if ch == ' ':
                    brk = cur                        # a line may break after a space
            lines.append((start, cur, True))
            firsts.append(no if first else 0)
            pos = cur + 1                            # skip the '\n'
        self.first_no = firsts
        self._lines_cache = (ck, lines)
        return lines

    def match_bracket(self, colors=None, limit: int = 30000) -> tuple[int, int] | None:
        """Matching bracket of the one before or under the cursor (strings and comments ignored if `colors` is given)."""
        ck = (self.text, self.cursor, id(colors), limit)
        if self._match_cache is not None and self._match_cache[0] == ck:
            return self._match_cache[1]
        result = self._find_bracket(colors, limit)
        self._match_cache = (ck, result)
        return result

    def _find_bracket(self, colors, limit: int):
        t, n = self.text, len(self.text)
        closers = {v: k for k, v in self.PAIRS.items()}

        def skip(i):
            return colors is not None and colors[i] in (JS_STRING, JS_COMMENT)

        for i in (self.cursor - 1, self.cursor):
            if not (0 <= i < n) or skip(i):
                continue
            ch = t[i]
            if ch in self.PAIRS:
                step, other = 1, self.PAIRS[ch]
            elif ch in closers:
                step, other = -1, closers[ch]
            else:
                continue
            depth, j = 0, i
            end = min(n, i + limit) if step > 0 else max(-1, i - limit)
            while j != end:
                if not skip(j):
                    if t[j] == ch:
                        depth += 1
                    elif t[j] == other:
                        depth -= 1
                        if depth == 0:
                            return i, j
                j += step
        return None


# --------------------------------------------------------------------------- export

def _enc_coord(v: int) -> int:
    if not -0x7FFF <= v <= 0x7FFF:
        raise ValueError('Chunk coordinate out of range')
    return (-v | 0x8000) if v < 0 else v


def encode_world(world: Map) -> str:
    """Base64 export, version 5 (uncompressed).

    Reimplemented here, independently of Map.export(). Music_Arrow arrows store a
    16-bit value (octave << 4 | note, instrument << 8) instead of a text; Key arrows
    store the key index (see arrows.Key). Text types (TEXT_TYPES: 22, 23, 33, 34)
    get the TEXT_FLAG flag when they have a text, and the Message is prefixed with the header
    LOGGER_MAGIC + logger_flag, exactly as in Map.export(). A Wall (25) without a letter keeps its
    color in bits 4 to 6 of dnf; with a letter, a u16 value (letter << 4 | color) follows.
    """
    chunks = []
    for (cx, cy), chunk in world.chunks.items():
        types = []
        for a in chunk.arrows:
            if a.type != ArrowType.Empty_cell and a.type not in types:
                types.append(a.type)
        if types:
            chunks.append((cx, cy, chunk, types))
    if len(chunks) > 0x7FFF:
        raise ValueError('Too many chunks for the format')

    body = bytearray(len(chunks).to_bytes(2, 'little'))
    for cx, cy, chunk, types in chunks:
        body += _enc_coord(cx).to_bytes(2, 'little') + _enc_coord(cy).to_bytes(2, 'little')
        body.append(len(types) - 1)
        for t in types:
            cells = [(x, y, chunk.get(x, y)) for x in range(CHUNK) for y in range(CHUNK)
                     if chunk.get(x, y).type == t]
            body.append(int(t))
            body.append(len(cells) - 1)
            for x, y, a in cells:
                is_note = a.type == ArrowType.Music_Arrow
                is_colored = a.type in COLORED_TYPES
                is_keyboard = a.type in KEYBOARD_TYPES
                is_wall = a.type in WALL_TYPES
                wall_color = int(a.wall_color)
                wall_inline = is_wall and a.wall_letter == 0 and 0 <= wall_color <= WALL_INLINE_MAX
                wall_data = is_wall and not wall_inline
                is_text = a.type in TEXT_TYPES and a.string != ''
                has_string = is_note or is_colored or is_keyboard or wall_data or (not is_wall and a.string != '')
                dnf = (int(a.direction) | (int(bool(a.flipped)) << 2)
                       | (0b1000 if has_string else 0) | (TEXT_FLAG if is_text else 0)
                       | (wall_color << WALL_COLOR_SHIFT if wall_inline else 0))
                body.append(x | (y << 4))
                body.append(dnf)
                if is_note:
                    body += a.note_value.to_bytes(2, 'little')
                elif is_colored:
                    body += a.display_value.to_bytes(2, 'little')
                elif is_keyboard:
                    body += a.key_value.to_bytes(2, 'little')
                elif is_wall:
                    if wall_data:
                        body += a.wall_value.to_bytes(2, 'little')
                elif a.string != '':
                    data = a.string.encode('utf-8')
                    if a.type == ArrowType.Message:
                        data = LOGGER_MAGIC + bytes([int(a.logger_flag) & 0xFF]) + data
                    if len(data) > MAX_TEXT_BYTES:
                        raise ValueError('Text too long')
                    body += len(data).to_bytes(2, 'little') + data
    raw = (5).to_bytes(2, 'little') + b'\x00' + bytes(body)
    return base64.b64encode(raw).decode('ascii')


# --------------------------------------------------------------------------- sprites

def _average_color(surf: pygame.Surface) -> tuple[int, int, int]:
    small = pygame.transform.smoothscale(surf, (16, 16))
    r = g = b = n = 0
    for y in range(16):
        for x in range(16):
            c = small.get_at((x, y))
            if c.a > 40:
                r += c.r
                g += c.g
                b += c.b
                n += 1
    return (r // n, g // n, b // n) if n else (128, 128, 128)


def _placeholder(t: ArrowType) -> pygame.Surface:
    """Fallback sprite (up arrow + number) if Arrows.png is missing."""
    surf = pygame.Surface((SPRITE, SPRITE), pygame.SRCALPHA)
    r, g, b = colorsys.hsv_to_rgb((int(t) * 0.137) % 1.0, 0.55, 0.85)
    pygame.draw.rect(surf, (int(r * 255), int(g * 255), int(b * 255)), (8, 8, 240, 240), border_radius=24)
    pygame.draw.polygon(surf, (20, 20, 20), [(128, 30), (210, 130), (150, 130), (150, 226), (106, 226), (106, 130), (46, 130)])
    txt = pygame.font.Font(None, 72).render(str(int(t)), True, (255, 255, 255))
    surf.blit(txt, (128 - txt.get_width() // 2, 150))
    return surf


class Sprites:
    def __init__(self):
        self.base: dict[ArrowType, pygame.Surface] = {}
        self.avg: dict[ArrowType, tuple[int, int, int]] = {}
        self.keys: dict[int, pygame.Surface] = {}       # sprites from Keys.png (index = Key value)
        self.cache: dict[tuple, pygame.Surface] = {}
        self.info = ''
        self._load()
        self._load_keys()
        for t, surf in self.base.items():
            self.avg[t] = _average_color(surf)

    @staticmethod
    def _open(*names: str) -> pygame.Surface | None:
        """Loads the first image found among `names` (script folder, then current folder)."""
        for name in names:
            for folder in (HERE, Path.cwd()):
                p = folder / name
                if p.exists():
                    return pygame.image.load(str(p)).convert_alpha()
        return None

    def _load_keys(self):
        """Keys.png: grid of SPRITE x SPRITE sprites, in the order of the Key enum, shifted by 1
        (no sprite for NotDefined: the first sprite is A)."""
        sheet = self._open('Keys.png')
        if sheet is None:
            self.info += ' ; Keys.png not found: only the base key sprite is shown, no letters on walls and no B / N on Light bulbs'
            return
        cols = max(1, sheet.get_width() // SPRITE)
        for k in Key:
            if k == Key.NotDefined:
                continue
            idx = int(k) - 1
            rect = pygame.Rect((idx % cols) * SPRITE, (idx // cols) * SPRITE, SPRITE, SPRITE)
            if sheet.get_rect().contains(rect):
                self.keys[int(k)] = sheet.subsurface(rect).copy()
        self.info += f' ; Keys.png loaded ({len(self.keys)} keys)'

    def _load(self):
        sheet = self._open('Arrows.png', 'tiles.png')      # tiles.png: old name, tolerated
        if sheet is None:
            self.info = 'Arrows.png not found: fallback sprites'
            for t in DRAWABLE:
                self.base[t] = _placeholder(t)
            return

        cols = max(1, sheet.get_width() // SPRITE)
        offset = SHEET_ID_OFFSET
        if offset is None:
            first = sheet.subsurface((0, 0, SPRITE, SPRITE))
            offset = 0 if pygame.mask.from_surface(first).count() == 0 else -1
        self.info = f'Arrows.png loaded (index = id{offset:+d})' if offset else 'Arrows.png loaded (index = id)'
        for t in DRAWABLE:
            idx = int(t) + offset
            rect = pygame.Rect((idx % cols) * SPRITE, (idx // cols) * SPRITE, SPRITE, SPRITE)
            if idx >= 0 and sheet.get_rect().contains(rect):
                self.base[t] = sheet.subsurface(rect).copy()
            else:
                self.base[t] = _placeholder(t)

    def get(self, t: ArrowType, direction, flipped, size: int, color: int = 0, bright: bool = False,
            key: int = 0, wall_color: int = 0, wall_letter: int = 0):
        base = self.base.get(t)
        if base is None:                       # Empty and TODO: no sprite, ignored
            return None
        colored = t in COLORED_TYPES
        keyed = t in KEYBOARD_TYPES
        overlay = self.keys.get(int(key)) if keyed else None   # NotDefined / unknown: base sprite only
        walled = t in WALL_TYPES
        wall_key = (self.keys.get(int(wall_letter))        # wall letter / digit: Keys.png sprite (A-Z, 0-9 only)
                    if walled and WALL_LETTER_FIRST <= int(wall_letter) <= WALL_LETTER_LAST else None)
        cache_key = (t, int(direction), bool(flipped), size, int(color) if colored else 0,
                     bool(bright) if colored else False, int(key) if keyed else 0,
                     int(wall_color) if walled else 0, int(wall_letter) if walled else 0)
        key = cache_key
        surf = self.cache.get(key)
        if surf is None:
            surf = pygame.transform.smoothscale(base, (size, size)) if size != SPRITE else base.copy()
            key_spr = None
            if overlay is not None:
                key_spr = pygame.transform.smoothscale(overlay, (size, size)) if size != SPRITE else overlay.copy()
                if KEY_FOLLOWS_DIRECTION:
                    surf.blit(key_spr, (0, 0))
                    key_spr = None
            if colored and int(color) != Color.Undefined:
                # the tile stays intact: it is drawn on a background of the chosen color
                bg = pygame.Surface((size, size), pygame.SRCALPHA)
                bg.fill((*display_rgb(color), 255))
                bg.blit(surf, (0, 0))
                surf = bg
            tint = wall_rgb(wall_color) if walled and int(wall_color) != WallColor.White else None
            if tint is not None:
                # tint: silhouette in the color (same alpha as the sprite) drawn on top at WALL_TINT_ALPHA / 255
                layer = surf.copy()
                layer.fill((255, 255, 255, 255), special_flags=pygame.BLEND_RGB_MAX)
                layer.fill((*tint, 255), special_flags=pygame.BLEND_RGBA_MULT)
                layer.fill((255, 255, 255, WALL_TINT_ALPHA), special_flags=pygame.BLEND_RGBA_MULT)
                surf.blit(layer, (0, 0))
            wall_spr = None
            if wall_key is not None:
                wall_spr = pygame.transform.smoothscale(wall_key, (size, size)) if size != SPRITE else wall_key.copy()
                if KEY_FOLLOWS_DIRECTION:
                    surf.blit(wall_spr, (0, 0))
                    wall_spr = None
            if flipped:
                surf = pygame.transform.flip(surf, True, False)    # horizontal mirror, then rotation
            if int(direction):
                surf = pygame.transform.rotate(surf, -90 * int(direction))   # clockwise
            if key_spr is not None:                # key drawn on top, after rotation (stays upright)
                surf.blit(key_spr, (0, 0))
            if wall_spr is not None:               # wall letter: same principle, on top of the tint
                surf.blit(wall_spr, (0, 0))
            if colored and size >= 8:
                # letter B (Bright) or N (Normal): Keys.png sprite at half the cell size, anchored at the
                # bottom right, added after the rotation so it stays upright
                mode_spr = self.keys.get(int(Key.B if bright else Key.N))
                if mode_spr is not None:
                    half = max(1, size // 2)
                    surf.blit(pygame.transform.smoothscale(mode_spr, (half, half)), (size - half, size - half))
            self.cache[key] = surf
        return surf


# --------------------------------------------------------------------------- editor

def line_cells(a, b):
    x0, y0 = a
    x1, y1 = b
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        yield x0, y0
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


HELP = [
    'Left click: place     Middle click (or Space + left click): pan     R (held): erase',
    'Wheel: zoom     Arrows: move (Shift = fast)     Home: back to 0,0',
    'ZQSD / WASD: orient     T / Shift+T: rotate     F: flip     P: eyedropper',
    'Notes: Tab / Shift+Tab = instrument     N / Shift+N = note     PgUp / PgDn = octave     (or the panel on the right)',
    'Light_bulb1 / Light_bulb2: choose the color and Normal / Bright in the panel on the right',
    'Key: K / Shift+K = next / previous key     (or the panel on the right)',
    'Wall: M / Shift+M = next / previous color     L / Shift+L = next / previous letter (none, A-Z, 0-9)     (or the panel on the right)',
    'Text (Source / Target / Script_block / Message): Enter or click in the panel = type, Esc = confirm',
    '   Right click on a text arrow: edit its text     Ctrl+Enter = confirm     Enter in the text = new line',
    '   Shift+arrows / mouse drag / double click (word) / triple click (line) = select     Ctrl+A / C / X / V = all / copy / cut / paste',
    '   Ctrl+Z / Ctrl+Y = undo / redo     Ctrl+Left / Right / Backspace / Delete = by word     Home / End / PgUp / PgDn / Ctrl+Home / Ctrl+End',
    '   Source / Target / Script_block = JavaScript (highlighting, line numbers, bracket matching, Import / Export .js buttons); Message = plain text',
    '   JavaScript: Tab / Shift+Tab = indent / dedent lines     Ctrl+/ = comment lines     Enter keeps the indentation and opens {} blocks',
    'Z / Ctrl+Z: undo     Y / Ctrl+Y: redo',
    'Select: hold E, move the mouse, release E (no click). E alone: deselect everything',
    'Selection mode (active while an arrow is selected): hold Shift+E = add     Ctrl+E = remove (no click)',
    '   C copy     X cut     V paste (under the cursor)     Backspace: delete',
    'Ctrl+S: save     Ctrl+O: open     Ctrl+C: copy the code     Ctrl+V: paste a code',
    'H: show / hide this help',
]

# Orientation by physical key position (ZQSD on AZERTY, WASD on QWERTY)
ORIENT_SCANCODES = {pygame.KSCAN_W: 0, pygame.KSCAN_D: 1, pygame.KSCAN_S: 2, pygame.KSCAN_A: 3}
SELECT_COLOR = (80, 200, 255)


class Editor:
    def __init__(self, path: str | None = None):
        pygame.init()
        pygame.display.set_caption('Arrows Editor')
        pygame.display.set_mode((1280, 800), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 22)
        self.sprites = Sprites()

        self.world = Map()
        self.world.version = 5
        self.rendered: dict[tuple[int, int], tuple[float, pygame.Surface | None]] = {}
        self.mini: dict[tuple[int, int], pygame.Surface | None] = {}

        self.cam_x = 0.0
        self.cam_y = 0.0
        self.zoom_i = ZOOMS.index(16)
        self.sel = DRAWABLE[0]
        self.direction = Direction.North
        self.flipped = False
        self.note_instrument = int(Instrument.Piano)     # settings used to place a Music_Arrow arrow
        self.note_pitch = 0
        self.note_octave = 4
        self.display_color = int(Color.Undefined)        # settings used to place a Light_bulb1 / Light_bulb2 (undefined by default)
        self.display_bright = False
        self.key_sel = int(Key.NotDefined)               # key used to place a Key arrow
        self.wall_color_sel = int(WallColor.White)       # settings used to place a Wall
        self.wall_letter_sel = 0                         # 0 = no letter, otherwise 1 (A) to 36 (9)
        # text used to place a Source / Target / Script_block / Message arrow (text_sel / text_cursor are views on it),
        # with cursor, selection and undo history
        self.tb = TextBuffer(TEXT_MAX_BYTES)
        self.text_scroll = 0
        self.text_editing = False                        # True: the keyboard is captured by the input area
        self.text_target: tuple[int, int] | None = None  # cell whose text is being edited (right click)
        self.text_dragging = False                       # mouse button held in the input area (selecting)
        self.text_click = (0.0, (0, 0), 0)               # time, position and count of the last clicks (double / triple click)
        self.char_w: dict[str, int] = {}
        self.overlay_cache: dict[tuple, pygame.Surface] = {}
        self.small_font = pygame.font.Font(None, 20)
        try:                                             # monospace font for JavaScript code
            self.code_font = pygame.font.SysFont('consolas,menlo,dejavusansmono,liberationmono,couriernew,monospace', 15)
        except Exception:
            self.code_font = self.small_font
        self.js_cache: tuple[str, bytearray] | None = None
        self.js_dir = HERE                               # last folder used to import / export .js files

        self.mouse_pos = pygame.mouse.get_pos()
        self.stroke: dict | None = None
        self.stroke_mode = None
        self.last_cell = None
        self.panning = False
        self.space = False
        self.selection: set[tuple[int, int]] = set()
        self.clipboard: list = []                 # (dx, dy, state) relative to the top-left corner
        self.e_held = False
        self.e_mode = 'replace'                   # replace / add / remove
        self.sel_anchor = None                    # starting cell of the selection rectangle
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self.show_help = False
        self.status = ('', 0.0)
        self.running = True
        self.path = Path(path) if path else HERE / 'World.json'

        self.say(self.sprites.info)
        if path and self.path.exists():
            self.load_file()

    # ---- utilities -----------------------------------------------------

    @property
    def scale(self) -> float:
        return ZOOMS[self.zoom_i]

    @property
    def surface(self) -> pygame.Surface:
        return pygame.display.get_surface()

    def say(self, text: str, seconds: float = 4.0):
        self.status = (text, time.time() + seconds)

    def in_panel(self, pos) -> bool:
        return pos[0] < PANEL_W

    def screen_to_world(self, pos) -> tuple[float, float]:
        W, H = self.surface.get_size()
        s = self.scale
        return (pos[0] - W / 2) / s + self.cam_x, (pos[1] - H / 2) / s + self.cam_y

    def cell_at(self, pos) -> tuple[int, int]:
        wx, wy = self.screen_to_world(pos)
        return math.floor(wx), math.floor(wy)

    def get_arrow(self, x: int, y: int) -> Arrow | None:
        chunk = self.world.chunks.get((x // CHUNK, y // CHUNK))
        return chunk.get(x % CHUNK, y % CHUNK) if chunk else None   # without creating a chunk

    def state_at(self, x: int, y: int):
        a = self.get_arrow(x, y)
        if a is None or a.type == ArrowType.Empty_cell:
            return None
        note = ((int(a.instrument), int(a.pitch), int(a.octave))
                if a.type == ArrowType.Music_Arrow else None)
        disp = (int(a.color), bool(a.bright)) if a.type in COLORED_TYPES else None
        keyv = int(a.key) if a.type in KEYBOARD_TYPES else None
        logf = int(a.logger_flag) if a.type == ArrowType.Message else None
        wall = (int(a.wall_color), int(a.wall_letter)) if a.type in WALL_TYPES else None
        return (int(a.type), int(a.direction), bool(a.flipped), a.string, note, disp, keyv, logf, wall)

    def make_arrow(self, state) -> Arrow:
        """Builds an arrow from a state: Arrow.text() for text types, Arrow.wall() for walls."""
        t, direction, flipped, string = ArrowType(state[0]), Direction(state[1]), state[2], state[3]
        if t in TEXT_TYPES:
            try:
                return Arrow.text(t, string, direction, flipped)
            except ValueError:                    # imported text longer than the input limit
                pass
        if t in WALL_TYPES and len(state) > 8 and state[8] is not None:
            try:
                return Arrow.wall(state[8][0], state[8][1], direction, flipped)
            except ValueError:                    # unknown color / letter (imported map): fall back below
                pass
        return Arrow(t, direction, flipped, string)

    def apply_state(self, x: int, y: int, state):
        key = (x // CHUNK, y // CHUNK)
        if state is None:
            chunk = self.world.chunks.get(key)
            if chunk:
                chunk.set(x % CHUNK, y % CHUNK, Arrow())
        else:
            arrow = self.make_arrow(state)
            if state[4] is not None:
                arrow.instrument, arrow.pitch, arrow.octave = state[4]
            if state[5] is not None:
                arrow.color, arrow.bright = state[5]
            if len(state) > 6 and state[6] is not None:
                arrow.key = state[6]
            if len(state) > 7 and state[7] is not None:
                arrow.logger_flag = state[7]
            if len(state) > 8 and state[8] is not None:
                arrow.wall_color, arrow.wall_letter = state[8]
            self.world.set(x, y, arrow)
        self.rendered.pop(key, None)
        self.mini.pop(key, None)

    def reset_caches(self):
        self.rendered.clear()
        self.mini.clear()

    # ---- editing ---------------------------------------------------------

    def begin_stroke(self, mode: str, pos):
        self.text_target = None
        self.stroke = {}
        self.stroke_mode = mode
        self.last_cell = self.cell_at(pos)
        self.paint(self.last_cell)

    def paint(self, cell):
        x, y = cell
        if self.stroke_mode == 'erase':
            new = None
        else:
            note = self.note_state() if self.sel == ArrowType.Music_Arrow else None
            disp = (self.display_color, self.display_bright) if self.sel in COLORED_TYPES else None
            keyv = self.key_sel if self.sel in KEYBOARD_TYPES else None
            txt = self.text_sel if self.sel in TEXT_TYPES else ''
            logf = LOGGER_DEFAULT_FLAG if self.sel == ArrowType.Message else None
            wall = (self.wall_color_sel, self.wall_letter_sel) if self.sel in WALL_TYPES else None
            new = (int(self.sel), int(self.direction), self.flipped, txt, note, disp, keyv, logf, wall)
        old = self.state_at(x, y)
        if old == new:
            return
        if cell not in self.stroke:
            self.stroke[cell] = [old, new]
        else:
            self.stroke[cell][1] = new
        self.apply_state(x, y, new)

    def push_changes(self, changes: dict):
        if changes:
            self.undo_stack.append(changes)
            self.undo_stack = self.undo_stack[-500:]
            self.redo_stack.clear()

    def end_stroke(self):
        if self.stroke:
            self.push_changes({c: v for c, v in self.stroke.items() if v[0] != v[1]})
            self.prune_selection()
        self.stroke = None
        self.stroke_mode = None
        self.last_cell = None

    def undo(self):
        if not self.undo_stack:
            return
        changes = self.undo_stack.pop()
        for (x, y), (old, _new) in changes.items():
            self.apply_state(x, y, old)
        self.redo_stack.append(changes)
        self.prune_selection()

    def redo(self):
        if not self.redo_stack:
            return
        changes = self.redo_stack.pop()
        for (x, y), (_old, new) in changes.items():
            self.apply_state(x, y, new)
        self.undo_stack.append(changes)
        self.prune_selection()

    def pipette(self):
        if self.in_panel(self.mouse_pos) or self.over_note_panel(self.mouse_pos):
            return
        a = self.get_arrow(*self.cell_at(self.mouse_pos))
        if a is not None and a.type in self.sprites.base:
            self.sel, self.direction, self.flipped = a.type, a.direction, bool(a.flipped)
            if a.type == ArrowType.Music_Arrow:
                self.note_instrument, self.note_pitch, self.note_octave = int(a.instrument), int(a.pitch), int(a.octave)
            elif a.type in COLORED_TYPES:
                self.display_color, self.display_bright = int(a.color), bool(a.bright)
            elif a.type in KEYBOARD_TYPES:
                self.key_sel = int(a.key)
            elif a.type in TEXT_TYPES:
                self.text_sel = a.string
                self.text_cursor, self.text_scroll = len(a.string), 0
            elif a.type in WALL_TYPES:
                self.wall_color_sel, self.wall_letter_sel = int(a.wall_color), int(a.wall_letter)
            self.text_target = None

    # ---- selection -------------------------------------------------------

    def prune_selection(self):
        """Removes from the selection the cells that no longer contain an arrow (mode ends if it becomes empty)."""
        if self.selection:
            self.selection = {c for c in self.selection if self.state_at(*c) is not None}

    def e_press(self, ctrl: bool, shift: bool):
        """E pressed: the rectangle's corner is fixed under the cursor, without a click. The rectangle follows the mouse
        while E is held and the selection is applied when E is released.
        Ctrl/Shift only count if a selection already exists; E alone deselects everything and
        then lets you draw a new selection."""
        self.e_held = True
        if self.selection and ctrl:
            self.e_mode = 'remove'
        elif self.selection and shift:
            self.e_mode = 'add'
        else:
            self.e_mode = 'replace'
            self.selection.clear()
        self.sel_anchor = None
        self.begin_selection_rect()

    def begin_selection_rect(self):
        """Fixes the starting corner under the cursor (if the cursor is over a panel, it will be as soon as it leaves it)."""
        if (self.e_held and self.sel_anchor is None and not self.in_panel(self.mouse_pos)
                and not self.over_note_panel(self.mouse_pos)):
            self.sel_anchor = self.cell_at(self.mouse_pos)

    def e_release(self):
        """E released: the current rectangle is confirmed (idempotent)."""
        self.e_held = False
        if self.sel_anchor is not None:
            self.finish_selection()

    def selection_rect(self):
        if self.sel_anchor is None:
            return None
        (x0, y0), (x1, y1) = self.sel_anchor, self.cell_at(self.mouse_pos)
        return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)

    def finish_selection(self):
        rect = self.selection_rect()
        self.sel_anchor = None
        if rect is None:
            return
        xa, ya, xb, yb = rect
        cells = set()
        for (cx, cy), chunk in self.world.chunks.items():
            if (cx + 1) * CHUNK - 1 < xa or cx * CHUNK > xb or (cy + 1) * CHUNK - 1 < ya or cy * CHUNK > yb:
                continue
            for idx, a in enumerate(chunk.arrows):
                if a.type == ArrowType.Empty_cell:
                    continue
                x, y = cx * CHUNK + idx % CHUNK, cy * CHUNK + idx // CHUNK
                if xa <= x <= xb and ya <= y <= yb:
                    cells.add((x, y))
        if self.e_mode == 'add':
            self.selection |= cells
        elif self.e_mode == 'remove':
            self.selection -= cells
        else:
            self.selection = cells
        if not cells:
            if (xa, ya) != (xb, yb):          # a simple press of E (1 cell) just deselects
                self.say('No arrow in this area')
        else:
            self.say(f'{len(self.selection)} arrow(s) selected', 2.0)

    def copy_selection(self) -> bool:
        items = [(c, self.state_at(*c)) for c in self.selection]
        items = [(c, st) for c, st in items if st is not None]
        if not items:
            self.say('Nothing to copy (empty selection)')
            return False
        x0 = min(c[0] for c, _ in items)
        y0 = min(c[1] for c, _ in items)
        self.clipboard = [(x - x0, y - y0, st) for (x, y), st in items]
        self.say(f'{len(items)} arrow(s) copied')
        return True

    def paste_selection(self):
        if not self.clipboard:
            self.say('Nothing to paste')
            return
        if self.in_panel(self.mouse_pos) or self.over_note_panel(self.mouse_pos):
            return
        ox, oy = self.cell_at(self.mouse_pos)
        changes, new_sel = {}, set()
        for dx, dy, st in self.clipboard:
            x, y = ox + dx, oy + dy
            old = self.state_at(x, y)
            if old != st:
                changes[(x, y)] = [old, st]
                self.apply_state(x, y, st)
            new_sel.add((x, y))
        self.push_changes(changes)
        self.selection = new_sel

    def delete_selection(self):
        changes = {}
        for x, y in self.selection:
            old = self.state_at(x, y)
            if old is not None:
                changes[(x, y)] = [old, None]
                self.apply_state(x, y, None)
        self.push_changes(changes)
        self.selection.clear()

    def cut_selection(self):
        if self.copy_selection():
            self.delete_selection()

    # ---- notes -----------------------------------------------------------

    def note_state(self) -> tuple[int, int, int]:
        return (self.note_instrument, self.note_pitch, self.note_octave)

    def set_instrument(self, instrument: int):
        """Changes instrument, clamping the octave into the instrument's range."""
        self.note_instrument = int(instrument)
        lo, hi = instrument_range(instrument)
        self.note_octave = max(lo, min(hi, self.note_octave))

    def set_octave(self, octave: int):
        lo, hi = instrument_range(self.note_instrument)
        if lo <= octave <= hi:
            self.note_octave = octave

    def note_tool_key(self, key: int, shift: bool):
        """Keyboard shortcuts for notes: they also select the Music_Arrow tool."""
        self.sel = ArrowType.Music_Arrow
        step = -1 if shift else 1
        if key == pygame.K_TAB:
            try:
                i = (NOTE_INSTRUMENTS.index(self.note_instrument) + step) % len(NOTE_INSTRUMENTS)
            except ValueError:
                i = 0
            self.set_instrument(NOTE_INSTRUMENTS[i])
        elif key == pygame.K_n:
            self.note_pitch = (self.note_pitch + step) % 12
        elif key == pygame.K_PAGEUP:
            self.set_octave(self.note_octave + 1)
        elif key == pygame.K_PAGEDOWN:
            self.set_octave(self.note_octave - 1)
        self.say(note_text(self.note_state()), 2.0)

    def key_tool_key(self, shift: bool):
        """K / Shift+K: selects the Key tool and moves to the next / previous key."""
        self.sel = ArrowType.Key
        self.key_sel = (self.key_sel + (-1 if shift else 1)) % len(KEY_LIST)
        self.say(f'Key: {key_label(self.key_sel)}', 2.0)

    def wall_tool_key(self, key: int, shift: bool):
        """M / Shift+M: next / previous wall color. L / Shift+L: next / previous letter
        (none, A to Z, 0 to 9). They also select the Wall tool."""
        self.sel = ArrowType.Wall
        step = -1 if shift else 1
        if key == pygame.K_m:
            self.wall_color_sel = (self.wall_color_sel + step) % len(WALL_COLOR_LIST)
        else:
            self.wall_letter_sel = (self.wall_letter_sel + step) % (WALL_LETTER_LAST + 1)
        self.say(f'Wall: {wall_text(self.wall_color_sel, self.wall_letter_sel)}', 2.0)

    # ---- text (Source / Target / Script_block / Message) -------

    @property
    def text_sel(self) -> str:
        return self.tb.text

    @text_sel.setter
    def text_sel(self, value: str):
        self.tb.load(value)                       # new content: cursor at the end, selection and history reset

    @property
    def text_cursor(self) -> int:
        return self.tb.cursor

    @text_cursor.setter
    def text_cursor(self, value: int):
        self.tb.move_to(value)

    def char_width(self, ch: str) -> int:
        code = self.sel in JS_TYPES
        w = self.char_w.get((code, ch))
        if w is None:
            w = self.char_w[(code, ch)] = (self.code_font if code else self.small_font).size(ch)[0]
        return w

    def gutter_w(self) -> int:
        """Width of the line-number column (JavaScript only)."""
        if self.sel not in JS_TYPES:
            return 0
        digits = len(str(self.tb.text.count('\n') + 1))
        return self.char_width('0') * max(2, digits) + 12

    def text_lines(self) -> list:
        """Visual lines (start, end, paragraph end): word wrapping adapted to the font and to the gutter."""
        return self.tb.lines(TP_WRAP_W - self.gutter_w(), self.char_width, self.sel in JS_TYPES)

    def cursor_line(self, lines) -> int:
        return self.tb.cursor_line(lines)

    def text_scroll_to_cursor(self):
        n = self.cursor_line(self.text_lines())
        if n < self.text_scroll:
            self.text_scroll = n
        elif n >= self.text_scroll + TP_VIS:
            self.text_scroll = n - TP_VIS + 1

    def text_scroll_by(self, delta: int):
        most = max(0, len(self.text_lines()) - TP_VIS)
        self.text_scroll = max(0, min(most, self.text_scroll + delta))

    def text_insert(self, s: str):
        """Typed text (replaces the selection; the byte limit is reported)."""
        self.tb.type_text(s, self.sel in JS_TYPES)
        if self.tb.limit_hit:
            self.say('Text too long: limit reached', 2.0)
        self.text_scroll_to_cursor()

    def clipboard_text(self) -> str:
        try:
            import tkinter
            root = tkinter.Tk()
            root.withdraw()
            try:
                return root.clipboard_get()
            finally:
                root.destroy()
        except Exception as exc:
            self.say(f'Clipboard unavailable ({type(exc).__name__})')
            return ''

    def clipboard_set(self, txt: str) -> bool:
        try:
            import tkinter
            root = tkinter.Tk()
            root.withdraw()
            try:
                root.clipboard_clear()
                root.clipboard_append(txt)
                root.update()
            finally:
                root.destroy()
            return True
        except Exception as exc:
            self.say(f'Clipboard unavailable ({type(exc).__name__})')
            return False

    def text_copy(self, cut: bool = False):
        """Ctrl+C / Ctrl+X: copies (and removes) the selected text."""
        if not self.tb.selection:
            self.say('Nothing selected', 1.5)
            return
        if self.clipboard_set(self.tb.selected_text()) and cut:
            self.tb.delete_back()                 # removes the selection

    def handle_text_key(self, e):
        """Special keys while typing (characters arrive via TEXTINPUT)."""
        mods = e.mod
        ctrl = bool(mods & (pygame.KMOD_CTRL | pygame.KMOD_META)) and not (mods & pygame.KMOD_ALT)   # AltGr = Ctrl+Alt on Windows
        shift = bool(mods & pygame.KMOD_SHIFT)
        k, tb, js = e.key, self.tb, self.sel in JS_TYPES
        enter = k in (pygame.K_RETURN, pygame.K_KP_ENTER)
        if k == pygame.K_ESCAPE or (ctrl and enter):
            self.end_text_edit()
            return
        if enter:
            tb.newline(js)
        elif k == pygame.K_TAB:
            if js:
                tb.tab(shift)
        elif ctrl and k == pygame.K_a:
            tb.select_all()
        elif ctrl and k == pygame.K_c:
            self.text_copy()
        elif ctrl and k == pygame.K_x:
            self.text_copy(cut=True)
        elif ctrl and k == pygame.K_v:
            tb.insert(self.clipboard_text())
            if tb.limit_hit:
                self.say('Text too long: limit reached', 2.0)
        elif ctrl and k == pygame.K_z:
            tb.redo() if shift else tb.undo()
        elif ctrl and k == pygame.K_y:
            tb.redo()
        elif ctrl and js and (k in (pygame.K_SLASH, pygame.K_KP_DIVIDE) or getattr(e, 'unicode', '') == '/'):
            tb.toggle_comment()
        elif k == pygame.K_BACKSPACE:
            tb.delete_back(ctrl)
        elif k == pygame.K_DELETE:
            tb.delete_forward(ctrl)
        elif k == pygame.K_LEFT:
            tb.move_left(ctrl, shift)
        elif k == pygame.K_RIGHT:
            tb.move_right(ctrl, shift)
        elif k in (pygame.K_UP, pygame.K_DOWN):
            tb.move_vertical(-1 if k == pygame.K_UP else 1, self.text_lines(), shift)
        elif k in (pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            tb.move_vertical(-TP_VIS if k == pygame.K_PAGEUP else TP_VIS, self.text_lines(), shift)
        elif k in (pygame.K_HOME, pygame.K_END):
            tb.home_end(k == pygame.K_HOME, self.text_lines(), shift, ctrl)
        self.text_scroll_to_cursor()

    def begin_text_edit(self, cursor: int | None = None, move: bool = True):
        """Starts typing: the cursor goes to `cursor` (default: end of the text) unless `move` is False."""
        if not self.text_editing:
            self.text_editing = True
            pygame.key.start_text_input()
            pygame.key.set_repeat(400, 35)
        if move:
            self.tb.move_to(len(self.tb.text) if cursor is None else cursor)
        self.text_scroll_to_cursor()

    def end_text_edit(self):
        """Leaves typing; if a cell is targeted (right click), its text is updated."""
        if not self.text_editing:
            return
        self.text_editing = False
        self.text_dragging = False
        pygame.key.stop_text_input()
        pygame.key.set_repeat()
        self.commit_text_target()

    def commit_text_target(self):
        """Applies the input area text to the targeted arrow (undoable with Ctrl+Z)."""
        if self.text_target is None:
            return
        x, y = self.text_target
        old = self.state_at(x, y)
        if old is None or ArrowType(old[0]) not in TEXT_TYPES:
            self.text_target = None
            return
        if old[3] == self.text_sel:
            return
        new = old[:3] + (self.text_sel,) + old[4:]
        self.push_changes({(x, y): [old, new]})
        self.apply_state(x, y, new)
        self.say(f'Text updated (cell {x}, {y})', 2.0)

    def edit_text_at(self, pos):
        """Right click on a text arrow: loads its text into the panel and starts typing."""
        cell = self.cell_at(pos)
        a = self.get_arrow(*cell)
        if a is None or a.type not in TEXT_TYPES:
            self.say('Right click: no text arrow here', 2.0)
            return
        self.end_text_edit()                      # confirms any previous typing
        self.sel = a.type
        self.text_target = cell
        self.text_sel = a.string
        self.text_scroll = 0
        self.begin_text_edit()
        self.say(f'Editing the text of cell {cell[0]}, {cell[1]} (Esc: confirm)', 3.0)

    def js_colors(self) -> bytearray:
        if self.js_cache is None or self.js_cache[0] != self.text_sel:
            self.js_cache = (self.text_sel, js_highlight(self.text_sel))
        return self.js_cache[1]

    def js_dialog(self, save: bool, initial: str = '') -> str | None:
        """File dialog (tkinter, like for the clipboard)."""
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        try:
            root.attributes('-topmost', True)
        except Exception:
            pass
        try:
            kw = dict(parent=root, initialdir=str(self.js_dir),
                      filetypes=[('JavaScript', ('*.js', '*.mjs')), ('All files', '*.*')])
            if save:
                path = filedialog.asksaveasfilename(defaultextension='.js', initialfile=initial, **kw)
            else:
                path = filedialog.askopenfilename(**kw)
        finally:
            root.destroy()
        return path or None

    def import_js(self):
        """Replaces the panel text with the contents of a .js file (Source / Target / Script_block)."""
        if self.sel not in JS_TYPES:
            return
        try:
            path = self.js_dialog(False)
        except Exception as exc:
            self.say(f'Dialog unavailable ({type(exc).__name__})')
            return
        if not path:
            return
        p = Path(path)
        try:
            code = clean_text(p.read_text(encoding='utf-8-sig'))
        except (OSError, UnicodeDecodeError) as exc:
            self.say(f'Cannot read: {exc}')
            return
        size = len(code.encode('utf-8'))
        if size > TEXT_MAX_BYTES:
            self.say(f'{p.name} is too long ({size} bytes, maximum {TEXT_MAX_BYTES})', 5.0)
            return
        self.js_dir = p.parent
        self.tb.replace_all(code, cursor=0)           # undoable (Ctrl+Z while typing)
        self.text_scroll = 0
        self.say(f'Imported: {p.name} ({size} bytes)' + ('' if self.text_target is None else ' (click Apply)'), 4.0)

    def export_js(self):
        """Writes the panel text to a .js file (UTF-8, \\n line endings)."""
        if self.sel not in JS_TYPES:
            return
        if not self.text_sel:
            self.say('Nothing to export: the text is empty', 2.5)
            return
        name = self.sel.name.lower()
        if self.text_target is not None:
            name += f'_{self.text_target[0]}_{self.text_target[1]}'
        try:
            path = self.js_dialog(True, name + '.js')
        except Exception as exc:
            self.say(f'Dialog unavailable ({type(exc).__name__})')
            return
        if not path:
            return
        p = Path(path)
        try:
            p.write_text(self.text_sel, encoding='utf-8', newline='\n')
        except OSError as exc:
            self.say(f'Cannot write: {exc}')
            return
        self.js_dir = p.parent
        self.say(f'Exported: {p.name}', 4.0)

    def text_layout(self, W: int) -> dict:
        """Positions of the text panel: input area, byte counter, Clear / Apply buttons."""
        x0, y0 = max(PANEL_W + 10, W - TP_W - 10), 64
        ix = x0 + NP_PAD
        box = pygame.Rect(ix, y0 + NP_PAD + 20, TP_INNER, TP_BOX_H)
        y = box.bottom + 4
        counter = (ix, y)
        y += 18 + NP_GAP
        bw = (TP_INNER - NP_GAP) // 2
        buttons = [('clear', pygame.Rect(ix, y, bw, NP_BTN_H)),
                   ('apply', pygame.Rect(ix + bw + NP_GAP, y, bw, NP_BTN_H))]
        y += NP_BTN_H
        if self.sel in JS_TYPES:                      # 2nd row: .js file import / export
            y += NP_GAP
            buttons += [('import', pygame.Rect(ix, y, bw, NP_BTN_H)),
                        ('export', pygame.Rect(ix + bw + NP_GAP, y, bw, NP_BTN_H))]
            y += NP_BTN_H
        y += NP_PAD
        return {'rect': pygame.Rect(x0, y0, TP_W, y - y0), 'box': box, 'counter': counter, 'buttons': buttons}

    def cursor_from_pos(self, pos, box) -> int:
        lines = self.text_lines()
        n = max(0, min(len(lines) - 1, (pos[1] - box.y - 4) // TP_LINE_H + self.text_scroll))
        s, e, last = lines[n]
        text = self.tb.text
        x, acc, i = pos[0] - box.x - 4 - self.gutter_w(), 0, s
        while i < e:
            w = self.char_width(text[i])
            if acc + w / 2 > x:
                break
            acc += w
            i += 1
        if not last and i == e and e > s:
            i = e - 1
        return i

    def text_box_click(self, pos, box):
        """Click in the input area: caret; Shift+click extends the selection; double click = word; triple click = line;
        dragging selects."""
        now = time.time()
        t0, p0, count = self.text_click
        same = now - t0 < 0.45 and abs(pos[0] - p0[0]) <= 4 and abs(pos[1] - p0[1]) <= 4
        count = count % 3 + 1 if same else 1                 # 1 -> 2 -> 3 -> back to 1
        self.text_click = (now, pos, count)
        idx = self.cursor_from_pos(pos, box)
        self.begin_text_edit(move=False)
        if count == 2:
            self.tb.select_range(*self.tb.word_at(idx))
        elif count == 3:
            self.tb.select_range(*self.tb.line_at(idx))
        else:
            self.tb.move_to(idx, bool(pygame.key.get_mods() & pygame.KMOD_SHIFT))
        self.text_dragging = count == 1
        self.text_scroll_to_cursor()

    def text_drag(self, pos):
        """Mouse moved with the button held in the input area: extends the selection (scrolls past the edges)."""
        box = self.text_layout(self.surface.get_width())['box']
        if pos[1] < box.y:
            self.text_scroll_by(-1)
        elif pos[1] > box.bottom:
            self.text_scroll_by(1)
        y = max(box.y + 4, min(box.bottom - 4, pos[1]))
        self.tb.move_to(self.cursor_from_pos((pos[0], y), box), extend=True)

    def click_text_panel(self, pos):
        lay = self.text_layout(self.surface.get_width())
        if lay['box'].collidepoint(pos):
            self.text_box_click(pos, lay['box'])
            return
        for name, rect in lay['buttons']:
            if rect.collidepoint(pos):
                if name == 'clear':
                    self.tb.replace_all('')               # undoable (Ctrl+Z while typing)
                    self.text_scroll = 0
                elif name == 'import':
                    self.import_js()
                elif name == 'export':
                    self.export_js()
                elif self.text_target is not None:
                    self.commit_text_target()
                else:
                    self.say('No cell targeted: right click on a text arrow', 2.5)
                return

    def note_layout(self, W: int) -> dict:
        """Positions of the notes panel buttons (instruments, notes, octaves)."""
        x0, y0 = max(PANEL_W + 10, W - NP_W - 10), 64
        ix = x0 + NP_PAD
        y = y0 + NP_PAD + 20
        rows = (len(NOTE_INSTRUMENTS) + 1) // 2
        instruments = []
        for n, inst in enumerate(NOTE_INSTRUMENTS):
            col, row = n // rows, n % rows
            instruments.append((pygame.Rect(ix + col * (NP_INST_W + NP_GAP), y + row * (NP_INST_H + NP_GAP),
                                            NP_INST_W, NP_INST_H), int(inst)))
        y += rows * (NP_INST_H + NP_GAP) + 6
        bw = (NP_INNER - 5 * NP_GAP) // 6
        pitches = [(pygame.Rect(ix + (i % 6) * (bw + NP_GAP), y + (i // 6) * (NP_BTN_H + NP_GAP), bw, NP_BTN_H), i)
                   for i in range(12)]
        y += 2 * (NP_BTN_H + NP_GAP) + 6
        bw = (NP_INNER - 7 * NP_GAP) // 8
        octaves = [(pygame.Rect(ix + o * (bw + NP_GAP), y, bw, NP_BTN_H), o) for o in range(8)]
        y += NP_BTN_H + NP_PAD
        return {'rect': pygame.Rect(x0, y0, NP_W, y - y0),
                'instruments': instruments, 'pitches': pitches, 'octaves': octaves}

    # ---- colors (Light_bulb1 / Light_bulb2) -------------------------

    def display_layout(self, W: int) -> dict:
        """Positions of the colors panel buttons (7 colors + Normal / Bright)."""
        x0, y0 = max(PANEL_W + 10, W - NP_W - 10), 64
        ix = x0 + NP_PAD
        y = y0 + NP_PAD + 20
        colors = []
        for n, c in enumerate(COLOR_LIST):
            col, row = n % 2, n // 2
            colors.append((pygame.Rect(ix + col * (NP_INST_W + NP_GAP), y + row * (NP_INST_H + NP_GAP),
                                       NP_INST_W, NP_INST_H), int(c)))
        y += ((len(COLOR_LIST) + 1) // 2) * (NP_INST_H + NP_GAP) + 6
        bw = (NP_INNER - NP_GAP) // 2
        brights = [(pygame.Rect(ix + i * (bw + NP_GAP), y, bw, NP_BTN_H), bool(i)) for i in range(2)]
        y += NP_BTN_H + NP_PAD
        return {'rect': pygame.Rect(x0, y0, NP_W, y - y0), 'colors': colors, 'brights': brights}

    def key_layout(self, W: int) -> dict:
        """Positions of the keys panel buttons (grid of KP_COLS columns)."""
        x0, y0 = max(PANEL_W + 10, W - NP_W - 10), 64
        ix = x0 + NP_PAD
        y = y0 + NP_PAD + 20
        bw = (NP_INNER - (KP_COLS - 1) * NP_GAP) // KP_COLS
        keys = [(pygame.Rect(ix + (n % KP_COLS) * (bw + NP_GAP), y + (n // KP_COLS) * (NP_INST_H + NP_GAP),
                             bw, NP_INST_H), int(k)) for n, k in enumerate(KEY_LIST)]
        y += ((len(KEY_LIST) + KP_COLS - 1) // KP_COLS) * (NP_INST_H + NP_GAP) + NP_PAD - NP_GAP
        return {'rect': pygame.Rect(x0, y0, NP_W, y - y0), 'keys': keys}

    # ---- walls (Wall) -----------------------------------------------------

    def wall_layout(self, W: int) -> dict:
        """Positions of the walls panel: 8 colors, a "No letter" button and an A-Z / 0-9 grid."""
        x0, y0 = max(PANEL_W + 10, W - NP_W - 10), 64
        ix = x0 + NP_PAD
        y = y0 + NP_PAD + 20
        colors = []
        for n, c in enumerate(WALL_COLOR_LIST):
            col, row = n % 2, n // 2
            colors.append((pygame.Rect(ix + col * (NP_INST_W + NP_GAP), y + row * (NP_INST_H + NP_GAP),
                                       NP_INST_W, NP_INST_H), int(c)))
        y += ((len(WALL_COLOR_LIST) + 1) // 2) * (NP_INST_H + NP_GAP) + 6
        none = pygame.Rect(ix, y, NP_INNER, NP_BTN_H)
        y += NP_BTN_H + NP_GAP
        bw = (NP_INNER - (WP_COLS - 1) * NP_GAP) // WP_COLS
        letters = [(pygame.Rect(ix + (n % WP_COLS) * (bw + NP_GAP), y + (n // WP_COLS) * (NP_INST_H + NP_GAP),
                                bw, NP_INST_H), idx) for n, idx in enumerate(WALL_LETTER_LIST)]
        y += ((len(WALL_LETTER_LIST) + WP_COLS - 1) // WP_COLS) * (NP_INST_H + NP_GAP) + NP_PAD - NP_GAP
        return {'rect': pygame.Rect(x0, y0, NP_W, y - y0), 'colors': colors, 'none': none, 'letters': letters}

    def over_note_panel(self, pos) -> bool:
        """True if the mouse is over the active side panel (notes, colors, keys, walls or text)."""
        W = self.surface.get_width()
        if self.sel == ArrowType.Music_Arrow:
            return self.note_layout(W)['rect'].collidepoint(pos)
        if self.sel in COLORED_TYPES:
            return self.display_layout(W)['rect'].collidepoint(pos)
        if self.sel in KEYBOARD_TYPES:
            return self.key_layout(W)['rect'].collidepoint(pos)
        if self.sel in TEXT_TYPES:
            return self.text_layout(W)['rect'].collidepoint(pos)
        if self.sel in WALL_TYPES:
            return self.wall_layout(W)['rect'].collidepoint(pos)
        return False

    def click_note_panel(self, pos):
        if self.sel in TEXT_TYPES:
            self.click_text_panel(pos)
            return
        if self.sel in KEYBOARD_TYPES:
            for rect, k in self.key_layout(self.surface.get_width())['keys']:
                if rect.collidepoint(pos):
                    self.key_sel = k
                    return
            return
        if self.sel in WALL_TYPES:
            lay = self.wall_layout(self.surface.get_width())
            for rect, c in lay['colors']:
                if rect.collidepoint(pos):
                    self.wall_color_sel = c
                    return
            if lay['none'].collidepoint(pos):
                self.wall_letter_sel = 0
                return
            for rect, idx in lay['letters']:
                if rect.collidepoint(pos):
                    self.wall_letter_sel = idx
                    return
            return
        if self.sel in COLORED_TYPES:
            lay = self.display_layout(self.surface.get_width())
            for rect, color in lay['colors']:
                if rect.collidepoint(pos):
                    self.display_color = color
                    return
            for rect, bright in lay['brights']:
                if rect.collidepoint(pos):
                    self.display_bright = bright
                    return
            return
        lay = self.note_layout(self.surface.get_width())
        for rect, inst in lay['instruments']:
            if rect.collidepoint(pos):
                self.set_instrument(inst)
                return
        for rect, pitch in lay['pitches']:
            if rect.collidepoint(pos):
                self.note_pitch = pitch
                return
        for rect, octave in lay['octaves']:
            if rect.collidepoint(pos):
                self.set_octave(octave)      # ignored if outside the instrument's range
                return

    def pick_palette(self, pos):
        col = (pos[0] - PAD) // (ICON + PAD)
        row = (pos[1] - PAD) // (ICON + PAD)
        if 0 <= col < PALETTE_COLS and row >= 0:
            i = row * PALETTE_COLS + col
            if i < len(DRAWABLE):
                self.sel = DRAWABLE[i]
                self.text_target = None

    def palette_index_at(self, pos):
        col = (pos[0] - PAD) // (ICON + PAD)
        row = (pos[1] - PAD) // (ICON + PAD)
        if 0 <= col < PALETTE_COLS and row >= 0:
            i = row * PALETTE_COLS + col
            if i < len(DRAWABLE):
                return i
        return None

    # ---- camera ----------------------------------------------------------

    def zoom(self, step: int):
        new_i = max(0, min(len(ZOOMS) - 1, self.zoom_i + step))
        if new_i == self.zoom_i:
            return
        before = self.screen_to_world(self.mouse_pos)
        self.zoom_i = new_i
        after = self.screen_to_world(self.mouse_pos)
        self.cam_x += before[0] - after[0]
        self.cam_y += before[1] - after[1]

    def fit_view(self):
        xs, ys = [], []
        for (cx, cy), c in self.world.chunks.items():
            if any(a.type != ArrowType.Empty_cell for a in c.arrows):
                xs.append(cx)
                ys.append(cy)
        W, H = self.surface.get_size()
        if not xs:
            self.cam_x = self.cam_y = 0.0
            return
        x0, x1 = min(xs) * CHUNK, (max(xs) + 1) * CHUNK
        y0, y1 = min(ys) * CHUNK, (max(ys) + 1) * CHUNK
        avail = W - PANEL_W
        self.zoom_i = 0
        for i in range(len(ZOOMS) - 1, -1, -1):
            s = ZOOMS[i]
            if s <= 16 and (x1 - x0) * s <= avail * 0.9 and (y1 - y0) * s <= H * 0.9:
                self.zoom_i = i
                break
        s = self.scale
        self.cam_x = (x0 + x1) / 2 - PANEL_W / 2 / s
        self.cam_y = (y0 + y1) / 2

    # ---- files / clipboard ---------------------------------------

    def load_code(self, text: str) -> bool:
        if text.lstrip().startswith('{'):          # World.json format: the code is in "data" (or "preview_data")
            try:
                doc = json.loads(text)
                text = doc.get('data') or doc.get('preview_data') or ''
                if not isinstance(text, str):
                    raise ValueError('"data" is not a string')
            except ValueError as exc:
                self.say(f'Invalid JSON: {exc}')
                return False
        code = ''.join(text.split())
        try:
            world = Map(code)
        except Exception as exc:
            self.say(f'Invalid code: {type(exc).__name__}')
            return False
        self.world = world
        self.reset_caches()
        self.selection.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.fit_view()
        return True

    def load_file(self):
        try:
            text = self.path.read_text(encoding='utf-8')
        except OSError as exc:
            self.say(f'Cannot read: {exc}')
            return
        if self.load_code(text):
            self.say(f'Loaded: {self.path.name}')

    def save_file(self):
        try:
            code = encode_world(self.world)
            doc = {
                'name': 'World',
                'version': 1,
                'theme': 'dark',
                'background_style': 'grid',
                'preview_data': code,
                'tags': [],
                '_preview_header_end': {'version': 1, 'fields': 435},
                'data': code,
            }
            self.path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            self.say(f'Saved: {self.path}')
        except (OSError, ValueError) as exc:
            self.say(f'Cannot save: {exc}')

    def copy_code(self):
        try:
            code = encode_world(self.world)
            import tkinter
            root = tkinter.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(code)
            root.update()
            root.destroy()
            self.say('Code copied to the clipboard')
        except Exception as exc:
            self.say(f'Cannot copy ({type(exc).__name__}): use Ctrl+S')

    def paste_code(self):
        try:
            import tkinter
            root = tkinter.Tk()
            root.withdraw()
            try:
                text = root.clipboard_get()
            finally:
                root.destroy()
        except Exception as exc:
            self.say(f'Clipboard unavailable ({type(exc).__name__})')
            return
        if self.load_code(text):
            self.say('Code pasted and loaded')

    # ---- events ------------------------------------------------------

    def handle_event(self, e):
        if e.type == pygame.QUIT:
            self.running = False

        elif e.type == pygame.MOUSEMOTION:
            self.mouse_pos = e.pos
            if self.text_dragging:
                self.text_drag(e.pos)
            self.begin_selection_rect()
            if self.panning:
                s = self.scale
                self.cam_x -= e.rel[0] / s
                self.cam_y -= e.rel[1] / s
            elif self.stroke is not None:
                cell = self.cell_at(e.pos)
                if cell != self.last_cell:
                    for c in line_cells(self.last_cell, cell):
                        self.paint(c)
                    self.last_cell = cell

        elif e.type == pygame.MOUSEBUTTONDOWN:
            self.mouse_pos = e.pos
            if self.text_editing and not (self.sel in TEXT_TYPES and self.over_note_panel(e.pos)):
                self.end_text_edit()                  # click outside the text panel: confirms the typing
            if self.in_panel(e.pos):
                if e.button == 1:
                    self.pick_palette(e.pos)
            elif self.over_note_panel(e.pos) and not (e.button == 1 and self.space):
                if e.button == 1:
                    self.click_note_panel(e.pos)
            elif e.button == 3:
                self.edit_text_at(e.pos)              # right click: edit an arrow's text
            elif e.button == 2 or (e.button == 1 and self.space):
                self.panning = True
            elif e.button == 1 and self.e_held:
                pass                                  # E held: selecting, the click places nothing
            elif e.button == 1 and self.stroke is None:
                self.begin_stroke('paint', e.pos)

        elif e.type == pygame.MOUSEBUTTONUP:
            if e.button == 1:
                self.text_dragging = False
            if self.panning and e.button in (1, 2):
                self.panning = False
            elif self.stroke is not None and e.button == 1 and self.stroke_mode == 'paint':
                self.end_stroke()

        elif e.type == pygame.MOUSEWHEEL:
            if e.y and self.sel in TEXT_TYPES and self.over_note_panel(self.mouse_pos):
                self.text_scroll_by(-e.y)
            elif e.y:
                self.zoom(1 if e.y > 0 else -1)

        elif e.type == pygame.TEXTINPUT:
            if self.text_editing:
                self.text_insert(e.text)

        elif e.type == pygame.KEYDOWN:
            if self.text_editing:                     # the input area captures the whole keyboard
                self.handle_text_key(e)
                return
            ctrl = e.mod & (pygame.KMOD_CTRL | pygame.KMOD_META)
            shift = e.mod & pygame.KMOD_SHIFT
            if e.key == pygame.K_e:
                if not self.e_held:                   # ignore key auto-repeat
                    if self.stroke is not None:       # E interrupts a stroke in progress (held click, R)
                        self.end_stroke()
                    self.e_press(bool(ctrl), bool(shift))
            elif ctrl:
                if e.key == pygame.K_z:
                    self.redo() if shift else self.undo()
                elif e.key == pygame.K_y:
                    self.redo()
                elif e.key == pygame.K_s:
                    self.save_file()
                elif e.key == pygame.K_o:
                    self.load_file()
                elif e.key == pygame.K_c:
                    self.copy_code()
                elif e.key == pygame.K_v:
                    self.paste_code()
            elif getattr(e, 'scancode', None) in ORIENT_SCANCODES:
                self.direction = Direction(ORIENT_SCANCODES[e.scancode])
            elif e.key == pygame.K_t:
                self.direction = Direction((int(self.direction) + (3 if shift else 1)) % 4)
            elif e.key == pygame.K_r:
                if (self.stroke is None and not self.in_panel(self.mouse_pos)
                        and not self.over_note_panel(self.mouse_pos)):
                    self.begin_stroke('erase', self.mouse_pos)
            elif e.key == pygame.K_z:
                self.undo()
            elif e.key == pygame.K_y:
                self.redo()
            # Selection mode: active while at least one arrow is selected
            elif e.key == pygame.K_c and self.selection:
                self.copy_selection()
            elif e.key == pygame.K_x and self.selection:
                self.cut_selection()
            elif e.key == pygame.K_BACKSPACE and self.selection:
                self.delete_selection()
            elif e.key == pygame.K_v and self.clipboard:      # also after an X (the selection is then empty)
                self.paste_selection()
            elif e.key == pygame.K_f:
                self.flipped = not self.flipped
            elif e.key == pygame.K_p:
                self.pipette()
            elif e.key == pygame.K_k:
                self.key_tool_key(bool(shift))
            elif e.key in (pygame.K_m, pygame.K_l):
                self.wall_tool_key(e.key, bool(shift))
            elif e.key in (pygame.K_TAB, pygame.K_n, pygame.K_PAGEUP, pygame.K_PAGEDOWN):
                self.note_tool_key(e.key, bool(shift))
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.sel in TEXT_TYPES:
                self.begin_text_edit()
            elif e.key == pygame.K_SPACE:
                self.space = True
            elif e.key == pygame.K_HOME:
                self.cam_x = self.cam_y = 0.0
            elif e.key in (pygame.K_h, pygame.K_F1):
                self.show_help = not self.show_help

        elif e.type == pygame.KEYUP:
            if e.key == pygame.K_SPACE:
                self.space = False
            elif e.key == pygame.K_e:
                self.e_release()
            elif e.key == pygame.K_r and self.stroke is not None and self.stroke_mode == 'erase':
                self.end_stroke()

    def update(self, dt: float):
        keys = pygame.key.get_pressed()
        if self.e_held and not keys[pygame.K_e]:      # missed KEYUP (focus loss...): confirm anyway
            self.e_release()
        if self.text_editing:
            return                                    # no camera movement while typing
        dx = int(keys[pygame.K_RIGHT]) - int(keys[pygame.K_LEFT])
        dy = int(keys[pygame.K_DOWN]) - int(keys[pygame.K_UP])
        if dx or dy:
            fast = 3 if (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) else 1
            speed = 700 * fast / self.scale
            self.cam_x += dx * speed * dt
            self.cam_y += dy * speed * dt

    # ---- rendering -----------------------------------------------------------

    def get_mini(self, key, chunk):
        if key in self.mini:
            return self.mini[key]
        mini = None
        for idx, a in enumerate(chunk.arrows):
            if a.type == ArrowType.Empty_cell:
                continue
            col = self.sprites.avg.get(a.type)
            if col is None:
                continue
            if a.type in COLORED_TYPES and int(a.color) != Color.Undefined:
                col = display_rgb(a.color, a.bright)
            elif a.type in WALL_TYPES and int(a.wall_color) != WallColor.White and wall_rgb(a.wall_color):
                col = wall_rgb(a.wall_color)
            if mini is None:
                mini = pygame.Surface((CHUNK, CHUNK), pygame.SRCALPHA)
            mini.set_at((idx % CHUNK, idx // CHUNK), col)
        self.mini[key] = mini
        return mini

    def build_surface(self, key, chunk, s):
        if s <= 1:
            mini = self.get_mini(key, chunk)
            if mini is None or s == 1:
                return mini
            n = int(round(CHUNK * s))
            return pygame.transform.smoothscale(mini, (n, n))
        size = int(s)
        surf = None
        for idx, a in enumerate(chunk.arrows):
            if a.type == ArrowType.Empty_cell:
                continue
            spr = self.sprites.get(a.type, a.direction, a.flipped, size, a.color, a.bright, a.key,
                                   a.wall_color, a.wall_letter)
            if spr is None:
                continue
            if surf is None:
                surf = pygame.Surface((CHUNK * size, CHUNK * size), pygame.SRCALPHA)
            surf.blit(spr, ((idx % CHUNK) * size, (idx // CHUNK) * size))
        return surf

    def chunk_surface(self, key, chunk):
        s = self.scale
        entry = self.rendered.get(key)
        if entry is not None and entry[0] == s:
            return entry[1]
        surf = self.build_surface(key, chunk, s)
        self.rendered[key] = (s, surf)
        return surf

    def note_overlay(self, note, size: int) -> pygame.Surface:
        """Banner (note + octave, instrument) shown on a Music_Arrow cell that is large enough."""
        key = (note, size)
        surf = self.overlay_cache.get(key)
        if surf is None:
            if len(self.overlay_cache) > 2000:
                self.overlay_cache.clear()
            instrument, pitch, octave = note
            big = pygame.font.Font(None, max(14, int(size * 0.42))).render(
                note_name(pitch, octave), True, (255, 255, 255))
            small = pygame.font.Font(None, max(12, int(size * 0.28))).render(
                instrument_name(instrument), True, (210, 210, 225))
            surf = pygame.Surface((size, big.get_height() + small.get_height() + 4), pygame.SRCALPHA)
            surf.fill((0, 0, 0, 160))
            surf.blit(big, ((size - big.get_width()) // 2, 1))
            surf.blit(small, ((size - small.get_width()) // 2, big.get_height() + 2))
            self.overlay_cache[key] = surf
        return surf

    def text_overlay(self, txt: str, size: int) -> pygame.Surface:
        """Banner (one-line text preview) shown on a text cell that is large enough."""
        line = txt[:200].replace('\n', ' / ')
        key = ('t', line, size)
        surf = self.overlay_cache.get(key)
        if surf is None:
            if len(self.overlay_cache) > 2000:
                self.overlay_cache.clear()
            font = pygame.font.Font(None, max(12, int(size * 0.28)))
            maxw = size - 6
            if font.size(line)[0] > maxw or len(txt) > 200:
                while line and font.size(line + '...')[0] > maxw:
                    line = line[:-1]
                line += '...'
            img = font.render(line, True, (255, 255, 255))
            surf = pygame.Surface((size, img.get_height() + 4), pygame.SRCALPHA)
            surf.fill((0, 0, 0, 160))
            surf.blit(img, ((size - img.get_width()) // 2, 2))
            self.overlay_cache[key] = surf
        return surf

    def visible_range(self, W, H):
        s = self.scale
        left, right = self.cam_x - W / 2 / s, self.cam_x + W / 2 / s
        top, bottom = self.cam_y - H / 2 / s, self.cam_y + H / 2 / s
        return left, right, top, bottom

    def draw_grid(self, screen, W, H):
        s = self.scale
        left, right, top, bottom = self.visible_range(W, H)

        def lines(step, color):
            if (right - left) / step > 600 or (bottom - top) / step > 600:
                return
            for k in range(math.ceil(left / step), math.floor(right / step) + 1):
                sx = ipx((k * step - self.cam_x) * s + W / 2)
                pygame.draw.line(screen, color, (sx, 0), (sx, H))
            for k in range(math.ceil(top / step), math.floor(bottom / step) + 1):
                sy = ipx((k * step - self.cam_y) * s + H / 2)
                pygame.draw.line(screen, color, (0, sy), (W, sy))

        if s >= 16:
            lines(1, GRID_CELL)
        if s * CHUNK >= 8:
            lines(CHUNK, GRID_CHUNK)
        ox, oy = ipx((0 - self.cam_x) * s + W / 2), ipx((0 - self.cam_y) * s + H / 2)
        pygame.draw.line(screen, GRID_AXIS, (ox, 0), (ox, H))
        pygame.draw.line(screen, GRID_AXIS, (0, oy), (W, oy))

    def draw_world(self, screen, W, H):
        s = self.scale
        left, right, top, bottom = self.visible_range(W, H)
        cx0, cx1 = math.floor(left / CHUNK), math.floor(right / CHUNK)
        cy0, cy1 = math.floor(top / CHUNK), math.floor(bottom / CHUNK)

        if s >= DIRECT_DRAW_MIN:
            size = int(s)
            for cy in range(cy0, cy1 + 1):
                for cx in range(cx0, cx1 + 1):
                    chunk = self.world.chunks.get((cx, cy))
                    if not chunk:
                        continue
                    for idx, a in enumerate(chunk.arrows):
                        if a.type == ArrowType.Empty_cell:
                            continue
                        spr = self.sprites.get(a.type, a.direction, a.flipped, size, a.color, a.bright, a.key,
                                               a.wall_color, a.wall_letter)
                        if spr is None:
                            continue
                        sx = ipx((cx * CHUNK + idx % CHUNK - self.cam_x) * s + W / 2)
                        sy = ipx((cy * CHUNK + idx // CHUNK - self.cam_y) * s + H / 2)
                        if sx > W or sy > H or sx + size < 0 or sy + size < 0:
                            continue
                        screen.blit(spr, (sx, sy))
                        if a.type == ArrowType.Music_Arrow and size >= NOTE_LABEL_MIN:
                            ov = self.note_overlay((int(a.instrument), int(a.pitch), int(a.octave)), size)
                            screen.blit(ov, (sx, sy + size - ov.get_height()))
                        elif a.type in TEXT_TYPES and a.string and size >= TEXT_LABEL_MIN:
                            ov = self.text_overlay(a.string, size)
                            screen.blit(ov, (sx, sy + size - ov.get_height()))
            return

        # Iterate over the smaller of the two sets: visible chunks or existing chunks
        n_visible = (cx1 - cx0 + 1) * (cy1 - cy0 + 1)
        chunks = self.world.chunks
        if n_visible <= len(chunks):
            items = [((cx, cy), chunks[(cx, cy)]) for cy in range(cy0, cy1 + 1)
                     for cx in range(cx0, cx1 + 1) if (cx, cy) in chunks]
        else:
            items = [(k, c) for k, c in chunks.items() if cx0 <= k[0] <= cx1 and cy0 <= k[1] <= cy1]

        for (cx, cy), chunk in items:
            surf = self.chunk_surface((cx, cy), chunk)
            if surf is None:
                continue
            sx = ipx((cx * CHUNK - self.cam_x) * s + W / 2)
            sy = ipx((cy * CHUNK - self.cam_y) * s + H / 2)
            screen.blit(surf, (sx, sy))

        if len(self.rendered) > 1500:          # keeps the cache from growing indefinitely
            keep = {k for k, _ in items}
            self.rendered = {k: v for k, v in self.rendered.items() if k in keep}

    def cell_rect(self, x0, y0, x1, y1, W, H):
        s = self.scale
        sx = ipx((x0 - self.cam_x) * s + W / 2)
        sy = ipx((y0 - self.cam_y) * s + H / 2)
        ex = ipx((x1 + 1 - self.cam_x) * s + W / 2)
        ey = ipx((y1 + 1 - self.cam_y) * s + H / 2)
        return pygame.Rect(sx, sy, max(2, ex - sx), max(2, ey - sy))

    def draw_selection(self, screen, W, H):
        s = self.scale
        if self.selection:
            if s >= 4 and len(self.selection) <= 20000:
                size = max(2, ipx(s))
                tint = pygame.Surface((size, size), pygame.SRCALPHA)
                tint.fill((*SELECT_COLOR, 70))
                pygame.draw.rect(tint, SELECT_COLOR, tint.get_rect(), 1)
                left, right, top, bottom = self.visible_range(W, H)
                for x, y in self.selection:
                    if left - 1 <= x <= right and top - 1 <= y <= bottom:
                        screen.blit(tint, (ipx((x - self.cam_x) * s + W / 2), ipx((y - self.cam_y) * s + H / 2)))
            else:
                xs = [c[0] for c in self.selection]
                ys = [c[1] for c in self.selection]
                pygame.draw.rect(screen, SELECT_COLOR,
                                 self.cell_rect(min(xs), min(ys), max(xs), max(ys), W, H), 1)
        rect = self.selection_rect()
        if rect is not None:
            r = self.cell_rect(*rect, W, H)
            veil = pygame.Surface(r.size, pygame.SRCALPHA)
            veil.fill((*SELECT_COLOR, 40))
            screen.blit(veil, r.topleft)
            pygame.draw.rect(screen, SELECT_COLOR, r, 2)

    def draw_cursor(self, screen, W, H):
        if self.in_panel(self.mouse_pos) or self.over_note_panel(self.mouse_pos) or self.panning:
            return
        s = self.scale
        hx, hy = self.cell_at(self.mouse_pos)
        sx = ipx((hx - self.cam_x) * s + W / 2)
        sy = ipx((hy - self.cam_y) * s + H / 2)
        size = max(2, ipx(s))
        if s >= 4 and not self.e_held:
            ghost = self.sprites.get(self.sel, self.direction, self.flipped, int(s),
                                     self.display_color, self.display_bright, self.key_sel,
                                     self.wall_color_sel, self.wall_letter_sel)
            if ghost is not None:
                ghost = ghost.copy()
                ghost.set_alpha(140)
                screen.blit(ghost, (sx, sy))
                if self.sel == ArrowType.Music_Arrow and s >= NOTE_LABEL_MIN:
                    ov = self.note_overlay(self.note_state(), int(s)).copy()
                    ov.set_alpha(140)
                    screen.blit(ov, (sx, sy + int(s) - ov.get_height()))
                elif self.sel in TEXT_TYPES and self.text_sel and s >= TEXT_LABEL_MIN:
                    ov = self.text_overlay(self.text_sel, int(s)).copy()
                    ov.set_alpha(140)
                    screen.blit(ov, (sx, sy + int(s) - ov.get_height()))
        pygame.draw.rect(screen, (255, 210, 60), (sx, sy, size, size), 1)

    def draw_panel(self, screen, H):
        pygame.draw.rect(screen, (34, 34, 42), (0, 0, PANEL_W, H))
        pygame.draw.line(screen, (70, 70, 85), (PANEL_W - 1, 0), (PANEL_W - 1, H))
        for i, t in enumerate(DRAWABLE):
            x = PAD + (i % PALETTE_COLS) * (ICON + PAD)
            y = PAD + (i // PALETTE_COLS) * (ICON + PAD)
            pygame.draw.rect(screen, (52, 52, 64), (x, y, ICON, ICON))
            spr = self.sprites.get(t, self.direction, self.flipped, ICON,
                                   self.display_color, self.display_bright, self.key_sel,
                                   self.wall_color_sel, self.wall_letter_sel)
            if spr is not None:
                screen.blit(spr, (x, y))
            if t == self.sel:
                pygame.draw.rect(screen, (255, 210, 60), (x - 1, y - 1, ICON + 2, ICON + 2), 2)

    def draw_display_panel(self, screen, W):
        if self.sel not in COLORED_TYPES:
            return
        lay = self.display_layout(W)
        rect = lay['rect']
        pygame.draw.rect(screen, (34, 34, 42), rect)
        pygame.draw.rect(screen, (70, 70, 85), rect, 1)
        title = self.small_font.render(f'Color: {display_text(self.display_color, self.display_bright)}',
                                       True, (255, 210, 60))
        screen.blit(title, (rect.x + NP_PAD, rect.y + NP_PAD))

        for r, color in lay['colors']:
            selected = color == self.display_color
            pygame.draw.rect(screen, (255, 210, 60) if selected else (52, 52, 64), r)
            swatch = pygame.Rect(r.x + 3, r.y + 3, 16, r.height - 6)
            pygame.draw.rect(screen, display_rgb(color), swatch)
            img = self.small_font.render(COLOR_LABELS[Color(color)], True,
                                         (20, 20, 20) if selected else (235, 235, 240))
            screen.blit(img, (swatch.right + 6, r.centery - img.get_height() // 2))
        for r, bright in lay['brights']:
            selected = bright == self.display_bright
            pygame.draw.rect(screen, (255, 210, 60) if selected else (52, 52, 64), r)
            img = self.small_font.render('Bright' if bright else 'Normal', True,
                                         (20, 20, 20) if selected else (235, 235, 240))
            screen.blit(img, (r.centerx - img.get_width() // 2, r.centery - img.get_height() // 2))

    def draw_key_panel(self, screen, W):
        if self.sel not in KEYBOARD_TYPES:
            return
        lay = self.key_layout(W)
        rect = lay['rect']
        pygame.draw.rect(screen, (34, 34, 42), rect)
        pygame.draw.rect(screen, (70, 70, 85), rect, 1)
        title = self.small_font.render(f'Key: {key_label(self.key_sel)}', True, (255, 210, 60))
        screen.blit(title, (rect.x + NP_PAD, rect.y + NP_PAD))
        for r, k in lay['keys']:
            selected = k == self.key_sel
            pygame.draw.rect(screen, (255, 210, 60) if selected else (52, 52, 64), r)
            img = self.small_font.render(key_label(k), True, (20, 20, 20) if selected else (235, 235, 240))
            screen.blit(img, (r.centerx - img.get_width() // 2, r.centery - img.get_height() // 2))

    def draw_wall_panel(self, screen, W):
        if self.sel not in WALL_TYPES:
            return
        lay = self.wall_layout(W)
        rect = lay['rect']
        pygame.draw.rect(screen, (34, 34, 42), rect)
        pygame.draw.rect(screen, (70, 70, 85), rect, 1)
        title = self.small_font.render(f'Wall: {wall_text(self.wall_color_sel, self.wall_letter_sel)}',
                                       True, (255, 210, 60))
        screen.blit(title, (rect.x + NP_PAD, rect.y + NP_PAD))

        def button(r, label, selected):
            pygame.draw.rect(screen, (255, 210, 60) if selected else (52, 52, 64), r)
            img = self.small_font.render(label, True, (20, 20, 20) if selected else (235, 235, 240))
            screen.blit(img, (r.centerx - img.get_width() // 2, r.centery - img.get_height() // 2))

        for r, c in lay['colors']:
            selected = c == self.wall_color_sel
            pygame.draw.rect(screen, (255, 210, 60) if selected else (52, 52, 64), r)
            swatch = pygame.Rect(r.x + 3, r.y + 3, 16, r.height - 6)
            pygame.draw.rect(screen, wall_rgb(c), swatch)
            pygame.draw.rect(screen, (90, 90, 105), swatch, 1)          # outline: white and black stay readable
            img = self.small_font.render(WALL_LABELS[WallColor(c)], True, (20, 20, 20) if selected else (235, 235, 240))
            screen.blit(img, (swatch.right + 6, r.centery - img.get_height() // 2))
        button(lay['none'], 'No letter', self.wall_letter_sel == 0)
        for r, idx in lay['letters']:
            button(r, wall_letter_char(idx), idx == self.wall_letter_sel)

    def draw_note_panel(self, screen, W):
        if self.sel != ArrowType.Music_Arrow:
            return
        lay = self.note_layout(W)
        rect = lay['rect']
        pygame.draw.rect(screen, (34, 34, 42), rect)
        pygame.draw.rect(screen, (70, 70, 85), rect, 1)
        title = self.small_font.render(f'Note: {note_text(self.note_state())}', True, (255, 210, 60))
        screen.blit(title, (rect.x + NP_PAD, rect.y + NP_PAD))
        lo, hi = instrument_range(self.note_instrument)

        def button(r, label, selected=False, enabled=True):
            fill = (255, 210, 60) if selected else ((52, 52, 64) if enabled else (40, 40, 48))
            color = (20, 20, 20) if selected else ((235, 235, 240) if enabled else (90, 90, 100))
            pygame.draw.rect(screen, fill, r)
            img = self.small_font.render(label, True, color)
            screen.blit(img, (r.centerx - img.get_width() // 2, r.centery - img.get_height() // 2))

        for r, inst in lay['instruments']:
            button(r, instrument_name(inst), inst == self.note_instrument)
        for r, pitch in lay['pitches']:
            button(r, PITCH_NAMES[pitch], pitch == self.note_pitch)
        for r, octave in lay['octaves']:
            button(r, str(octave), octave == self.note_octave, lo <= octave <= hi)

    def draw_text_panel(self, screen, W):
        if self.sel not in TEXT_TYPES:
            return
        lay = self.text_layout(W)
        rect, box = lay['rect'], lay['box']
        code = self.sel in JS_TYPES
        tb = self.tb
        pygame.draw.rect(screen, (34, 34, 42), rect)
        pygame.draw.rect(screen, (70, 70, 85), rect, 1)
        name = self.sel.name + (' (JS)' if code else '')
        if self.text_target is not None:
            head = f'{name}: cell {self.text_target[0]}, {self.text_target[1]}'
        else:
            head = f'{name}: text to place'
        screen.blit(self.small_font.render(head, True, (255, 210, 60)), (rect.x + NP_PAD, rect.y + NP_PAD))

        pygame.draw.rect(screen, (22, 22, 27), box)
        pygame.draw.rect(screen, (255, 210, 60) if self.text_editing else (70, 70, 85), box, 1)
        text, lines = tb.text, self.text_lines()
        font = self.code_font if code else self.small_font
        colors = self.js_colors() if code else None
        gw = self.gutter_w()
        tx = box.x + 4 + gw                           # left edge of the text
        sel = tb.selection
        cur_n = tb.cursor_line(lines)
        cur_no = text.count('\n', 0, tb.cursor) + 1   # number of the line holding the cursor
        match = tb.match_bracket(colors) if (code and self.text_editing) else None
        first = self.text_scroll
        stop = min(len(lines), first + TP_VIS)

        def x_of(start, i):                           # x of character `i` on the visual line starting at `start`
            return tx + sum(self.char_width(c) for c in text[start:i])

        screen.set_clip(box.inflate(-4, -4))
        if gw:                                        # line-number column
            pygame.draw.rect(screen, (27, 27, 34), (box.x + 1, box.y + 1, gw, box.height - 2))
            pygame.draw.line(screen, (60, 60, 72), (box.x + gw, box.y + 1), (box.x + gw, box.bottom - 2))
        if not text and not self.text_editing:
            msg = 'Click here (or press Enter) to write JavaScript' if code else 'Click here (or press Enter) to type the text'
            screen.blit(self.small_font.render(msg, True, (110, 110, 125)), (tx, box.y + 4))
        for n in range(first, stop):
            s, e, para_end = lines[n]
            y = box.y + 4 + (n - first) * TP_LINE_H
            if self.text_editing and sel is None and n == cur_n:      # current line
                pygame.draw.rect(screen, (30, 30, 39), (box.x + gw + 1, y, box.width - gw - 2, TP_LINE_H))
            if sel:                                   # selection (a selected newline shows as a small extra block)
                a, b = max(s, sel[0]), min(e, sel[1])
                nl = para_end and e < len(text) and sel[0] <= e < sel[1]
                if b > a or nl:
                    x1 = x_of(s, a)
                    pygame.draw.rect(screen, (55, 85, 145), (x1, y, x_of(s, b) - x1 + (6 if nl else 0), TP_LINE_H))
            if match:                                 # matching brackets
                for idx in match:
                    if s <= idx < e:
                        pygame.draw.rect(screen, (100, 100, 55), (x_of(s, idx), y, self.char_width(text[idx]), TP_LINE_H))
            if gw and tb.first_no[n]:
                num = tb.first_no[n]
                img = self.small_font.render(str(num), True, (180, 180, 195) if num == cur_no else (100, 100, 115))
                screen.blit(img, (box.x + gw - 6 - img.get_width(), y + 1))
            if e <= s:
                continue
            if colors is None:                        # plain text (Message)
                screen.blit(font.render(text[s:e], True, (235, 235, 240)), (tx, y))
                continue
            x, k = tx, s                              # JavaScript: one segment per run of characters of the same color
            while k < e:
                c = colors[k]
                m = k + 1
                while m < e and colors[m] == c:
                    m += 1
                seg = text[k:m]
                if seg.strip():
                    screen.blit(font.render(seg, True, JS_COLORS[c]), (x, y))
                x += sum(self.char_width(ch) for ch in seg)
                k = m
        if self.text_editing and first <= cur_n < stop and int(time.time() * 2) % 2 == 0:      # blinking caret
            cx = x_of(lines[cur_n][0], tb.cursor)
            cy = box.y + 4 + (cur_n - first) * TP_LINE_H
            pygame.draw.line(screen, (255, 255, 255), (cx, cy), (cx, cy + TP_LINE_H - 4))
        if len(lines) > TP_VIS:                       # scrollbar
            track = box.height - 8
            h = max(12, track * TP_VIS // len(lines))
            y = box.y + 4 + (track - h) * self.text_scroll // max(1, len(lines) - TP_VIS)
            pygame.draw.rect(screen, (90, 90, 105), (box.right - 6, y, 3, h))
        screen.set_clip(None)

        col = tb.cursor - (text.rfind('\n', 0, tb.cursor) + 1) + 1
        info = f'Ln {cur_no}, Col {col}' + (f'  ({sel[1] - sel[0]} selected)' if sel else '')
        screen.blit(self.small_font.render(info, True, (150, 150, 165)), lay['counter'])
        used = self.small_font.render(f'{len(text.encode("utf-8"))} / {TEXT_MAX_BYTES} bytes', True, (150, 150, 165))
        screen.blit(used, (box.right - used.get_width(), lay['counter'][1]))
        for name, r in lay['buttons']:
            enabled = name != 'apply' or self.text_target is not None
            pygame.draw.rect(screen, (52, 52, 64) if enabled else (40, 40, 48), r)
            label = {'clear': 'Clear', 'apply': 'Apply', 'import': 'Import .js', 'export': 'Export .js'}[name]
            img = self.small_font.render(label, True, (235, 235, 240) if enabled else (90, 90, 100))
            screen.blit(img, (r.centerx - img.get_width() // 2, r.centery - img.get_height() // 2))

    def text(self, screen, txt, pos, color=(235, 235, 240)):
        img = self.font.render(txt, True, color)
        bg = pygame.Surface((img.get_width() + 8, img.get_height() + 4), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 150))
        screen.blit(bg, (pos[0] - 4, pos[1] - 2))
        screen.blit(img, pos)

    def draw_hud(self, screen, W, H):
        x = PANEL_W + 10
        hx, hy = self.cell_at(self.mouse_pos)
        if self.in_panel(self.mouse_pos):
            i = self.palette_index_at(self.mouse_pos)
            where = DRAWABLE[i].name if i is not None else ''
        else:
            where = f'cell {hx}, {hy}   chunk {hx // CHUNK}, {hy // CHUNK}'
            under = self.get_arrow(hx, hy)
            if under is not None and under.type == ArrowType.Music_Arrow and not self.over_note_panel(self.mouse_pos):
                where += '   ' + note_text((under.instrument, under.pitch, under.octave))
            elif under is not None and under.type in COLORED_TYPES and not self.over_note_panel(self.mouse_pos):
                where += '   ' + display_text(under.color, under.bright)
            elif under is not None and under.type in KEYBOARD_TYPES and not self.over_note_panel(self.mouse_pos):
                where += '   Key: ' + key_label(under.key)
            elif under is not None and under.type in WALL_TYPES and not self.over_note_panel(self.mouse_pos):
                where += '   ' + wall_text(under.wall_color, under.wall_letter)
            elif under is not None and under.type in TEXT_TYPES and under.string and not self.over_note_panel(self.mouse_pos):
                where += '   Text: ' + text_preview(under.string)
        self.text(screen, where, (x, 8))
        sel = (f'{self.sel.name}   direction {self.direction.name}   '
               f'flip {"yes" if self.flipped else "no"}   zoom {self.scale:g} px/cell')
        if self.sel == ArrowType.Music_Arrow:
            sel += '   ' + note_text(self.note_state())
        elif self.sel in COLORED_TYPES:
            sel += '   ' + display_text(self.display_color, self.display_bright)
        elif self.sel in KEYBOARD_TYPES:
            sel += '   Key: ' + key_label(self.key_sel)
        elif self.sel in WALL_TYPES:
            sel += '   ' + wall_text(self.wall_color_sel, self.wall_letter_sel)
        elif self.sel in TEXT_TYPES:
            sel += '   Text: ' + (text_preview(self.text_sel) if self.text_sel else '(empty)')
        if self.selection:
            sel += f'   SELECTION MODE ({len(self.selection)})'
        if self.e_held:
            sel += '   [E: ' + {'replace': 'new selection', 'add': 'add', 'remove': 'remove'}[self.e_mode] + ']'
        self.text(screen, sel, (x, 32))
        if time.time() < self.status[1]:
            self.text(screen, self.status[0], (x, H - 52), (255, 220, 120))
        self.text(screen, 'H: help', (x, H - 28), (170, 170, 185))
        if self.show_help:
            for i, line in enumerate(HELP):
                self.text(screen, line, (x, 64 + i * 24))

    def draw(self):
        screen = self.surface
        W, H = screen.get_size()
        screen.fill(BG)
        self.draw_grid(screen, W, H)
        self.draw_world(screen, W, H)
        self.draw_selection(screen, W, H)
        self.draw_cursor(screen, W, H)
        self.draw_panel(screen, H)
        self.draw_note_panel(screen, W)
        self.draw_display_panel(screen, W)
        self.draw_key_panel(screen, W)
        self.draw_wall_panel(screen, W)
        self.draw_text_panel(screen, W)
        self.draw_hud(screen, W, H)
        pygame.display.flip()

    def run(self):
        while self.running:
            dt = self.clock.tick(60) / 1000
            for e in pygame.event.get():
                self.handle_event(e)
            self.update(dt)
            self.draw()
        pygame.quit()


if __name__ == '__main__':
    Editor(sys.argv[1] if len(sys.argv) > 1 else None).run()
