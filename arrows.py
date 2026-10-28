from enum import IntEnum
import base64
from typing import Self
import zlib

class Direction(IntEnum):
    North = 0
    East  = 1
    South = 2
    West  = 3

class ArrowType(IntEnum):
    Empty_cell             = 0
    Arrow                  = 1
    Source_block           = 2
    Blocker                = 3
    Delay_arrow            = 4
    Detector               = 5
    I_Splitter             = 6
    L_Splitter             = 7
    T_Splitter             = 8
    Pulse_generator        = 9
    Blue_arrow             = 10
    Diagonal_arrow         = 11
    Blue_I_Splitter        = 12
    Blue_L_Splitter        = 13
    Diagonal_Splitter      = 14
    Not_gate               = 15
    And_gate               = 16
    XOR_gate               = 17
    Latch                  = 18
    T_flip_flop            = 19
    Randomizer             = 20
    Key                    = 21
    Source                 = 22
    Target                 = 23
    Directional_button     = 24
    Wall                   = 25
    Unknown                = 26
    Light_bulb1            = 27
    Light_bulb2            = 28
    Music_Arrow            = 29
    Transmitter            = 30
    Projectile             = 31
    Update_detector        = 32
    Script_block           = 33
    Message                = 34
    Flash                  = 35
    Piston                 = 36
    Swap                   = 37
    Rotator                = 38
    Mirror                 = 39
    unknown1               = 40
    unknown2               = 41
    Logger                 = 42
    Interval               = 43
    TODO1                 = 44
    TODO2                 = 45
    TODO3                 = 46
    TODO4                 = 47
    TODO5                 = 48
    TODO6                 = 49
    TODO7                 = 50
    TODO8                 = 51
    TODO9                 = 52
    TODO10                = 53
    TODO11                = 54
    TODO12                = 55
    TODO13                = 56
    TODO14                = 57
    TODO15                = 58
    TODO16                = 59
    TODO17                = 60
    TODO18                = 61
    TODO19                = 62
    TODO20                = 63


class Instrument(IntEnum):
    Piano        = 0
    Bass         = 1
    Guitar       = 2
    Drums        = 3
    Tuba         = 4
    Trombone     = 5
    Organ        = 6
    Harp         = 7
    Xylophone    = 8
    Bassoon      = 9
    Cello        = 10
    Clarinet     = 11
    Contrabass   = 12
    Flute        = 13
    Horn         = 14
    Oboe         = 15
    Trumpet      = 16
    Violin       = 17
    Timpani      = 18
    SquareWave   = 19
    TriangleWave = 20
    SawWave      = 21


class Pitch(IntEnum):
    C      = 0
    CSharp = 1
    D      = 2
    DSharp = 3
    E      = 4
    F      = 5
    FSharp = 6
    G      = 7
    GSharp = 8
    A      = 9
    ASharp = 10
    B      = 11


class Color(IntEnum):
    """Color of a Light_bulb1 / Light_bulb2 arrow."""
    Undefined = 0
    Red       = 1
    Blue      = 2
    Yellow    = 3
    Green     = 4
    Orange    = 5
    Purple    = 6


class Key(IntEnum):
    """Key assignable to a Key arrow (stored 16-bit value)."""
    NotDefined = 0
    A = 1
    B = 2
    C = 3
    D = 4
    E = 5
    F = 6
    G = 7
    H = 8
    I = 9
    J = 10
    K = 11
    L = 12
    M = 13
    N = 14
    O = 15
    P = 16
    Q = 17
    R = 18
    S = 19
    T = 20
    U = 21
    V = 22
    W = 23
    X = 24
    Y = 25
    Z = 26
    Num0 = 27
    Num1 = 28
    Num2 = 29
    Num3 = 30
    Num4 = 31
    Num5 = 32
    Num6 = 33
    Num7 = 34
    Num8 = 35
    Num9 = 36
    F1  = 37
    F2  = 38
    F3  = 39
    F4  = 40
    F5  = 41
    F6  = 42
    F7  = 43
    F8  = 44
    F9  = 45
    F10 = 46
    F11 = 47
    F12 = 48
    Space = 49
    Enter = 50
    Tab   = 51
    Shift = 52
    Ctrl  = 53
    Alt   = 54
    Back  = 55
    Up    = 56
    Down  = 57
    Left  = 58
    Right = 59


class WallColor(IntEnum):
    """Color of a Wall (ArrowType 25), stored on 3 bits (0 to 7)."""
    White  = 0
    Red    = 1
    Blue   = 2
    Yellow = 3
    Green  = 4
    Orange = 5
    Purple = 6
    Black  = 7


# Wall (ArrowType 25): color (WallColor) and optional letter / digit (Key.A..Key.Z, Key.Num0..Key.Num9).
# v5 format:
#   - without a letter: the color (0 to 7) is in bits 4 to 6 of dnf, with no extra data:
#       dnf = rotation | (color << 4)          (white without a letter: dnf = 0)
#   - with a letter: dnf = rotation | 0b1000, then a u16 value = (letter << 4) | color,
#       where letter = key index (A = 1 ... Z = 26, 0 = 27 ... 9 = 36).
WALL_TYPES = frozenset({ArrowType.Wall})
WALL_COLOR_SHIFT = 4
WALL_INLINE_MAX = 7                       # maximum color storable in dnf
WALL_LETTER_FIRST = int(Key.A)
WALL_LETTER_LAST = int(Key.Num9)


def wall_letter_index(ch: str) -> int:
    """'A'..'Z' or '0'..'9' (case-insensitive) -> Wall letter index (1 to 36)."""
    c = ch.upper() if isinstance(ch, str) and len(ch) == 1 else ""
    if "A" <= c <= "Z":
        return int(Key.A) + ord(c) - ord("A")
    if "0" <= c <= "9":
        return int(Key.Num0) + ord(c) - ord("0")
    raise ValueError(f"Invalid letter for a Wall: {ch!r} (A to Z or 0 to 9)")


def wall_letter_char(index: int) -> str:
    """Inverse of wall_letter_index: '' if there is no letter (0) or the index is unknown."""
    if int(Key.A) <= index <= int(Key.Z):
        return chr(ord("A") + index - int(Key.A))
    if int(Key.Num0) <= index <= int(Key.Num9):
        return chr(ord("0") + index - int(Key.Num0))
    return ""


# Arrow types whose 16 data bits are a color (not a string or a note).
COLORED_TYPES = frozenset({ArrowType.Light_bulb1, ArrowType.Light_bulb2})
# Arrow types whose 16 data bits are a keyboard key.
KEYBOARD_TYPES = frozenset({ArrowType.Key})
BRIGHT_FLAG = 0x10      # "bright" bit in the low byte of the color value

# Arrow types that can carry a custom text (v5): Source, Target, Script_block, Message.
# Format: dnf = rotation | 0b01000 (data present) | 0b10000 (text), then u16 length + UTF-8 bytes.
TEXT_TYPES = frozenset({ArrowType.Source, ArrowType.Target,
                        ArrowType.Script_block, ArrowType.Message})
TEXT_FLAG = 0b10000
MAX_TEXT_BYTES = 0x7FFF   # the length is read back as signed 16 bits on import
# A Message's text is prefixed with the header b"LGS1" + 1 byte (0x01 in the known examples).
LOGGER_MAGIC = b"LGS1"
LOGGER_DEFAULT_FLAG = 1


# Allowed octave range (min, max) for each instrument.
INSTRUMENT_RANGES: dict[Instrument, tuple[int, int]] = {
    Instrument.Piano:        (0, 7),
    Instrument.Organ:        (1, 6),
    Instrument.SquareWave:   (0, 7),
    Instrument.TriangleWave: (0, 7),
    Instrument.SawWave:      (0, 7),
    Instrument.Guitar:       (1, 5),
    Instrument.Harp:         (2, 6),
    Instrument.Violin:       (2, 6),
    Instrument.Cello:        (1, 5),
    Instrument.Contrabass:   (0, 4),
    Instrument.Bass:         (0, 4),
    Instrument.Flute:        (4, 7),
    Instrument.Oboe:         (3, 6),
    Instrument.Clarinet:     (2, 6),
    Instrument.Bassoon:      (1, 5),
    Instrument.Trumpet:      (3, 6),
    Instrument.Horn:         (1, 5),
    Instrument.Trombone:     (1, 5),
    Instrument.Tuba:         (1, 4),
    Instrument.Xylophone:    (3, 7),
    Instrument.Timpani:      (1, 3),
    Instrument.Drums:        (1, 1),
}


class Arrow:
    def __init__(self, type: ArrowType = ArrowType.Empty_cell, direction: Direction = Direction.North, flipped = False, string: str = "",
                 instrument: int = Instrument.Piano, octave: int = 0, pitch: int = Pitch.C,
                 color: int = Color.Undefined, bright: bool = False,
                 key: int = Key.NotDefined, logger_flag: int = LOGGER_DEFAULT_FLAG,
                 wall_color: int = WallColor.White, wall_letter: int = Key.NotDefined):
        self.type = type
        self.direction = direction
        self.flipped = flipped
        self.string = string
        # Only used if type == ArrowType.Music_Arrow
        self.instrument = instrument
        self.octave = octave
        self.pitch = pitch
        # Only used if type in COLORED_TYPES (Light_bulb1 / Light_bulb2)
        self.color = color
        self.bright = bright
        # Only used if type == ArrowType.Key
        self.key = key
        # Only used if type == ArrowType.Message (byte following "LGS1" in the stored text)
        self.logger_flag = logger_flag
        # Only used if type == ArrowType.Wall (wall_letter: 0 = none, otherwise letter index 1 to 36)
        self.wall_color = wall_color
        self.wall_letter = wall_letter

    direction: Direction = Direction.North
    flipped: bool = False
    type: ArrowType = ArrowType.Empty_cell
    string: str
    instrument: int = Instrument.Piano
    octave: int = 0
    pitch: int = Pitch.C
    color: int = Color.Undefined
    bright: bool = False
    key: int = Key.NotDefined
    logger_flag: int = LOGGER_DEFAULT_FLAG
    wall_color: int = WallColor.White
    wall_letter: int = Key.NotDefined

    @classmethod
    def text(cls, type: ArrowType, string: str,
             direction: Direction = Direction.North, flipped: bool = False) -> "Arrow":
        """Creates a Source / Target / Script_block / Message arrow carrying `string`.
        For a Message, the "LGS1" header is added automatically on export."""
        try:
            type = ArrowType(type)
        except ValueError:
            raise ValueError(f"Type invalide : {type}") from None
        if type not in TEXT_TYPES:
            names = ", ".join(f"{t.name} ({int(t)})" for t in sorted(TEXT_TYPES))
            raise ValueError(f"{type.name} does not support custom text (valid types: {names})")
        if len(string.encode("utf-8")) > MAX_TEXT_BYTES - (len(LOGGER_MAGIC) + 1):
            raise ValueError("Text too long")
        return cls(type, direction, flipped, string)

    @classmethod
    def logger(cls, string: str, direction: Direction = Direction.North, flipped: bool = False) -> "Arrow":
        return cls.text(ArrowType.Message, string, direction, flipped)

    @classmethod
    def note(cls, instrument: Instrument, pitch: Pitch, octave: int,
             direction: Direction = Direction.North, flipped: bool = False) -> "Arrow":
        """Creates a Music_Arrow arrow playing `pitch` at the given `octave` with `instrument`."""
        lo, hi = INSTRUMENT_RANGES[Instrument(instrument)]
        if not lo <= octave <= hi:
            raise ValueError(f"{Instrument(instrument).name} supports octaves {lo} to {hi} (got {octave})")
        if not 0 <= int(pitch) <= 11:
            raise ValueError(f"Note invalide : {pitch}")
        return cls(ArrowType.Music_Arrow, direction, flipped, "", Instrument(instrument), octave, Pitch(pitch))

    @classmethod
    def display(cls, color: Color = Color.Undefined, bright: bool = False,
                direction: Direction = Direction.North, flipped: bool = False,
                directional: bool = False) -> "Arrow":
        """Creates a Light_bulb1 arrow (or Light_bulb2 if `directional`) of the given color,
        normal or bright."""
        try:
            color = Color(color)
        except ValueError:
            raise ValueError(f"Couleur invalide : {color}") from None
        t = ArrowType.Light_bulb2 if directional else ArrowType.Light_bulb1
        return cls(t, direction, flipped, "", color=color, bright=bool(bright))

    @classmethod
    def keyboard(cls, key: Key = Key.NotDefined,
                 direction: Direction = Direction.North, flipped: bool = False) -> "Arrow":
        """Creates a Key arrow bound to the key `key`."""
        try:
            key = Key(key)
        except ValueError:
            raise ValueError(f"Touche invalide : {key}") from None
        return cls(ArrowType.Key, direction, flipped, "", key=key)

    @classmethod
    def wall(cls, color: WallColor = WallColor.White, letter: "str | int | None" = None,
             direction: Direction = Direction.North, flipped: bool = False) -> "Arrow":
        """Creates a Wall of the given color, with an optional letter (A-Z) or digit (0-9).
        `letter`: a character, a Key (Key.A to Key.Num9), or None / "" / 0 for no letter."""
        try:
            color = WallColor(color)
        except ValueError:
            raise ValueError(f"Invalid Wall color: {color}") from None
        if letter is None or letter == "" or (not isinstance(letter, str) and int(letter) == 0):
            index = 0
        elif isinstance(letter, str):
            index = wall_letter_index(letter)
        else:
            index = int(letter)
            if not WALL_LETTER_FIRST <= index <= WALL_LETTER_LAST:
                raise ValueError(f"Invalid letter for a Wall: {letter} (Key.A to Key.Num9)")
        return cls(ArrowType.Wall, direction, flipped, "", wall_color=color, wall_letter=index)

    @property
    def wall_value(self) -> int:
        """16-bit value stored with a letter: (letter << 4) | color."""
        return ((int(self.wall_letter) << 4) | (int(self.wall_color) & 0x0F)) & 0xFFFF

    @property
    def wall_char(self) -> str:
        """Letter or digit shown on the Wall ('' if none)."""
        return wall_letter_char(int(self.wall_letter))

    @property
    def key_value(self) -> int:
        """Stored 16-bit value: key index (0 = not defined)."""
        return int(self.key) & 0xFFFF

    @property
    def display_value(self) -> int:
        """Stored 16-bit value: low byte = color | (0x10 if bright), high byte = 0."""
        return (int(self.color) & 0x0F) | (BRIGHT_FLAG if self.bright else 0)

    @property
    def note_value(self) -> int:
        """Stored 16-bit value: low byte = octave<<4 | note, high byte = instrument."""
        return (((self.octave & 0xF) << 4) | (int(self.pitch) & 0xF)) | (int(self.instrument) << 8)


class Chunk:
    arrows: list[Arrow]

    def __init__(self):
        self.arrows = []
        for _ in range(256):
            self.arrows.append(Arrow())

    def get(self, x: int, y: int) -> Arrow:
        return self.arrows[y*16+x]

    def set(self, x: int, y: int, arrow: Arrow):
        self.arrows[y*16+x] = arrow


class Map:
    version: int = 0
    chunks: dict[tuple[int, int], Chunk]

    def __init__(self, string: None|str = None):
        self.chunks = {}
        if string is not None:
            self.import_(string)

    def get(self, x: int, y: int) -> Arrow:
        chunk_x = x//16
        chunk_y = y//16
        arrow_x = x % 16
        arrow_y = y % 16
        if (chunk_x, chunk_y) not in self.chunks:
            self.chunks[(chunk_x, chunk_y)] = Chunk()
        return self.chunks[(chunk_x, chunk_y)].get(arrow_x, arrow_y)

    def set(self, x: int, y: int, arrow: Arrow):
        chunk_x = x//16
        chunk_y = y//16
        arrow_x = x % 16
        arrow_y = y % 16
        if (chunk_x, chunk_y) not in self.chunks:
            self.chunks[(chunk_x, chunk_y)] = Chunk()

        self.chunks[(chunk_x, chunk_y)].set(arrow_x, arrow_y, arrow)

    def import_(self, string: str):
        raw_data = base64.b64decode(string)
        def pop8() -> int:
            nonlocal raw_data
            val = raw_data[:1]
            raw_data = raw_data[1:]
            return int.from_bytes(val, byteorder='little')
        def pop16() -> int:
            nonlocal raw_data
            val = raw_data[:2]
            raw_data = raw_data[2:]
            return int.from_bytes(val, byteorder='little', signed=True)

        def pop16u() -> int:
            nonlocal raw_data
            val = raw_data[:2]
            raw_data = raw_data[2:]
            return int.from_bytes(val, byteorder='little', signed=False)

        self.version = pop16()
        assert self.version in {0, 4, 5}
        if self.version >= 4:
            compressed = pop8()
            if compressed:
                raw_data = zlib.decompress(raw_data)
        chunks_count = pop16()
        for _ in range(chunks_count):
            chunk_x = pop16()
            if chunk_x & 0x8000:
                chunk_x &= 0x7FFF
                chunk_x *= -1
            chunk_y = pop16()
            if chunk_y & 0x8000:
                chunk_y &= 0x7FFF
                chunk_y *= -1
            arrow_types = pop8()+1
            for _ in range(arrow_types):
                type = pop8()
                type_count = pop8()+1
                for _ in range(type_count):
                    position = pop8()
                    x = position & 0x0F
                    y = (position & 0xF0) >> 4
                    dnf = pop8()
                    has_string = False
                    inline_value = 0      # v5: value stored in bits 4 to 6 of dnf (a Wall's color)
                    strbuf = bytearray()
                    if self.version == 4:
                        has_string = dnf & 1 != 0
                        dnf >>= 1
                    elif self.version == 5:
                        has_string = dnf & 0b1000
                        inline_value = (dnf >> WALL_COLOR_SHIFT) & 0b111
                        dnf &= 0b0111
                    note_value = 0
                    if has_string:
                        if (type == ArrowType.Music_Arrow or type in COLORED_TYPES or type in KEYBOARD_TYPES
                                or (type in WALL_TYPES and self.version >= 5)):
                            # For a Music_Arrow, a colored arrow, a Key or a Wall (v5), these 16 bits are not
                            # a string length but a value (note, color + brightness, key, letter + color).
                            note_value = pop16u()
                        else:
                            cnt = pop16()
                            for _ in range(cnt):
                                strbuf.append(pop8())
                    flipped = dnf & 0b0100 != 0
                    direction = dnf & 0b0011
                    arrow = Arrow()
                    if type == ArrowType.Music_Arrow:
                        arrow.instrument = note_value >> 8
                        arrow.octave = (note_value & 0xF0) >> 4
                        arrow.pitch = note_value & 0x0F
                    elif type in COLORED_TYPES:
                        arrow.color = note_value & 0x0F
                        arrow.bright = bool(note_value & BRIGHT_FLAG)
                    elif type in KEYBOARD_TYPES:
                        try:
                            arrow.key = Key(note_value)
                        except ValueError:
                            arrow.key = note_value  # unknown key: keep the raw value
                    elif type in WALL_TYPES and self.version >= 5:
                        value = note_value if has_string else inline_value
                        arrow.wall_color = value & 0x0F
                        arrow.wall_letter = value >> 4
                    arrow.flipped = flipped
                    arrow.type = ArrowType(type)
                    arrow.direction = Direction(direction)
                    if type == ArrowType.Message and self.version >= 5 and strbuf.startswith(LOGGER_MAGIC) and len(strbuf) > len(LOGGER_MAGIC):
                        # Message header: "LGS1" + 1 flag byte, then the text
                        arrow.logger_flag = strbuf[len(LOGGER_MAGIC)]
                        strbuf = strbuf[len(LOGGER_MAGIC) + 1:]
                    arrow.string = strbuf.decode('utf-8')
                    self.set(chunk_x*16 + x, chunk_y*16 + y, arrow)

    def export(self) -> str:
        raw_data = bytearray([])
        def push8(val: int):
            nonlocal raw_data
            raw_data.extend(val.to_bytes(byteorder='little', length=1))
        def push16(val: int):
            nonlocal raw_data
            raw_data.extend(val.to_bytes(byteorder='little', length=2))

        # Only keep chunks that contain at least one arrow
        exported: list[tuple[int, int, Chunk, list[ArrowType]]] = []
        for (chunk_x, chunk_y), chunk in self.chunks.items():
            types: list[ArrowType] = []
            for arrow in chunk.arrows:
                if arrow.type != ArrowType.Empty_cell and arrow.type not in types:
                    types.append(arrow.type)
            if types:
                exported.append((chunk_x, chunk_y, chunk, types))

        push16(len(exported))
        for chunk_x, chunk_y, chunk, types in exported:
            if chunk_x < 0:
                chunk_x *= -1
                chunk_x |= 0x8000
            if chunk_y < 0:
                chunk_y *= -1
                chunk_y |= 0x8000
            push16(chunk_x)
            push16(chunk_y)
            push8(len(types)-1)
            for type in types:
                push8(type)
                push8(0)
                types_count_index = len(raw_data)-1
                types_count = 0
                for x in range(16):
                    for y in range(16):
                        arrow = chunk.get(x, y)
                        if arrow.type != type: continue
                        position = x | (y << 4)
                        rotation = int(arrow.direction) | (int(arrow.flipped) << 2)
                        is_note = arrow.type == ArrowType.Music_Arrow
                        is_colored = arrow.type in COLORED_TYPES
                        is_keyboard = arrow.type in KEYBOARD_TYPES
                        is_wall = arrow.type in WALL_TYPES
                        wall_color = int(arrow.wall_color)
                        # Wall without a letter: color 0-7 in dnf; otherwise (letter, or color outside 0-7): u16 value.
                        wall_inline = is_wall and arrow.wall_letter == 0 and 0 <= wall_color <= WALL_INLINE_MAX
                        wall_data = is_wall and not wall_inline
                        if is_wall and (wall_color != 0 or arrow.wall_letter != 0) and self.version < 5:
                            raise ValueError("Wall colors and letters require version 5")
                        is_text = arrow.type in TEXT_TYPES and arrow.string != ""
                        has_string = (is_note or is_colored or is_keyboard or wall_data
                                      or (not is_wall and arrow.string != ""))
                        if has_string and self.version < 4:
                            raise ValueError("Attempted to save embedded strings/notes to v0")
                        if self.version == 4:
                            dnf = (rotation << 1) | int(has_string)
                        elif self.version >= 5:
                            dnf = rotation | (0b1000 if has_string else 0) | (TEXT_FLAG if is_text else 0)
                            if wall_inline:
                                dnf |= wall_color << WALL_COLOR_SHIFT
                        else:
                            dnf = rotation
                        push8(position)
                        push8(dnf)
                        if is_note:
                            push16(arrow.note_value)
                        elif is_colored:
                            push16(arrow.display_value)
                        elif is_keyboard:
                            push16(arrow.key_value)
                        elif is_wall:
                            if wall_data:
                                push16(arrow.wall_value)
                        elif arrow.string != "":
                            encoded = arrow.string.encode('utf-8')
                            if arrow.type == ArrowType.Message and self.version >= 5:
                                encoded = LOGGER_MAGIC + bytes([int(arrow.logger_flag) & 0xFF]) + encoded
                            if len(encoded) > MAX_TEXT_BYTES:
                                raise ValueError("Text too long")
                            push16(len(encoded))
                            for c in encoded:
                                push8(c)
                        types_count += 1
                raw_data[types_count_index] = types_count-1
        if self.version >= 4:
            compressed = zlib.compress(raw_data)
            is_compressed = False
            if len(compressed) < len(raw_data):
                raw_data = bytearray(compressed)
                is_compressed = True
            raw_data = bytearray((b'\1' if is_compressed else b'\0') + raw_data)
        raw_data = self.version.to_bytes(byteorder='little', length=2) + raw_data
        return base64.b64encode(raw_data).decode('utf-8')

    def paste(self, x: int, y: int, src: Self|str):
        # for typecheck
        if isinstance(src, str):
            m = Map(src)
        else:
            m = src

        for chunk_x, chunk_y in m.chunks:
            chunk = m.chunks[(chunk_x, chunk_y)]
            for i, arrow in enumerate(chunk.arrows):
                arrow_x = chunk_x * 16 + i % 16 + x
                arrow_y = chunk_y * 16 + i // 16 + y
                self.set(arrow_x, arrow_y, arrow)