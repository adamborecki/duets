"""Choosing chords for a melody that comes without any.

A small dynamic programme over the diatonic chords of the key: each bar (or
half bar) takes the chord that best covers the melody notes sounding there,
with a preference for ordinary progressions and a proper cadence at the end.
"""
from __future__ import annotations

from fractions import Fraction

from .model import F, Tune, onsets
from .theory import Chord, Key


def diatonic_chords(key: Key) -> list:
    sc = key.scale()
    if key.is_minorish:
        spec = [(0, "m"), (3, "m"), (4, "7"), (5, ""), (2, ""), (6, ""), (4, "m")]
    else:
        spec = [(0, ""), (3, ""), (4, "7"), (5, "m"), (1, "m"), (4, ""), (2, "m")]
    out = []
    for deg, kind in spec:
        root = sc[deg].in_octave(4)
        if key.mode == "dorian" and deg == 3:
            kind = ""
        if key.mode == "mixolydian" and deg == 6:
            kind = ""
        out.append((deg, Chord(root, kind)))
    return out


_NEXT = {  # (from degree, to degree) -> bonus
    (4, 0): 1.2, (0, 3): 0.5, (0, 4): 0.6, (3, 4): 0.8, (3, 0): 0.6, (1, 4): 0.9, (5, 1): 0.5,
    (5, 3): 0.5, (0, 5): 0.4, (4, 5): 0.2, (0, 0): 0.5, (4, 4): 0.3, (3, 3): 0.2, (2, 5): 0.3,
}


def harmonize(tune: Tune) -> None:
    """Fill in ``bar.chords`` for every bar of a melody-only tune."""
    key = tune.key
    cands = diatonic_chords(key)
    meter = tune.meter
    # harmonic rhythm: two chords per bar in 4/4 and 6/8 when the melody is busy, else one
    slots = []           # (bar index, start, end)
    for i, b in enumerate(tune.bars):
        if b.pickup:
            continue
        half = b.length / 2
        if meter.beats in (4, 2) and b.length == meter.bar_len and meter.beats == 4:
            slots.append((i, F(0), half))
            slots.append((i, half, b.length))
        else:
            slots.append((i, F(0), b.length))
    if not slots:
        return

    def fit(slot, chord: Chord) -> float:
        i, s, e = slot
        b = tune.bars[i]
        score = 0.0
        total = 0.0
        for off, ev in onsets(b.melody):
            if ev.is_rest:
                continue
            a, c = max(off, s), min(off + ev.dur, e)
            if c <= a:
                continue
            w = float(c - a) * (1.6 if meter.strength(off) <= 2 else 1.0)
            total += w
            pc = ev.pitches[0].pc
            if chord.has_pc(pc):
                score += w
            elif any((pc - t.pc) % 12 in (1, 2, 10, 11) for t in chord.tones()):
                score -= 0.35 * w          # a step away from a chord tone: passing note
            else:
                score -= 1.0 * w
        return score / total if total else 0.0

    n = len(slots)
    INF = -1e9
    best = [[INF] * len(cands) for _ in range(n)]
    back = [[0] * len(cands) for _ in range(n)]
    for c, (deg, ch) in enumerate(cands):
        best[0][c] = 3.0 * fit(slots[0], ch) + (0.8 if deg == 0 else 0.0) - 0.15 * c
    for k in range(1, n):
        same_bar = slots[k][0] == slots[k - 1][0]
        for c, (deg, ch) in enumerate(cands):
            f = 3.0 * fit(slots[k], ch) - 0.12 * c
            for p, (pdeg, pch) in enumerate(cands):
                if best[k - 1][p] == INF:
                    continue
                tr = _NEXT.get((pdeg, deg), 0.0)
                if same_bar and p == c:
                    tr += 0.6             # do not change harmony mid-bar without a reason
                val = best[k - 1][p] + f + tr
                if val > best[k][c]:
                    best[k][c] = val
                    back[k][c] = p
    # cadence: end on the tonic
    best[n - 1][0] += 2.5
    c = max(range(len(cands)), key=lambda x: best[n - 1][x])
    path = [c]
    for k in range(n - 1, 0, -1):
        c = back[k][c]
        path.append(c)
    path.reverse()
    for b in tune.bars:
        b.chords = []
    for slot, c in zip(slots, path):
        i, s, e = slot
        ch = cands[c][1]
        bar = tune.bars[i]
        if bar.chords and bar.chords[-1][1] == ch:
            continue
        bar.chords.append((s, ch))
