"""Music theory primitives: spelled pitches, intervals, keys, meters, chords.

Everything here keeps *spelling* (F# is not Gb), because the whole point of the
project is sheet music that reads correctly.  Durations elsewhere are
``fractions.Fraction`` counted in quarter notes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from typing import Iterable, Optional

STEP_NAMES = "CDEFGAB"
STEP_SEMIS = (0, 2, 4, 5, 7, 9, 11)
# position of each natural step on the line of fifths, C = 0
STEP_LOF = (0, 2, 4, -1, 1, 3, 5)


# ---------------------------------------------------------------------------
# Intervals
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Interval:
    """A diatonic interval: number of letter steps and number of semitones."""

    steps: int
    semis: int

    def __add__(self, other: "Interval") -> "Interval":
        return Interval(self.steps + other.steps, self.semis + other.semis)

    def __neg__(self) -> "Interval":
        return Interval(-self.steps, -self.semis)

    def __sub__(self, other: "Interval") -> "Interval":
        return self + (-other)


_IV = {
    "P1": (0, 0), "A1": (0, 1), "m2": (1, 1), "M2": (1, 2), "A2": (1, 3),
    "d3": (2, 2), "m3": (2, 3), "M3": (2, 4), "d4": (3, 4), "P4": (3, 5),
    "A4": (3, 6), "d5": (4, 6), "P5": (4, 7), "A5": (4, 8), "m6": (5, 8),
    "M6": (5, 9), "d7": (6, 9), "m7": (6, 10), "M7": (6, 11), "P8": (7, 12),
    "m9": (8, 13), "M9": (8, 14), "A9": (8, 15), "P11": (10, 17),
    "A11": (10, 18), "m13": (12, 20), "M13": (12, 21),
}
IV = {k: Interval(*v) for k, v in _IV.items()}
OCTAVE = IV["P8"]


# ---------------------------------------------------------------------------
# Pitches
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Pitch:
    """A spelled pitch.  ``d`` is the diatonic number (octave*7 + step), so
    C4 (middle C) has d = 28; ``alter`` is -2..+2 semitones."""

    d: int
    alter: int = 0

    # -- constructors -----------------------------------------------------
    @staticmethod
    def of(step: int, alter: int = 0, octave: int = 4) -> "Pitch":
        return Pitch(octave * 7 + step, alter)

    @staticmethod
    def parse(text: str) -> "Pitch":
        """Parse scientific names like ``C4``, ``F#3``, ``Bb5``, ``Ebb2``.
        Without an octave digit the pitch is placed in octave 4."""
        m = re.fullmatch(r"\s*([A-Ga-g])([#b♯♭x]*)(-?\d+)?\s*", text)
        if not m:
            raise ValueError(f"bad pitch {text!r}")
        step = STEP_NAMES.index(m.group(1).upper())
        alter = 0
        for ch in m.group(2):
            alter += {"#": 1, "♯": 1, "b": -1, "♭": -1, "x": 2}[ch]
        octave = int(m.group(3)) if m.group(3) else 4
        return Pitch.of(step, alter, octave)

    # -- properties -------------------------------------------------------
    @property
    def step(self) -> int:
        return self.d % 7

    @property
    def octave(self) -> int:
        return self.d // 7

    @property
    def midi(self) -> int:
        return 12 * (self.octave + 1) + STEP_SEMIS[self.step] + self.alter

    @property
    def pc(self) -> int:
        return self.midi % 12

    @property
    def lof(self) -> int:
        """Position on the line of fifths (C=0, G=1, F=-1, F#=6 ...)."""
        return STEP_LOF[self.step] + 7 * self.alter

    # -- operations -------------------------------------------------------
    def __add__(self, iv: Interval) -> "Pitch":
        d = self.d + iv.steps
        natural = 12 * (d // 7 + 1) + STEP_SEMIS[d % 7]
        return Pitch(d, self.midi + iv.semis - natural)

    def __sub__(self, other):
        if isinstance(other, Interval):
            return self + (-other)
        return Interval(self.d - other.d, self.midi - other.midi)

    def octave_shift(self, n: int) -> "Pitch":
        return Pitch(self.d + 7 * n, self.alter)

    def in_octave(self, octave: int) -> "Pitch":
        return Pitch(octave * 7 + self.step, self.alter)

    def nearest_to(self, midi: float) -> "Pitch":
        """The octave transposition of this pitch class closest to ``midi``."""
        base = self.in_octave(4)
        k = round((midi - base.midi) / 12)
        return base.octave_shift(k)

    def at_or_above(self, midi: int) -> "Pitch":
        p = self.nearest_to(midi)
        while p.midi < midi:
            p = p.octave_shift(1)
        while p.midi - 12 >= midi:
            p = p.octave_shift(-1)
        return p

    def at_or_below(self, midi: int) -> "Pitch":
        p = self.nearest_to(midi)
        while p.midi > midi:
            p = p.octave_shift(-1)
        while p.midi + 12 <= midi:
            p = p.octave_shift(1)
        return p

    def same_class(self, other: "Pitch") -> bool:
        return self.step == other.step and self.alter == other.alter

    # -- text -------------------------------------------------------------
    @property
    def class_name(self) -> str:
        acc = "#" * self.alter if self.alter > 0 else "b" * (-self.alter)
        return STEP_NAMES[self.step] + acc

    @property
    def name(self) -> str:
        return f"{self.class_name}{self.octave}"

    def lily(self) -> str:
        """Absolute LilyPond name (Dutch note names): C4 -> c', Bb2 -> bes,"""
        s = "cdefgab"[self.step]
        if self.alter > 0:
            s += "is" * self.alter
        elif self.alter < 0:
            s += "es" * (-self.alter)
        marks = self.octave - 3
        return s + ("'" * marks if marks >= 0 else "," * (-marks))

    def lily_class(self) -> str:
        s = "cdefgab"[self.step]
        if self.alter > 0:
            s += "is" * self.alter
        elif self.alter < 0:
            s += "es" * (-self.alter)
        return s

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return self.name


P = Pitch.parse


def interval_between(a: Pitch, b: Pitch) -> Interval:
    return Interval(b.d - a.d, b.midi - a.midi)


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------
MODE_LOF = {
    "major": 0, "ionian": 0, "minor": -3, "aeolian": -3, "dorian": -2,
    "mixolydian": -1, "lydian": 1, "phrygian": -4, "locrian": -5,
}
MODE_SCALE = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
}
MODE_SCALE["ionian"] = MODE_SCALE["major"]
MODE_SCALE["aeolian"] = MODE_SCALE["minor"]
MODE_ALIASES = {
    "": "major", "maj": "major", "major": "major", "ion": "major", "ionian": "major",
    "m": "minor", "min": "minor", "minor": "minor", "aeo": "minor", "aeolian": "minor",
    "dor": "dorian", "dorian": "dorian", "mix": "mixolydian", "mixolydian": "mixolydian",
    "lyd": "lydian", "lydian": "lydian", "phr": "phrygian", "phrygian": "phrygian",
    "loc": "locrian", "locrian": "locrian",
}
# default spelling of the five chromatic (non-scale) tones, as scale-degree
# index + alteration relative to the scale tone, keyed by semitones above tonic
_CHROMATIC_MAJORISH = {1: (0, +1), 3: (2, -1), 6: (3, +1), 8: (4, +1), 10: (6, -1)}
_CHROMATIC_MINORISH = {1: (1, -1), 4: (2, +1), 6: (3, +1), 9: (5, +1), 11: (6, +1)}


@dataclass(frozen=True)
class Key:
    tonic: Pitch  # octave is ignored
    mode: str = "major"

    @staticmethod
    def parse(text: str) -> "Key":
        """Parse ``C``, ``Bb``, ``F#m``, ``Am``, ``D dorian``, ``Gmix``, ``E minor``."""
        t = text.strip()
        m = re.match(r"([A-Ga-g])([#b]?)\s*([A-Za-z]*)", t)
        if not m:
            raise ValueError(f"bad key {text!r}")
        tonic = Pitch.of(STEP_NAMES.index(m.group(1).upper()),
                         {"#": 1, "b": -1, "": 0}[m.group(2)], 4)
        word = m.group(3).lower()
        mode = MODE_ALIASES.get(word)
        if mode is None:
            mode = MODE_ALIASES.get(word[:3], "major")
        return Key(tonic, mode)

    @property
    def sharps(self) -> int:
        """Number of sharps (positive) or flats (negative) in the signature."""
        return self.tonic.in_octave(4).lof + MODE_LOF[self.mode]

    @property
    def is_minorish(self) -> bool:
        return self.mode in ("minor", "aeolian", "dorian", "phrygian", "locrian")

    @property
    def name(self) -> str:
        return f"{self.tonic.class_name} {self.mode}"

    @property
    def short(self) -> str:
        if self.mode in ("major", "ionian"):
            return self.tonic.class_name
        if self.mode in ("minor", "aeolian"):
            return self.tonic.class_name + "m"
        return f"{self.tonic.class_name} {self.mode[:3]}"

    @lru_cache(maxsize=None)
    def scale(self) -> tuple:
        """The seven scale tones as pitches in octave 4/5 ascending from the tonic."""
        t = self.tonic.in_octave(4)
        out = []
        for i, semi in enumerate(MODE_SCALE[self.mode]):
            d = t.d + i
            natural = 12 * (d // 7 + 1) + STEP_SEMIS[d % 7]
            out.append(Pitch(d, t.midi + semi - natural))
        return tuple(out)

    def degree(self, deg: int, alter: int = 0) -> Pitch:
        """Scale degree (0-based, may exceed 6) as a pitch near octave 4."""
        sc = self.scale()
        p = sc[deg % 7].octave_shift(deg // 7)
        return Pitch(p.d, p.alter + alter)

    def spell(self, midi: int) -> Pitch:
        """Spell a MIDI pitch the way this key would normally write it."""
        t = self.tonic.in_octave(4)
        rel = (midi - t.midi) % 12
        sc = self.scale()
        semis = MODE_SCALE[self.mode]
        if rel in semis:
            base = sc[semis.index(rel)]
        else:
            table = _CHROMATIC_MINORISH if self.is_minorish else _CHROMATIC_MAJORISH
            if rel in table:
                deg, da = table[rel]
                # the table is defined against major / natural minor; fall back
                # to "raise the tone below" if the mode's scale shifts things
                cand = Pitch(sc[deg].d, sc[deg].alter + da)
                if (cand.midi - t.midi) % 12 != rel:
                    below = max(i for i, s in enumerate(semis) if s < rel)
                    cand = Pitch(sc[below].d, sc[below].alter + (rel - semis[below]))
                base = cand
            else:
                below = max(i for i, s in enumerate(semis) if s < rel)
                base = Pitch(sc[below].d, sc[below].alter + (rel - semis[below]))
        return base.nearest_to(midi)

    def contains(self, p: Pitch) -> bool:
        return any(p.same_class(s) for s in self.scale())

    def degree_of(self, p: Pitch) -> Optional[int]:
        """0-based scale degree of a pitch by letter name (ignores alteration)."""
        return (p.step - self.tonic.step) % 7

    def transpose(self, iv: Interval) -> "Key":
        return Key((self.tonic.in_octave(4) + iv).in_octave(4), self.mode)

    def lily(self) -> str:
        mode = {"ionian": "major", "aeolian": "minor"}.get(self.mode, self.mode)
        return f"\\key {self.tonic.lily_class()} \\{mode}"

    def relative_major_tonic(self) -> Pitch:
        """Tonic of the major key sharing this key's signature."""
        lof = self.sharps
        return pitch_from_lof(lof)


def pitch_from_lof(lof: int) -> Pitch:
    """Pitch class (octave 4) at a line-of-fifths position."""
    step = STEP_LOF.index((lof + 1) % 7 - 1)
    alter = (lof + 1) // 7
    return Pitch.of(step, alter, 4)


# ---------------------------------------------------------------------------
# Meters
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Meter:
    num: int
    den: int

    @staticmethod
    def parse(text: str) -> "Meter":
        t = text.strip()
        if t in ("C", "c", "common"):
            return Meter(4, 4)
        if t in ("C|", "c|", "cut"):
            return Meter(2, 2)
        m = re.match(r"(\d+)\s*/\s*(\d+)", t)
        if not m:
            raise ValueError(f"bad meter {text!r}")
        return Meter(int(m.group(1)), int(m.group(2)))

    @property
    def bar_len(self) -> Fraction:
        return Fraction(self.num * 4, self.den)

    @property
    def compound(self) -> bool:
        return (self.num in (6, 9, 12) and self.den in (8, 16)) or (self.num == 6 and self.den == 4)

    @property
    def beat_len(self) -> Fraction:
        if self.compound:
            return Fraction(12, self.den)
        if self.num == 3 and self.den == 8:
            return Fraction(1, 2)
        return Fraction(4, self.den)

    @property
    def beats(self) -> int:
        return int(self.bar_len / self.beat_len)

    @property
    def levels(self) -> tuple:
        """Metric grid units from the bar down to small subdivisions, in quarters."""
        bar = self.bar_len
        beat = self.beat_len
        lv = [bar]
        if self.compound:
            if self.beats == 4:
                lv.append(beat * 2)
            lv.append(beat)
            sub = beat / 3
        else:
            if self.beats == 4:
                lv.append(beat * 2)
            elif self.beats in (6, 8) and self.num % 2 == 0:
                lv.append(bar / 2)
            lv.append(beat)
            sub = beat / 2
        for _ in range(4):
            lv.append(sub)
            sub = sub / 2
        out = []
        for u in lv:
            if not out or u < out[-1]:
                out.append(u)
        return tuple(out)

    def strength(self, pos: Fraction) -> int:
        """Metric weight of a position in the bar: 0 = downbeat, larger = weaker."""
        for i, u in enumerate(self.levels):
            if pos % u == 0:
                return i
        return len(self.levels)

    def beat_positions(self) -> list:
        return [self.beat_len * i for i in range(self.beats)]

    def lily(self) -> str:
        return f"\\time {self.num}/{self.den}"

    @property
    def text(self) -> str:
        return f"{self.num}/{self.den}"


# ---------------------------------------------------------------------------
# Chords
# ---------------------------------------------------------------------------
# kind -> (interval names above the root, LilyPond chordmode suffix, display suffix)
CHORD_KINDS = {
    "": (("M3", "P5"), "", ""),
    "m": (("m3", "P5"), ":m", "m"),
    "dim": (("m3", "d5"), ":dim", "dim"),
    "aug": (("M3", "A5"), ":aug", "+"),
    "sus4": (("P4", "P5"), ":sus4", "sus4"),
    "sus2": (("M2", "P5"), ":sus2", "sus2"),
    "6": (("M3", "P5", "M6"), ":6", "6"),
    "m6": (("m3", "P5", "M6"), ":m6", "m6"),
    "7": (("M3", "P5", "m7"), ":7", "7"),
    "maj7": (("M3", "P5", "M7"), ":maj7", "maj7"),
    "m7": (("m3", "P5", "m7"), ":m7", "m7"),
    "mmaj7": (("m3", "P5", "M7"), ":m7+", "m(maj7)"),
    "dim7": (("m3", "d5", "d7"), ":dim7", "dim7"),
    "m7b5": (("m3", "d5", "m7"), ":m7.5-", "m7b5"),
    "7sus4": (("P4", "P5", "m7"), ":sus4.7", "7sus4"),
    "aug7": (("M3", "A5", "m7"), ":aug7", "7#5"),
    "7b5": (("M3", "d5", "m7"), ":7.5-", "7b5"),
    "9": (("M3", "P5", "m7", "M9"), ":9", "9"),
    "m9": (("m3", "P5", "m7", "M9"), ":m9", "m9"),
    "maj9": (("M3", "P5", "M7", "M9"), ":maj9", "maj9"),
    "7b9": (("M3", "P5", "m7", "m9"), ":7.9-", "7b9"),
    "7#9": (("M3", "P5", "m7", "A9"), ":7.9+", "7#9"),
    "69": (("M3", "P5", "M6", "M9"), ":6.9", "6/9"),
    "add9": (("M3", "P5", "M9"), ":5.9", "add9"),
    "11": (("M3", "P5", "m7", "M9", "P11"), ":11", "11"),
    "m11": (("m3", "P5", "m7", "M9", "P11"), ":m11", "m11"),
    "13": (("M3", "P5", "m7", "M9", "M13"), ":13", "13"),
    "5": (("P5",), ":1.5", "5"),
}
# what each kind collapses to when a simpler chord is wanted
SIMPLER = {
    "6": "", "m6": "m", "maj7": "", "mmaj7": "m", "9": "7", "m9": "m7", "maj9": "",
    "7b9": "7", "7#9": "7", "69": "", "add9": "", "11": "7", "m11": "m7", "13": "7",
    "7sus4": "7", "sus4": "", "sus2": "", "aug7": "7", "7b5": "7", "5": "",
}
TRIAD_OF = {
    "": "", "m": "m", "dim": "dim", "aug": "aug", "sus4": "", "sus2": "", "6": "",
    "m6": "m", "7": "", "maj7": "", "m7": "m", "mmaj7": "m", "dim7": "dim",
    "m7b5": "dim", "7sus4": "", "aug7": "aug", "7b5": "", "9": "", "m9": "m",
    "maj9": "", "7b9": "", "7#9": "", "69": "", "add9": "", "11": "", "m11": "m",
    "13": "", "5": "",
}

_QUALITY_PATTERNS = [
    # (regex on the normalised quality text, kind)
    (r"(maj|ma|M|Δ|\^)9", "maj9"),
    (r"(maj|ma|M|Δ|\^)(7|11|13)?", "maj7"),
    (r"(m|min|mi|-)(maj|ma|M|Δ)7?", "mmaj7"),
    (r"(m|min|mi|-)7b5|ø7?|h7?", "m7b5"),
    (r"(dim|o|°)7", "dim7"),
    (r"dim|o|°|d", "dim"),
    (r"(m|min|mi|-)11", "m11"),
    (r"(m|min|mi|-)9", "m9"),
    (r"(m|min|mi|-)7", "m7"),
    (r"(m|min|mi|-)6", "m6"),
    (r"(m|min|mi|-)", "m"),
    (r"(aug|\+|a)7|7(#5|\+5|\+|aug)", "aug7"),
    (r"aug|\+|a|#5|\+5", "aug"),
    (r"7sus4?|sus47|11sus", "7sus4"),
    (r"sus4?", "sus4"),
    (r"sus2|2", "sus2"),
    (r"7(b9|-9)", "7b9"),
    (r"7(#9|\+9)", "7#9"),
    (r"7(b5|-5)", "7b5"),
    (r"13", "13"),
    (r"11", "11"),
    (r"9", "9"),
    (r"7", "7"),
    (r"6/?9|69", "69"),
    (r"6", "6"),
    (r"add9|add2", "add9"),
    (r"5", "5"),
    (r"", ""),
]


@dataclass(frozen=True)
class Chord:
    root: Pitch            # octave ignored (kept in octave 4)
    kind: str = ""
    bass: Optional[Pitch] = None

    # -- parsing ----------------------------------------------------------
    @staticmethod
    def parse(text: str) -> Optional["Chord"]:
        """Parse a lead-sheet chord symbol.  Returns None for 'N.C.' and junk."""
        t = text.strip().replace("♯", "#").replace("♭", "b")
        t = t.strip("()")
        if not t or t.upper().startswith("N.C") or t.upper() in ("NC", "N"):
            return None
        m = re.match(r"([A-G])([#b]?)(.*)$", t)
        if not m:
            return None
        root = Pitch.of(STEP_NAMES.index(m.group(1)), {"#": 1, "b": -1, "": 0}[m.group(2)], 4)
        rest = m.group(3).strip()
        bass = None
        if "/" in rest:
            q, b = rest.rsplit("/", 1)
            bm = re.fullmatch(r"\s*([A-Ga-g])([#b]?)\s*", b)
            if bm:
                bass = Pitch.of(STEP_NAMES.index(bm.group(1).upper()),
                                {"#": 1, "b": -1, "": 0}[bm.group(2)], 4)
                rest = q
        q = rest.replace(" ", "").replace("(", "").replace(")", "")
        kind = None
        for pat, k in _QUALITY_PATTERNS:
            if re.fullmatch(pat, q):
                kind = k
                break
        if kind is None:
            # fall back on the leading recognisable part
            ql = q
            if ql.startswith(("maj", "ma", "M")):
                kind = "maj7" if "7" in ql or "9" in ql else ""
            elif ql.startswith(("dim", "o", "°")):
                kind = "dim7" if "7" in ql else "dim"
            elif ql.startswith(("m", "-")):
                kind = "m7" if any(c in ql for c in "79") else ("m6" if "6" in ql else "m")
            elif ql.startswith(("aug", "+")):
                kind = "aug"
            elif any(c in ql for c in ("7", "9", "11", "13")):
                kind = "7"
            else:
                kind = ""
        if bass is not None and bass.same_class(root):
            bass = None
        return Chord(root, kind, bass)

    # -- tones ------------------------------------------------------------
    def intervals(self) -> tuple:
        return tuple(IV[n] for n in CHORD_KINDS[self.kind][0])

    def tones(self) -> list:
        """Root, third, fifth ... as spelled pitches ascending from the root (octave 4)."""
        r = self.root.in_octave(4)
        return [r] + [r + iv for iv in self.intervals()]

    def pcs(self) -> set:
        return {p.pc for p in self.tones()}

    def has_pc(self, pc: int) -> bool:
        return pc % 12 in self.pcs()

    @property
    def third(self) -> Pitch:
        return self.tones()[1]

    @property
    def fifth(self) -> Pitch:
        t = self.tones()
        return t[2] if len(t) > 2 else t[1]

    @property
    def seventh(self) -> Optional[Pitch]:
        t = self.tones()
        if len(t) > 3 and self.kind not in ("add9",):
            return t[3]
        return None

    @property
    def bass_pitch(self) -> Pitch:
        return (self.bass or self.root).in_octave(4)

    @property
    def is_minor(self) -> bool:
        return TRIAD_OF[self.kind] in ("m", "dim")

    @property
    def is_dominant(self) -> bool:
        return self.kind in ("7", "9", "13", "7b9", "7#9", "aug7", "7b5", "11", "7sus4")

    def spell_pc(self, pc: int) -> Optional[Pitch]:
        for p in self.tones():
            if p.pc == pc % 12:
                return p
        if self.bass is not None and self.bass.pc == pc % 12:
            return self.bass.in_octave(4)
        return None

    # -- transformations --------------------------------------------------
    def simplified(self, level: int = 1) -> "Chord":
        """level 0: plain triads; 1: triads + common sevenths; 2: unchanged."""
        if level >= 2:
            return self
        kind = self.kind
        if level == 0:
            kind = TRIAD_OF[kind]
        else:
            while kind in SIMPLER and kind not in ("maj7", "6", "m6", "sus4", "7sus4"):
                kind = SIMPLER[kind]
            if kind in ("maj7", "6", "m6", "sus4", "7sus4") and level < 1:
                kind = SIMPLER[kind]
        return Chord(self.root, kind, self.bass)

    def triad(self) -> "Chord":
        return Chord(self.root, TRIAD_OF[self.kind], self.bass)

    def transpose(self, iv: Interval) -> "Chord":
        root = (self.root.in_octave(4) + iv).in_octave(4)
        bass = (self.bass.in_octave(4) + iv).in_octave(4) if self.bass else None
        root, bass = _tidy_spelling(root, bass)
        return Chord(root, self.kind, bass)

    def without_bass(self) -> "Chord":
        return Chord(self.root, self.kind, None)

    # -- text -------------------------------------------------------------
    @property
    def name(self) -> str:
        s = self.root.class_name + CHORD_KINDS[self.kind][2]
        if self.bass is not None:
            s += "/" + self.bass.class_name
        return s

    def lily(self, dur: str) -> str:
        """LilyPond chordmode token with a duration string like '2.' or '1*3/4'."""
        s = self.root.lily_class() + dur + CHORD_KINDS[self.kind][1]
        if self.bass is not None:
            s += "/" + self.bass.lily_class()
        return s

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.name}>"


def _tidy_spelling(root: Pitch, bass: Optional[Pitch]):
    """Avoid double accidentals and silly roots (Fb, E#, B#, Cb) after transposition."""
    def tidy(p: Pitch) -> Pitch:
        if abs(p.alter) >= 2 or p.class_name in ("Fb", "E#", "B#", "Cb"):
            return enharmonic_simple(p)
        return p
    return tidy(root), (tidy(bass) if bass else None)


def enharmonic_simple(p: Pitch) -> Pitch:
    """Respell with the fewest accidentals (prefers flats for black keys except F#/C#)."""
    names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    q = Pitch.parse(names[p.pc] + "4")
    return q.nearest_to(p.midi)


def spell_midi_in_chord(midi: int, chord: Optional[Chord], key: Key) -> Pitch:
    """Spell a MIDI note as a chord tone if it is one, else as the key would."""
    if chord is not None:
        p = chord.spell_pc(midi % 12)
        if p is not None:
            return p.nearest_to(midi)
    return key.spell(midi)


def transposition_interval(src: Key, dst: Key, direction: str = "nearest") -> Interval:
    """Interval that moves ``src`` tonic to ``dst`` tonic (up or down, at most a tritone
    by default)."""
    a = src.tonic.in_octave(4)
    b = dst.tonic.in_octave(4)
    iv = interval_between(a, b)
    if direction == "up":
        while iv.semis < 0:
            iv = iv + OCTAVE
        while iv.semis >= 12:
            iv = iv - OCTAVE
    elif direction == "down":
        while iv.semis > 0:
            iv = iv - OCTAVE
        while iv.semis <= -12:
            iv = iv + OCTAVE
    else:
        while iv.semis > 6:
            iv = iv - OCTAVE
        while iv.semis < -6:
            iv = iv + OCTAVE
    return iv
