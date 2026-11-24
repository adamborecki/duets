"""Turning exact durations into conventional rhythmic notation.

A note of 2.5 quarters starting on beat 2 of a 4/4 bar cannot be written with
one symbol; it has to be split into tied notes in a way that keeps the beats
visible.  ``notate`` does that for one voice of one bar and also groups
triplets.
"""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

from .model import Ev, F
from .theory import Meter

_PLAIN = {
    F(8): "\\breve", F(4): "1", F(2): "2", F(1): "4", F(1, 2): "8",
    F(1, 4): "16", F(1, 8): "32", F(1, 16): "64",
}
_SINGLE = dict(_PLAIN)
for _d, _s in list(_PLAIN.items()):
    if _d <= 4 and _d >= F(1, 8):
        _SINGLE[_d * 3 / 2] = _s + "."


def representable(d: Fraction) -> bool:
    return d in _SINGLE


def lily_dur(d: Fraction) -> str:
    return _SINGLE[d]


def _is_pow2(n: int) -> bool:
    return n > 0 and n & (n - 1) == 0


def _strongest_inside(start: Fraction, end: Fraction, levels) -> Fraction:
    """The metrically strongest grid point strictly between start and end."""
    for u in levels:
        k = (start // u + 1) * u
        if k < end:
            return k
    # fall back: halve
    return start + (end - start) / 2


def _level_of(pos: Fraction, levels) -> int:
    for i, u in enumerate(levels):
        if pos % u == 0:
            return i
    return len(levels)


def _crosses(start: Fraction, end: Fraction, unit: Fraction) -> bool:
    k = (start // unit + 1) * unit
    return k < end


def _note_ok(start: Fraction, end: Fraction, meter: Meter) -> bool:
    d = end - start
    if not representable(d):
        return False
    levels = meter.levels
    a = _level_of(start, levels)
    # never tie over the barline with one symbol
    if _crosses(start, end, levels[0]):
        return False
    if meter.compound:
        beat = meter.beat_len
        if _crosses(start, end, beat):
            # only whole-beat multiples starting on a beat may span beats
            if start % beat != 0 or end % beat != 0:
                return False
            # two beats out of four must start on beat 1 or 3
            if meter.beats == 4 and d == 2 * beat and start % (2 * beat) != 0:
                return False
        return True
    for j, u in enumerate(levels):
        if j >= a:
            break
        if not _crosses(start, end, u):
            continue
        if j < a - 1:
            return False          # hides a boundary two levels above the start
        # crossing a boundary one level up: must end on a grid point of the
        # start's own level (simple syncopation), e.g. 8th-quarter-8th
        if a < len(levels) and end % levels[a] != 0:
            return False
        if a >= len(levels):
            return False
    return True


def _best_note_split(start: Fraction, end: Fraction, meter: Meter) -> Fraction:
    """Where to cut a note that needs a tie: on the strongest grid level that
    falls inside it, preferring the latest point that leaves a clean first part."""
    for u in meter.levels:
        k = (start // u + 1) * u
        if k >= end:
            continue
        points = []
        while k < end:
            points.append(k)
            k += u
        for b in reversed(points):
            if _note_ok(start, b, meter):
                return b
        return points[0]
    return start + (end - start) / 2


def split_note(start: Fraction, dur: Fraction, meter: Meter) -> list:
    """Split a sounding duration into conventionally notated pieces."""
    end = start + dur
    if dur <= 0:
        return []
    if _note_ok(start, end, meter):
        return [dur]
    if dur <= F(1, 16):
        return [dur]
    b = _best_note_split(start, end, meter)
    return split_note(start, b - start, meter) + split_note(b, end - b, meter)


def split_rest(start: Fraction, dur: Fraction, meter: Meter) -> list:
    """Split a silence so that every rest sits squarely on the metric grid."""
    end = start + dur
    if dur <= 0:
        return []
    levels = meter.levels
    for u in levels[1:]:
        if start % u == 0 and dur == u and representable(u):
            return [dur]
    if meter.compound:
        beat = meter.beat_len
        # the first two thirds of a beat may share one rest
        if start % beat == 0 and dur == beat * 2 / 3:
            return [dur]
    else:
        # in 3/4 etc. a rest of exactly one beat or one sub-beat is caught above
        pass
    if dur <= F(1, 16):
        return [dur]
    b = _strongest_inside(start, end, levels)
    return split_rest(start, b - start, meter) + split_rest(b, end - b, meter)


def _ternary(x: Fraction) -> bool:
    return x.denominator % 3 == 0


def notate(events, meter: Meter, mpos: Fraction = F(0)) -> list:
    """Return a list of tokens for one voice of one bar.

    Each token is either an ``Ev`` with a representable duration, or a tuple
    ``("tuplet", (num, den), [Ev, ...])`` whose events carry *written*
    durations.
    """
    out: list = []
    t = F(mpos)
    i = 0
    events = list(events)
    n = len(events)
    while i < n:
        e = events[i]
        if _ternary(e.dur) or _ternary(t):
            # gather a triplet group
            j = i
            span = F(0)
            group = []
            while j < n:
                group.append(events[j])
                span += events[j].dur
                j += 1
                if not _ternary(span) and not _ternary(t + span) and _is_pow2(span.denominator) \
                        and _is_pow2(span.numerator):
                    break
            written = [replace(g, dur=g.dur * 3 / 2) for g in group]
            if all(representable(w.dur) for w in written):
                out.append(("tuplet", (3, 2), written))
            else:
                # could not express: fall back to plain (approximate) notation
                for g in group:
                    out.append(replace(g, dur=_nearest_plain(g.dur)))
            t += span
            i = j
            continue
        if e.is_rest:
            for d in split_rest(t, e.dur, meter):
                out.append(replace(e, dur=d))
        else:
            parts = split_note(t, e.dur, meter)
            last = len(parts) - 1
            end_marks = tuple(m for m in e.marks if m in ("ferm", "slur)"))
            start_marks = tuple(m for m in e.marks if m not in ("ferm", "slur)"))
            for k, d in enumerate(parts):
                marks = ()
                if k == 0:
                    marks += start_marks
                if k == last:
                    marks += end_marks
                out.append(replace(e, dur=d, tie=(True if k < last else e.tie), marks=marks))
        t += e.dur
        i += 1
    return out


def _nearest_plain(d: Fraction) -> Fraction:
    return min(_SINGLE, key=lambda x: abs(x - d))


def written_ok(events, meter: Meter, mpos: Fraction = F(0)) -> bool:
    """True if the voice can be notated without resorting to approximations."""
    try:
        for tok in notate(events, meter, mpos):
            if isinstance(tok, tuple):
                continue
            if not representable(tok.dur):
                return False
        return True
    except Exception:
        return False
