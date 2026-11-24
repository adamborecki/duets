"""Data model.

``Tune``  – a lead sheet: one melody line, chord symbols, optional extra voices
            (e.g. the alto/tenor/bass of a hymn harmonisation).
``Piece`` – a finished four-hand arrangement: four hands, chord symbols and
            the annotations the engraver needs.

All durations are ``Fraction`` quarter notes.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Optional

from .theory import Chord, Interval, Key, Meter, Pitch

F = Fraction
HANDS = ("prh", "plh", "srh", "slh")          # primo right/left, secondo right/left
HAND_LABEL = {"prh": "Primo R.H.", "plh": "Primo L.H.", "srh": "Secondo R.H.", "slh": "Secondo L.H."}


@dataclass(frozen=True)
class Ev:
    """A note, chord (several pitches) or rest (no pitches)."""

    dur: Fraction
    pitches: tuple = ()
    tie: bool = False           # tied into the next event
    marks: tuple = ()           # 'stacc', 'accent', 'ten', 'ferm', 'slur(' , 'slur)', 'arp'

    @property
    def is_rest(self) -> bool:
        return not self.pitches

    @property
    def top(self) -> Optional[Pitch]:
        return max(self.pitches, key=lambda p: p.midi) if self.pitches else None

    @property
    def bottom(self) -> Optional[Pitch]:
        return min(self.pitches, key=lambda p: p.midi) if self.pitches else None

    def transposed(self, iv: Interval) -> "Ev":
        return replace(self, pitches=tuple(p + iv for p in self.pitches))

    def shifted(self, octaves: int) -> "Ev":
        return replace(self, pitches=tuple(p.octave_shift(octaves) for p in self.pitches))

    def with_marks(self, *marks: str) -> "Ev":
        return replace(self, marks=tuple(dict.fromkeys(self.marks + marks)))


def N(pitch, dur, **kw) -> Ev:
    """Note (or chord if ``pitch`` is a list/tuple)."""
    if isinstance(pitch, (list, tuple)):
        ps = tuple(sorted(pitch, key=lambda p: (p.midi, p.d)))
    else:
        ps = (pitch,)
    return Ev(F(dur), ps, **kw)


def R(dur) -> Ev:
    return Ev(F(dur))


def total(events) -> Fraction:
    return sum((e.dur for e in events), F(0))


def onsets(events):
    """Yield (offset, event) pairs."""
    t = F(0)
    for e in events:
        yield t, e
        t += e.dur


def sounding_at(events, pos: Fraction) -> Optional[Ev]:
    t = F(0)
    for e in events:
        if t <= pos < t + e.dur:
            return e
        t += e.dur
    return None


def merge_ties(events) -> list:
    """Collapse tied chains of identical pitch content into single long events."""
    out: list = []
    for e in events:
        if out and out[-1].tie and out[-1].pitches == e.pitches and not e.is_rest:
            prev = out[-1]
            out[-1] = replace(prev, dur=prev.dur + e.dur, tie=e.tie,
                              marks=tuple(dict.fromkeys(prev.marks + e.marks)))
        elif out and out[-1].is_rest and e.is_rest:
            out[-1] = replace(out[-1], dur=out[-1].dur + e.dur)
        else:
            out.append(e)
    return out


def fit(events, length: Fraction) -> list:
    """Pad with rests or truncate so the events fill exactly ``length``."""
    out = []
    t = F(0)
    for e in events:
        if t >= length:
            break
        if t + e.dur > length:
            out.append(replace(e, dur=length - t, tie=False))
            t = length
            break
        out.append(e)
        t += e.dur
    if t < length:
        out.append(R(length - t))
    return out


# ---------------------------------------------------------------------------
# Lead sheets
# ---------------------------------------------------------------------------
@dataclass
class TBar:
    """One bar of a lead sheet."""

    length: Fraction
    melody: list = field(default_factory=list)       # list[Ev], sums to length
    chords: list = field(default_factory=list)       # list[(offset, Chord)]
    voices: dict = field(default_factory=dict)       # extra voices: name -> list[Ev]
    pickup: bool = False          # an anacrusis (its notes belong before the barline)
    start_repeat: bool = False
    end_repeat: bool = False
    volta: int = 0                # 1 / 2 when the bar is inside a 1st / 2nd ending
    label: str = ""               # section label that starts here ("A", "B", "Refrain")
    double_bar: bool = False      # a section ends after this bar
    fermata_end: bool = False
    meter: Optional[Meter] = None  # meter change taking effect at this bar
    key: Optional[Key] = None      # key change taking effect at this bar
    intro_start: bool = False      # hymnal "introduction" bracket starts here
    intro_end: bool = False        # ... and ends after this bar

    def chord_at(self, pos: Fraction) -> Optional[Chord]:
        cur = None
        for off, ch in self.chords:
            if off <= pos:
                cur = ch
        return cur


@dataclass
class Tune:
    title: str = "Untitled"
    key: Key = field(default_factory=lambda: Key.parse("C"))
    meter: Meter = field(default_factory=lambda: Meter(4, 4))
    bars: list = field(default_factory=list)
    tempo: int = 100              # beats per minute, in ``meter.beat_len`` units
    tempo_text: str = ""
    subtitle: str = ""
    composer: str = ""
    lyricist: str = ""
    year: Optional[int] = None
    source: str = ""              # where the transcription came from
    credit: str = ""              # attribution line required/polite for the source
    tune_name: str = ""           # hymn tune name, e.g. NUN DANKET
    category: str = ""            # hymn / carol / folk / classical / rag / standard / original ...
    tags: list = field(default_factory=list)
    style: str = ""               # accompaniment style hint (waltz, march, swing, chorale ...)
    slug: str = ""
    free_meter: bool = False
    notes: str = ""
    collection: str = ""
    path: str = ""
    tempo_set: bool = False

    # -- helpers ----------------------------------------------------------
    @property
    def has_chords(self) -> bool:
        return any(b.chords for b in self.bars)

    @property
    def has_satb(self) -> bool:
        return any(b.voices for b in self.bars)

    def melody_pitches(self):
        for b in self.bars:
            for e in b.melody:
                for p in e.pitches:
                    yield p

    def melody_range(self):
        ms = [p.midi for p in self.melody_pitches()]
        return (min(ms), max(ms)) if ms else (60, 72)

    def play_order(self) -> list:
        return play_order(self.bars)


def play_order(bars) -> list:
    """Indices of ``bars`` in performance order, honouring repeats and endings."""
    order: list = []
    i = 0
    n = len(bars)
    rep_start = 0
    passes = 0          # completed passes of the current repeat
    guard = 0
    while i < n and guard < 10000:
        guard += 1
        b = bars[i]
        if b.start_repeat and passes == 0:
            rep_start = i
        if b.volta and b.volta != passes + 1 and b.volta in (1, 2):
            # skip an ending that is not for this pass
            if b.volta == 1 and passes >= 1:
                i += 1
                continue
            if b.volta == 2 and passes == 0:
                i += 1
                continue
        order.append(i)
        if b.end_repeat and passes == 0:
            passes = 1
            i = rep_start
            continue
        if b.end_repeat and passes >= 1:
            passes = 0
            rep_start = i + 1
        elif b.volta == 2 and (i + 1 >= n or bars[i + 1].volta != 2):
            passes = 0
            rep_start = i + 1
        i += 1
    return order


# ---------------------------------------------------------------------------
# Arranged pieces
# ---------------------------------------------------------------------------
@dataclass
class PBar:
    length: Fraction
    hands: dict = field(default_factory=dict)        # hand -> list of voices, voice = list[Ev]
    chords: list = field(default_factory=list)       # list[(offset, Chord)]
    pickup: bool = False
    start_repeat: bool = False
    end_repeat: bool = False
    volta: int = 0
    mark: str = ""                 # boxed rehearsal / section text
    text: str = ""                 # plain text above the system (e.g. "rit.")
    tempo: Optional[tuple] = None  # (text, bpm) change at this bar
    key: Optional[Key] = None      # key change at this bar
    meter: Optional[Meter] = None  # meter change at this bar
    dyn: dict = field(default_factory=dict)          # 'p'/'s' -> dynamic at bar start
    double_bar: bool = False
    final: bool = False

    def voice(self, hand: str, i: int = 0) -> list:
        return self.hands[hand][i]


@dataclass
class Piece:
    title: str
    key: Key
    meter: Meter
    bars: list = field(default_factory=list)
    tempo: int = 100
    tempo_text: str = ""
    subtitle: str = ""
    composer: str = ""
    arranger: str = ""
    credit: str = ""
    category: str = ""
    tags: list = field(default_factory=list)
    flavor: str = ""               # description of the arrangement recipe
    slug: str = ""
    levels: dict = field(default_factory=dict)       # 'p' / 's' -> difficulty 1..5 (float)
    stats: dict = field(default_factory=dict)
    clefs: dict = field(default_factory=dict)        # hand -> 'treble' | 'bass'
    ottava: dict = field(default_factory=dict)       # hand -> 0 | 1
    free_meter: bool = False
    swing: bool = False
    notes: str = ""

    def play_order(self) -> list:
        return play_order(self.bars)

    def hand_pitches(self, hand: str):
        for b in self.bars:
            for v in b.hands.get(hand, []):
                for e in v:
                    for p in e.pitches:
                        yield p
