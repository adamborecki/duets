"""Difficulty rating and sanity checks for arranged pieces.

Levels run from 1 (beginner: single notes, slow, one position) to 5 (late
intermediate: full chords, octaves, quick figuration).  They are computed
from what is actually on the page, so they stay honest whatever recipe made
the arrangement.
"""
from __future__ import annotations

from fractions import Fraction
from statistics import mean

from .lily import PART_HANDS
from .model import HANDS, Ev, F, Piece, onsets, total
from .notate import written_ok

LEVEL_NAMES = {1: "beginner", 2: "late beginner", 3: "early intermediate", 4: "intermediate", 5: "late intermediate"}


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _hand_events(piece: Piece, hand: str):
    """Yield (bar_index, offset, event) for everything a hand plays.  When the
    hand has two voices their simultaneous notes are merged into one event."""
    for i, b in enumerate(piece.bars):
        voices = [v for v in b.hands.get(hand, []) if v]
        if not voices:
            continue
        if len(voices) == 1:
            for off, e in onsets(voices[0]):
                yield i, off, e
            continue
        merged = {}
        for v in voices:
            prev_tied = False
            for off, e in onsets(v):
                if e.pitches and not prev_tied:
                    cur = merged.get(off)
                    merged[off] = e if cur is None else Ev(min(cur.dur, e.dur), tuple(sorted(
                        set(cur.pitches + e.pitches), key=lambda p: (p.midi, p.d))))
                prev_tied = bool(e.tie and e.pitches)
        for off in sorted(merged):
            yield i, off, merged[off]


def rate_part(piece: Piece, part: str) -> tuple:
    """Return (level, details) for 'p' or 's'."""
    meter = piece.meter
    beat = float(meter.beat_len)
    sec_per_q = 60.0 / max(piece.tempo, 30) / beat        # seconds per quarter note
    pulse = meter.beat_len / (3 if meter.compound else 1)
    hands = PART_HANDS[part]
    per_hand = {}
    bars_active = {h: 0 for h in hands}
    both_active = 0
    indep_sum = 0.0
    n_bars = 0
    for i, b in enumerate(piece.bars):
        if b.pickup:
            continue
        n_bars += 1
        sets = {}
        pitchsets = {}
        for h in hands:
            ons = set()
            pcs = []
            prev_tied = False
            for v in b.hands.get(h, []):
                for off, e in onsets(v):
                    if not e.is_rest and not prev_tied:
                        ons.add(off)
                        pcs.append((off, tuple(sorted(p.pc for p in e.pitches))))
                    prev_tied = e.tie and not e.is_rest
            sets[h] = ons
            pitchsets[h] = pcs
            if ons:
                bars_active[h] += 1
        a, c = sets[hands[0]], sets[hands[1]]
        if a and c:
            both_active += 1
            union = a | c
            inter = a & c
            if pitchsets[hands[0]] == pitchsets[hands[1]]:
                ind = 0.0                         # parallel octaves
            elif a == c:
                ind = 0.35                        # same rhythm, different notes
            elif not inter:
                ind = 0.3                         # hands take turns (oom-pah)
            elif a <= c or c <= a:
                ind = 0.45                        # one hand holds while the other moves
            else:
                ind = 0.6 + 0.4 * (1 - len(inter) / len(union))
            indep_sum += ind
    feats = {}
    speeds, chord_terms, leap_terms, rhythm_terms, spans = [], [], [], [], []
    for h in hands:
        events = [(i, off, e) for i, off, e in _hand_events(piece, h)]
        notes = [(i, off, e) for i, off, e in events if not e.is_rest]
        if not notes:
            continue
        # speed: onsets per second in the busier bars
        per_bar = {}
        prev_tie = False
        for i, off, e in events:
            if not e.is_rest and not prev_tie:
                per_bar[i] = per_bar.get(i, 0) + 1
            prev_tie = e.tie and not e.is_rest
        rates = []
        for i, cnt in per_bar.items():
            dur = float(piece.bars[i].length) * sec_per_q
            if dur > 0:
                rates.append(cnt / dur)
        rates.sort()
        nps = rates[int(len(rates) * 0.75)] if rates else 0.0
        speeds.append(nps)
        sizes = [len(e.pitches) for _, _, e in notes]
        avg_size = mean(sizes)
        span = max((e.top.midi - e.bottom.midi) for _, _, e in notes)
        spans.append(span)
        ct = _clamp((avg_size - 1) * 0.3, 0, 0.9)
        if span >= 12:
            ct += 0.3 * sum(1 for _, _, e in notes if e.top.midi - e.bottom.midi >= 12) / len(notes) + 0.1
        elif span >= 9:
            ct += 0.1
        chord_terms.append(ct)
        # leaps: movement of the hand's centre between consecutive attacks
        centres = [(e.top.midi + e.bottom.midi) / 2 for _, _, e in notes]
        if len(centres) > 1:
            jumps = [abs(a - b) for a, b in zip(centres, centres[1:])]
            big = sum(1 for j in jumps if j > 7) / len(jumps)
            leap_terms.append(_clamp((mean(jumps) - 2.2) / 7.0, 0, 1) * 0.6 + big * 0.8)
        # rhythm: attacks off the pulse, ties, very short notes
        off_grid = 0
        short = 0
        ties = 0
        for i, off, e in notes:
            mp = (meter.bar_len - piece.bars[i].length) if piece.bars[i].pickup else F(0)
            if (mp + off) % pulse != 0:
                off_grid += 1
            if e.dur < pulse / 2:
                short += 1
            if e.tie:
                ties += 1
        rhythm_terms.append(_clamp(0.6 * off_grid / len(notes) + 1.2 * short / len(notes)
                                   + 1.0 * ties / len(notes), 0, 1))
        # pitch range covered
        ms = [p.midi for _, _, e in notes for p in e.pitches]
        feats[h] = {"nps": round(nps, 2), "avg_notes": round(avg_size, 2), "span": span,
                    "range": max(ms) - min(ms)}
    if not speeds:
        return 1.0, {"empty": True}
    speed = _clamp((max(speeds) - 1.6) / 3.6, 0, 1.4)
    # both hands busy is harder than one
    if len(speeds) > 1:
        speed += 0.25 * _clamp((min(speeds) - 1.6) / 3.6, 0, 1)
    chord = max(chord_terms)
    leap = max(leap_terms) if leap_terms else 0.0
    rhythm = max(rhythm_terms)
    together = both_active / max(n_bars, 1)
    indep = (indep_sum / both_active) if both_active else 0.0
    sharps = abs(piece.key.sharps)
    chroma = 0
    count = 0
    for h in hands:
        for _, _, e in _hand_events(piece, h):
            for p in e.pitches:
                count += 1
                if not piece.key.contains(p):
                    chroma += 1
    keyterm = _clamp(max(sharps - 1, 0) / 5.0 + 3.0 * chroma / max(count, 1), 0, 1)
    wide = max((f["range"] for f in feats.values()), default=0)
    reach = _clamp((wide - 9) / 16.0, 0, 1)
    poly = sum(1 for b in piece.bars for h in hands if len([v for v in b.hands.get(h, []) if v]) > 1)
    poly = _clamp(poly / max(n_bars, 1), 0, 1)
    level = (1.0 + 1.35 * speed + 1.1 * chord + 0.9 * leap + 1.3 * indep * together
             + 0.7 * rhythm + 0.5 * keyterm + 0.45 * reach + 0.8 * poly)
    level = _clamp(level, 1.0, 5.0)
    details = {"speed": round(speed, 2), "chord": round(chord, 2), "leap": round(leap, 2),
               "independence": round(indep * together, 2), "rhythm": round(rhythm, 2),
               "key": round(keyterm, 2), "reach": round(reach, 2), "hands": feats}
    return round(level, 1), details


def rate(piece: Piece) -> dict:
    """Fill ``piece.levels`` / ``piece.stats`` and return the levels."""
    for part in ("p", "s"):
        lv, det = rate_part(piece, part)
        piece.levels[part] = lv
        piece.stats[part] = det
    return piece.levels


# ---------------------------------------------------------------------------
# sanity checks
# ---------------------------------------------------------------------------
def _sounding(voices):
    """List of (start, end, low_midi, high_midi) for the notes of a hand in a bar."""
    out = []
    for v in voices:
        for off, e in onsets(v):
            if not e.is_rest:
                out.append((off, off + e.dur, e.bottom.midi, e.top.midi))
    return out


def check(piece: Piece) -> list:
    """Return a list of human-readable problems (empty = clean)."""
    problems = []
    meter = piece.meter
    collisions = 0
    crossings = 0
    for i, b in enumerate(piece.bars):
        if b.meter is not None:
            meter = b.meter
        mp = (meter.bar_len - b.length) if (b.pickup and b.length < meter.bar_len) else F(0)
        for h in HANDS:
            for v in b.hands.get(h, []):
                if total(v) != b.length:
                    problems.append(f"bar {i + 1} {h}: duration {total(v)} != {b.length}")
                if not written_ok(v, meter, mp):
                    problems.append(f"bar {i + 1} {h}: rhythm cannot be notated cleanly")
                for e in v:
                    if e.pitches:
                        span = e.top.midi - e.bottom.midi
                        if span > 12:
                            problems.append(f"bar {i + 1} {h}: stretch of {span} semitones")
                        if e.bottom.midi < 24 or e.top.midi > 103:
                            problems.append(f"bar {i + 1} {h}: pitch out of range")
        plow = _sounding(b.hands.get("plh", [])) + _sounding(b.hands.get("prh", []))
        shigh = _sounding(b.hands.get("srh", [])) + _sounding(b.hands.get("slh", []))
        for (a0, a1, alo, ahi) in plow:
            for (b0, b1, blo, bhi) in shigh:
                if a0 < b1 and b0 < a1 and bhi >= alo:
                    collisions += 1
        for part in ("p", "s"):
            rh = _sounding(b.hands.get(PART_HANDS[part][0], []))
            lh = _sounding(b.hands.get(PART_HANDS[part][1], []))
            for (a0, a1, alo, ahi) in rh:
                for (b0, b1, blo, bhi) in lh:
                    if a0 < b1 and b0 < a1 and bhi > alo:
                        crossings += 1
    if collisions and not getattr(piece, "part_names", None):
        problems.append(f"{collisions} moments where Secondo reaches into the Primo's notes")
    if crossings:
        problems.append(f"{crossings} moments where a player's hands cross")
    return problems
