"""A practical ABC notation reader.

Handles what real-world tune collections use: headers, key signatures and
modes, accidentals that last for the bar, note lengths, broken rhythm,
triplets, chords, ties, chord symbols in quotes, repeats with first/second
endings, parts (``P:``), inline fields, multiple voices (``V:``) and voice
overlays (``&``).  Lyrics, slurs, grace notes and ornaments are skipped.

``parse_abc(text)`` returns a list of ``AbcTune``; ``AbcTune.to_tune()`` turns
one into the project's lead-sheet model (``duets.model.Tune``).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional

from .model import Ev, F, TBar, Tune, total
from .theory import STEP_NAMES, Chord, Key, Meter, Pitch


class AbcError(ValueError):
    pass


@dataclass
class AbcBar:
    events: list = field(default_factory=list)       # list[Ev]
    chords: list = field(default_factory=list)       # list[(offset, Chord|None)]
    overlays: list = field(default_factory=list)     # list[list[Ev]]
    start_repeat: bool = False
    end_repeat: bool = False
    double_bar: bool = False
    final_bar: bool = False
    volta: int = 0
    part: str = ""
    key: Optional[Key] = None
    meter: Optional[Meter] = None
    free: bool = False
    intro_start: bool = False
    intro_end: bool = False

    @property
    def length(self) -> Fraction:
        return total(self.events)


@dataclass
class AbcTune:
    headers: dict = field(default_factory=dict)      # field letter -> list of values
    comments: dict = field(default_factory=dict)     # %KEY value pseudo-fields
    meta: dict = field(default_factory=dict)         # %%duets key: value
    key: Key = field(default_factory=lambda: Key.parse("C"))
    meter: Meter = field(default_factory=lambda: Meter(4, 4))
    free_meter: bool = False
    tempo: Optional[int] = None                       # beats per minute (as written)
    tempo_unit: Optional[Fraction] = None             # the note value the tempo counts, in quarters
    voices: dict = field(default_factory=dict)        # voice id -> list[AbcBar]
    voice_order: list = field(default_factory=list)
    voice_props: dict = field(default_factory=dict)
    staves: str = ""
    warnings: list = field(default_factory=list)

    @property
    def title(self) -> str:
        return (self.headers.get("T") or ["Untitled"])[0].strip()

    def header(self, letter: str, default: str = "") -> str:
        v = self.headers.get(letter)
        return v[0].strip() if v else default

    # ------------------------------------------------------------------
    def main_voice(self) -> list:
        return self.voices[self.voice_order[0]]

    def to_tune(self, voice: Optional[str] = None) -> Tune:
        vid = voice or self.voice_order[0]
        bars = self.voices[vid]
        return _to_tune(self, bars)


# ---------------------------------------------------------------------------
# header helpers
# ---------------------------------------------------------------------------
def parse_key_field(text: str):
    """Return (Key or None, properties dict) from the value of a K: field."""
    t = text.split("%")[0].strip()
    props = {}
    for m in re.finditer(r"(clef|octave|transpose|middle|stafflines|staves|stem|name|nm|snm|sname)\s*=\s*(\"[^\"]*\"|\S+)", t):
        props[m.group(1)] = m.group(2).strip('"')
    t = re.sub(r"(clef|octave|transpose|middle|stafflines|staves|stem|name|nm|snm|sname)\s*=\s*(\"[^\"]*\"|\S+)", "", t).strip()
    for word in ("treble", "bass", "alto", "tenor", "perc"):
        if re.search(r"\b%s\b" % word, t):
            props.setdefault("clef", word)
            t = re.sub(r"\b%s\b" % word, "", t).strip()
    if not t or t.lower() == "none":
        return None, props
    if t.upper().startswith("HP"):
        return Key.parse("D"), props
    m = re.match(r"([A-G])([#b]?)\s*([A-Za-z]*)", t)
    if not m:
        return None, props
    try:
        return Key.parse(m.group(0)), props
    except ValueError:
        return None, props


def parse_tempo(text: str):
    """Return (bpm, unit_in_quarters or None) from a Q: field."""
    t = re.sub(r'"[^"]*"', "", text).strip()
    m = re.search(r"(\d+)\s*/\s*(\d+)\s*=\s*(\d+)", t)
    if m:
        unit = Fraction(int(m.group(1)), int(m.group(2))) * 4
        return int(m.group(3)), unit
    m = re.search(r"[A-Za-z]?\s*=?\s*(\d+)", t)
    if m:
        return int(m.group(1)), None
    return None, None


def _key_alter(key: Optional[Key], step: int) -> int:
    if key is None:
        return 0
    for p in key.scale():
        if p.step == step:
            return p.alter
    return 0


# ---------------------------------------------------------------------------
# the scanner
# ---------------------------------------------------------------------------
_NOTE_RE = re.compile(r"(\^\^|\^|__|_|=)?([A-Ga-g])([,']*)")
_LEN_RE = re.compile(r"(\d+)?(/+)?(\d+)?")
_FIELD_LINE = re.compile(r"^([A-Za-z]):(.*)$")


class _Voice:
    def __init__(self, vid: str):
        self.id = vid
        self.bars: list = []
        self.cur = AbcBar()
        self.acc: dict = {}
        self.pending_chords: list = []
        self.pending_marks: list = []
        self.tuplet = None          # [factor, remaining]
        self.broken: Optional[Fraction] = None
        self.volta = 0
        self.part = ""
        self.key_change: Optional[Key] = None
        self.meter_change: Optional[Meter] = None
        self.pending_start_repeat = False
        self.in_overlay = False
        self.overlay_main: list = []
        self.overlay_others: list = []
        self.intro_start = False
        self.octave_shift = 0
        self.key = None
        self.key_set = False


class _Parser:
    def __init__(self):
        self.tune = AbcTune()
        self.unit = None            # default note length as a fraction of a whole note
        self.key: Optional[Key] = None
        self.meter: Optional[Meter] = Meter(4, 4)
        self.free = False
        self.voices: dict = {}
        self.vcur: Optional[_Voice] = None
        self.in_body = False
        self.done = False
        self.header_key: Optional[Key] = None

    # -- voices ---------------------------------------------------------
    def voice(self, vid: str) -> _Voice:
        if vid not in self.voices:
            self.voices[vid] = _Voice(vid)
            self.tune.voice_order.append(vid)
        return self.voices[vid]

    def switch_voice(self, text: str):
        parts = text.split("%")[0].split()
        if not parts:
            return
        vid = parts[0]
        v = self.voice(vid)
        _, props = parse_key_field(" ".join(parts[1:]))
        if props:
            self.tune.voice_props.setdefault(vid, {}).update(props)
        self.vcur = v
        # each voice keeps its own current key (a later voice starts again in the opening key)
        if self.in_body:
            self.key = v.key if v.key_set else self.header_key

    # -- header fields ----------------------------------------------------
    def field(self, letter: str, value: str, inline: bool = False):
        value = value.strip()
        t = self.tune
        if letter == "V":
            self.switch_voice(value)
            return
        if letter == "K":
            key, props = parse_key_field(value)
            if not self.in_body:
                self.key = key
                self.header_key = key
                t.key = key or Key.parse("C")
                self.in_body = True
                if props and self.vcur is not None:
                    t.voice_props.setdefault(self.vcur.id, {}).update(props)
            else:
                if key is not None:
                    self.key = key
                    v = self.vcur or self.voice("1")
                    v.key_change = key
                    v.key = key
                    v.key_set = True
            return
        if letter == "M":
            val = value.split("%")[0].strip()
            if val.lower() == "none" or not val:
                self.free = True
                if not self.in_body:
                    t.free_meter = True
                meter = None
            else:
                try:
                    meter = Meter.parse(val)
                except ValueError:
                    meter = None
            if meter is not None:
                if not self.in_body:
                    self.meter = meter
                    t.meter = meter
                else:
                    self.meter = meter
                    v = self.vcur or self.voice("1")
                    v.meter_change = meter
            return
        if letter == "L":
            m = re.match(r"\s*(\d+)\s*/\s*(\d+)", value)
            if m:
                self.unit = Fraction(int(m.group(1)), int(m.group(2)))
            return
        if letter == "Q":
            bpm, unit = parse_tempo(value)
            if bpm and t.tempo is None:
                t.tempo, t.tempo_unit = bpm, unit
            return
        if letter == "P" and self.in_body:
            v = self.vcur or self.voice("1")
            v.part = value.split("%")[0].strip()
            return
        if letter in ("w", "W"):
            return
        if not inline:
            t.headers.setdefault(letter, []).append(value)

    # -- body -------------------------------------------------------------
    def default_unit(self) -> Fraction:
        if self.unit is not None:
            return self.unit
        m = self.meter or Meter(4, 4)
        return Fraction(1, 16) if Fraction(m.num, m.den) < Fraction(3, 4) else Fraction(1, 8)

    def read_length(self, s: str, i: int):
        m = _LEN_RE.match(s, i)
        num = int(m.group(1)) if m.group(1) else 1
        mult = Fraction(num)
        if m.group(2):
            if m.group(3):
                mult = mult / int(m.group(3))
            else:
                mult = mult / (2 ** len(m.group(2)))
        return mult, m.end()

    def read_pitch(self, s: str, i: int, v: _Voice):
        m = _NOTE_RE.match(s, i)
        if not m:
            return None, i
        acc, letter, octs = m.group(1), m.group(2), m.group(3)
        step = STEP_NAMES.index(letter.upper())
        octave = 4 if letter.isupper() else 5
        octave += octs.count("'") - octs.count(",") + v.octave_shift
        if acc is not None:
            alter = {"^": 1, "^^": 2, "_": -1, "__": -2, "=": 0}[acc]
            v.acc[(step, octave)] = alter
        elif (step, octave) in v.acc:
            alter = v.acc[(step, octave)]
        else:
            alter = _key_alter(self.key, step)
        return Pitch.of(step, alter, octave), m.end()

    def add_event(self, v: _Voice, pitches: tuple, mult: Fraction, tie: bool):
        dur = self.default_unit() * 4 * mult
        if v.tuplet is not None:
            dur = dur * v.tuplet[0]
            v.tuplet[1] -= 1
            if v.tuplet[1] <= 0:
                v.tuplet = None
        if v.broken is not None:
            dur = dur * v.broken
            v.broken = None
        marks = tuple(v.pending_marks) if pitches else ()
        if pitches:
            v.pending_marks = []
        if v.pending_chords:
            off = total(v.cur.events)
            for c in v.pending_chords:
                v.cur.chords.append((off, c))
            v.pending_chords = []
        if v.key_change is not None and not v.cur.events:
            v.cur.key = v.key_change
            v.key_change = None
        if v.meter_change is not None and not v.cur.events:
            v.cur.meter = v.meter_change
            v.meter_change = None
        if v.part and not v.cur.events:
            v.cur.part = v.part
            v.part = ""
        if v.intro_start and not v.cur.events:
            v.cur.intro_start = True
            v.intro_start = False
        v.cur.events.append(Ev(dur, pitches, tie, marks))

    def end_bar(self, v: _Voice, token: str = "|"):
        """Close the current bar at a bar line ``token``."""
        if v.in_overlay:
            v.overlay_others.append(v.cur.events)
            v.cur.events = v.overlay_main
            v.cur.overlays = v.overlay_others
            v.in_overlay = False
            v.overlay_main, v.overlay_others = [], []
        end_rep = token.startswith(":")
        start_rep = token.endswith(":")
        double = ("||" in token) or ("|]" in token) or ("[|" in token)
        final = "|]" in token
        if v.cur.events:
            b = v.cur
            b.volta = v.volta
            b.free = self.free
            if v.pending_start_repeat:
                b.start_repeat = True
                v.pending_start_repeat = False
            b.end_repeat = end_rep
            b.double_bar = double
            b.final_bar = final
            v.bars.append(b)
            if v.volta == 1 and end_rep:
                v.volta = 0
            elif v.volta == 2 and (double or end_rep or start_rep):
                v.volta = 0
            elif v.volta == 2 and self._volta2_done(v):
                v.volta = 0
            elif v.volta > 2 and (double or end_rep or start_rep):
                v.volta = 0
        else:
            if end_rep and v.bars:
                v.bars[-1].end_repeat = True
                if v.volta == 1:
                    v.volta = 0
            if double and v.bars:
                v.bars[-1].double_bar = True
                if v.volta == 2:
                    v.volta = 0
        if start_rep:
            v.pending_start_repeat = True
        carry = AbcBar()
        v.cur = carry
        v.acc = {}

    @staticmethod
    def _volta2_done(v: _Voice) -> bool:
        """A second ending without an explicit end lasts as long as the first."""
        n1 = n2 = 0
        for b in reversed(v.bars):
            if b.volta == 2:
                n2 += 1
            elif b.volta == 1:
                n1 += 1
            else:
                break
        return n1 > 0 and n2 >= n1

    def body_line(self, line: str):
        s = line
        if self.vcur is None:
            self.vcur = self.voice("1")
        v = self.vcur
        i = 0
        n = len(s)
        last_note_idx = None
        while i < n:
            c = s[i]
            if c in " \t":
                i += 1
                continue
            if c == "%":
                break
            if c == "\\":
                i += 1
                continue
            if c == '"':
                j = s.find('"', i + 1)
                if j < 0:
                    break
                text = s[i + 1:j].strip()
                if text and text[0] not in "^_<>@":
                    v.pending_chords.append(Chord.parse(_clean_chord_text(text)))
                i = j + 1
                continue
            if c == "!" or c == "+":
                j = s.find(c, i + 1)
                if j < 0 or j - i > 30:
                    i += 1
                    continue
                name = s[i + 1:j].strip().lower()
                if name == "fermata":
                    v.pending_marks.append("ferm")
                elif name == "sintro":
                    v.intro_start = True
                elif name == "eintro":
                    if v.cur.events:
                        v.cur.intro_end = True
                    elif v.bars:
                        v.bars[-1].intro_end = True
                i = j + 1
                continue
            if c == "{":
                j = s.find("}", i + 1)
                i = j + 1 if j > 0 else n
                continue
            if c == "[":
                # inline field, volta, bar line or chord
                m = re.match(r"\[([A-Za-z]):([^\]]*)\]", s[i:])
                if m:
                    self.field(m.group(1), m.group(2), inline=True)
                    v = self.vcur
                    i += m.end()
                    continue
                m = re.match(r"\[\s*([1-9])", s[i:])
                if m:
                    v.volta = int(m.group(1))
                    i += m.end()
                    while i < n and s[i] in ",-0123456789. ":
                        if s[i] == " ":
                            break
                        i += 1
                    continue
                if i + 1 < n and s[i + 1] == "|":
                    i = self.barline(s, i, v)
                    continue
                # chord
                j = i + 1
                pitches = []
                first_mult = None
                tie_inside = False
                while j < n and s[j] != "]":
                    p, j2 = self.read_pitch(s, j, v)
                    if p is None:
                        j += 1
                        continue
                    mult, j2 = self.read_length(s, j2)
                    if first_mult is None:
                        first_mult = mult
                    if j2 < n and s[j2] == "-":
                        tie_inside = True
                        j2 += 1
                    pitches.append(p)
                    j = j2
                j += 1
                mult, j = self.read_length(s, j)
                tie = tie_inside
                if j < n and s[j] == "-":
                    tie = True
                    j += 1
                if pitches:
                    ps = tuple(sorted(set(pitches), key=lambda p: (p.midi, p.d)))
                    self.add_event(v, ps, (first_mult or Fraction(1)) * mult, tie)
                    last_note_idx = len(v.cur.events) - 1
                i = j
                continue
            if c in "|:":
                i = self.barline(s, i, v)
                continue
            if c == "&":
                # voice overlay: restart the bar in a parallel voice
                if not v.in_overlay:
                    v.in_overlay = True
                    v.overlay_main = v.cur.events
                    v.overlay_others = []
                else:
                    v.overlay_others.append(v.cur.events)
                v.cur.events = []
                i += 1
                continue
            if c == "(":
                m = re.match(r"\((\d)(?::(\d?))?(?::(\d?))?", s[i:])
                if m:
                    p = int(m.group(1))
                    qv = int(m.group(2)) if m.group(2) else None
                    r = int(m.group(3)) if m.group(3) else p
                    if qv is None:
                        compound = self.meter is not None and self.meter.compound
                        qv = {2: 3, 3: 2, 4: 3, 6: 2, 8: 3}.get(p, 3 if compound else 2)
                    v.tuplet = [Fraction(qv, p), r]
                    i += m.end()
                    continue
                i += 1
                continue
            if c == ")":
                i += 1
                continue
            if c in "<>":
                k = 1
                while i + k < n and s[i + k] == c:
                    k += 1
                long_f = {1: Fraction(3, 2), 2: Fraction(7, 4), 3: Fraction(15, 8)}.get(k, Fraction(3, 2))
                short_f = 2 - long_f
                if v.cur.events:
                    prev = v.cur.events[-1]
                    f1, f2 = (long_f, short_f) if c == ">" else (short_f, long_f)
                    v.cur.events[-1] = Ev(prev.dur * f1, prev.pitches, prev.tie, prev.marks)
                    v.broken = f2
                i += k
                continue
            if c in "zx":
                mult, j = self.read_length(s, i + 1)
                self.add_event(v, (), mult, False)
                i = j
                continue
            if c == "Z" or c == "X":
                mult, j = self.read_length(s, i + 1)
                bar_len = (self.meter or Meter(4, 4)).bar_len
                for _ in range(int(mult)):
                    v.cur.events.append(Ev(bar_len))
                    self.end_bar(v, "|")
                i = j
                continue
            if c == "-":
                if v.cur.events and not v.cur.events[-1].is_rest:
                    e = v.cur.events[-1]
                    v.cur.events[-1] = Ev(e.dur, e.pitches, True, e.marks)
                i += 1
                continue
            if c in "^_=" or c in "ABCDEFGabcdefg":
                p, j = self.read_pitch(s, i, v)
                if p is None:
                    i += 1
                    continue
                mult, j = self.read_length(s, j)
                tie = False
                if j < n and s[j] == "-":
                    tie = True
                    j += 1
                self.add_event(v, (p,), mult, tie)
                i = j
                continue
            if c == "H":
                v.pending_marks.append("ferm")
                i += 1
                continue
            if c == ".":
                i += 1
                continue
            # anything else (ornament letters, backquotes, y spacers, ...) is ignored
            if c == "y":
                _, j = self.read_length(s, i + 1)
                i = j
                continue
            i += 1

    def barline(self, s: str, i: int, v: _Voice) -> int:
        j = i
        n = len(s)
        while j < n and s[j] in ":|]":
            j += 1
        if j < n and s[j] == "[" and j + 1 < n and s[j + 1] == "|":
            j += 2
        token = s[i:j]
        if s[i] == "[":
            token = "[|"
            j = i + 2
            while j < n and s[j] in ":|]":
                j += 1
            token = s[i:j]
        self.end_bar(v, token)
        # optional ending number right after the bar line
        m = re.match(r"\s?\[?([1-9])(?![/\d]*[A-Ga-gz])", s[j:])
        m2 = re.match(r"\[?([1-9])", s[j:])
        if m2 and (s[j] == "[" or s[j].isdigit()):
            v.volta = int(m2.group(1))
            j += m2.end()
            while j < n and s[j] in ",-.0123456789":
                j += 1
        return j

    # -- finishing ---------------------------------------------------------
    def finish(self) -> Optional[AbcTune]:
        t = self.tune
        for vid, v in self.voices.items():
            if v.cur.events or v.in_overlay:
                self.end_bar(v, "|]")
            if v.bars:
                v.bars[-1].final_bar = True
            t.voices[vid] = v.bars
        t.voice_order = [vid for vid in t.voice_order if t.voices.get(vid)]
        if not t.voice_order:
            return None
        return t


def _clean_chord_text(text: str) -> str:
    t = text.strip()
    t = t.replace("(", "").replace(")", "")
    # Nottingham writes bass notes in lower case: D7/f#
    return t


def parse_abc(text: str) -> list:
    """Parse the text of an ABC file into a list of ``AbcTune``."""
    tunes = []
    p: Optional[_Parser] = None
    pending_comments: dict = {}
    file_staves = ""
    in_text = False
    for raw in text.splitlines():
        line = raw.rstrip("\r\n")
        stripped = line.strip()
        if in_text:
            if stripped.lower().startswith("%%endtext"):
                in_text = False
            continue
        if stripped.lower().startswith("%%begintext"):
            in_text = True
            continue
        if stripped.startswith("%%duets"):
            m = re.match(r"%%duets\s+([A-Za-z-]+)\s*:\s*(.*)$", stripped)
            if m and p is not None:
                p.tune.meta[m.group(1).lower()] = m.group(2).strip()
            continue
        if stripped.startswith("%%"):
            d = stripped[2:].strip()
            if d.lower().startswith(("staves", "score")):
                if p is not None:
                    p.tune.staves = d
                else:
                    file_staves = d
            continue
        if stripped.startswith("%"):
            m = re.match(r"%([A-Z]{4,})\s+(.*)$", stripped)
            if m:
                (p.tune.comments if p is not None else pending_comments)[m.group(1)] = m.group(2).strip()
            continue
        if not stripped:
            # a blank line ends the tune
            if p is not None and p.in_body and any(v.bars or v.cur.events for v in p.voices.values()):
                p.done = True
            continue
        m = _FIELD_LINE.match(stripped)
        if m and m.group(1) == "X":
            if p is not None:
                t = p.finish()
                if t is not None:
                    tunes.append(t)
            p = _Parser()
            p.tune.comments.update(pending_comments)
            p.tune.staves = file_staves
            p.tune.headers["X"] = [m.group(2).strip()]
            continue
        if p is None:
            continue
        if m and not (p.in_body and m.group(1) in "ABCDEFGabcdefg" and False):
            letter = m.group(1)
            # in the body, only genuine field letters count
            if (not p.in_body) or letter in "KLMPQVwWTIN":
                p.field(letter, m.group(2))
                continue
        if p.in_body and not p.done:
            p.body_line(line)
    if p is not None:
        t = p.finish()
        if t is not None:
            tunes.append(t)
    return tunes


# ---------------------------------------------------------------------------
# AbcTune -> Tune
# ---------------------------------------------------------------------------
def nominal_bar_length(bars, meter: Optional[Meter]) -> Fraction:
    if meter is not None:
        return meter.bar_len
    cnt = Counter(b.length for b in bars)
    return cnt.most_common(1)[0][0]


def guess_meter(length: Fraction) -> Meter:
    table = {F(4): Meter(4, 4), F(3): Meter(3, 4), F(2): Meter(2, 4), F(6): Meter(6, 4),
             F(8): Meter(4, 2), F(3, 2): Meter(3, 8), F(5): Meter(5, 4), F(9, 2): Meter(9, 8)}
    if length in table:
        return table[length]
    fr = Fraction(length) / 4
    return Meter(fr.numerator, fr.denominator) if fr.denominator in (1, 2, 4, 8) else Meter(4, 4)


def _to_tune(abc: AbcTune, bars: list) -> Tune:
    if not bars:
        raise AbcError("no music")
    meter = abc.meter
    free = abc.free_meter
    lengths = Counter(b.length for b in bars)
    common = lengths.most_common(1)[0][0]
    if free:
        meter = guess_meter(common)
    if bars[0].meter is not None:
        meter = bars[0].meter
        bars[0].meter = None
    key0 = abc.key
    if bars[0].key is not None:
        key0 = bars[0].key
        bars[0].key = None
    nominal = meter.bar_len
    tbars = []
    cur_nominal = nominal
    for i, b in enumerate(bars):
        if b.meter is not None:
            cur_nominal = b.meter.bar_len
        from .mxl import spread_stacked
        tb = TBar(length=b.length, melody=list(b.events),
                  chords=spread_stacked(list(b.chords), b.length, b.meter or meter))
        tb.start_repeat = b.start_repeat
        tb.end_repeat = b.end_repeat
        tb.double_bar = b.double_bar
        tb.volta = b.volta
        tb.label = b.part
        tb.meter = b.meter
        tb.key = b.key
        tb.intro_start = b.intro_start
        tb.intro_end = b.intro_end
        if b.length < cur_nominal:
            if i == 0:
                tb.pickup = True
            else:
                prev = tbars[-1]
                if prev.length < cur_nominal and prev.length + b.length == cur_nominal and not prev.pickup:
                    tb.pickup = True
                elif (prev.end_repeat or prev.double_bar or b.start_repeat or b.part) and \
                        b.length <= cur_nominal / 2 and prev.length == cur_nominal:
                    tb.pickup = True
        tbars.append(tb)
    irregular = len(irregular_bars(tbars, meter))
    key = key0
    tune = Tune(title=_tidy_title(abc.title), key=key, meter=meter, bars=tbars)
    tune.free_meter = free or irregular > max(2, len(tbars) // 4)
    if abc.tempo:
        unit = abc.tempo_unit or meter.beat_len
        tune.tempo = int(round(abc.tempo * float(unit / meter.beat_len)))
    else:
        tune.tempo = 0
    tune.composer = abc.header("C")
    tune.source = abc.header("S")
    rhythm = abc.header("R")
    if rhythm:
        tune.style = rhythm.lower()
    return tune


def _tidy_title(t: str) -> str:
    t = t.strip()
    m = re.match(r"^(.*),\s*(The|A|An)$", t)
    if m:
        t = f"{m.group(2)} {m.group(1)}"
    return t


def apply_play_order(tune: Tune, order: str) -> None:
    """Honour a Nottingham-style part order such as ``AAB`` or ``ABAC``: doubled
    parts get repeat signs, other revisits are written out."""
    order = re.sub(r"[^A-Za-z]", "", order or "")
    if not order:
        return
    parts: dict = {}
    cur = None
    for b in tune.bars:
        if b.label:
            cur = b.label.strip()[:1]
        if cur is None:
            cur = order[0]
        parts.setdefault(cur, []).append(b)
    if any(ch not in parts for ch in order):
        return
    import copy
    out = []
    i = 0
    used = set()
    while i < len(order):
        ch = order[i]
        run = 1
        while i + run < len(order) and order[i + run] == ch:
            run += 1
        src = parts[ch]
        bars = src if ch not in used else [copy.deepcopy(b) for b in src]
        used.add(ch)
        has_rep = any(b.end_repeat for b in bars)
        if run >= 2 and not has_rep and not any(b.volta for b in bars):
            first = next((b for b in bars if not b.pickup), bars[0])
            bars[0].start_repeat = True
            bars[-1].end_repeat = True
        out.extend(bars)
        i += run
    for b in out:
        b.double_bar = b.double_bar
    tune.bars = out


def irregular_bars(bars, meter: Meter) -> list:
    """Indices of bars whose length is not explained by the meter, an upbeat,
    or a bar split around a repeat sign."""
    out = []
    nominal = meter.bar_len
    n = len(bars)
    first_pick = bars[0].length if (bars and bars[0].pickup) else None
    for i, b in enumerate(bars):
        if b.meter is not None:
            nominal = b.meter.bar_len
        if b.length == nominal or b.pickup:
            continue
        nxt = bars[i + 1] if i + 1 < n else None
        if nxt is not None and nxt.pickup and nxt.meter is None and b.length + nxt.length == nominal:
            continue
        if b.length < nominal and (i == n - 1 or b.end_repeat or b.volta):
            # last bar (or the bar before a repeat) completing the opening upbeat
            if any(x.pickup and x.length + b.length == nominal for x in bars):
                continue
        out.append(i)
    return out
