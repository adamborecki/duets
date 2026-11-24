"""Harmony helpers: chord timelines, voicings, bass lines, chord inference."""
from __future__ import annotations

from fractions import Fraction
from itertools import combinations
from typing import Optional

from .model import F, TBar, Tune, onsets
from .theory import CHORD_KINDS, IV, Chord, Key, Meter, Pitch

# ---------------------------------------------------------------------------
# chord timeline
# ---------------------------------------------------------------------------


def fill_chords(tune: Tune) -> None:
    """Make every bar start with an explicit chord (carrying the previous one
    forward) and drop empty/None symbols.  Bars before the first chord get the
    first chord of the tune (or the tonic triad)."""
    first = None
    for b in tune.bars:
        for _, c in b.chords:
            if c is not None:
                first = c
                break
        if first is not None:
            break
    if first is None:
        first = tonic_chord(tune.key)
    cur = None
    for b in tune.bars:
        pts = [(off, c) for off, c in sorted(b.chords, key=lambda x: x[0]) if c is not None and off < b.length]
        # collapse duplicates at the same offset (keep the last written)
        ded = {}
        for off, c in pts:
            ded[off] = c
        pts = sorted(ded.items())
        if not pts or pts[0][0] > 0:
            lead = cur if cur is not None else (pts[0][1] if (pts and b.pickup) else first)
            pts.insert(0, (F(0), lead))
        # drop repeats of the same chord inside a bar
        out = []
        for off, c in pts:
            if out and out[-1][1] == c:
                continue
            out.append((off, c))
        b.chords = out
        cur = out[-1][1]


def tonic_chord(key: Key) -> Chord:
    return Chord(key.tonic.in_octave(4), "m" if key.is_minorish else "")


def spans(bar) -> list:
    """Chord spans of a bar: list of (start, end, chord)."""
    pts = bar.chords
    out = []
    for i, (off, c) in enumerate(pts):
        end = pts[i + 1][0] if i + 1 < len(pts) else bar.length
        if end > off:
            out.append((off, end, c))
    return out


def chord_at(bar, pos: Fraction) -> Optional[Chord]:
    cur = None
    for off, c in bar.chords:
        if off <= pos:
            cur = c
    return cur


# ---------------------------------------------------------------------------
# voicings
# ---------------------------------------------------------------------------
def voicing_tones(chord: Chord, n: int) -> list:
    """Which chord tones to use for an n-note right-hand voicing (as spelled
    pitch classes), most important first."""
    t = chord.tones()
    root, third = t[0], t[1]
    fifth = t[2] if len(t) > 2 else None
    seventh = t[3] if len(t) > 3 else None
    if chord.kind in ("6", "m6", "69"):
        seventh = t[3]
    if chord.kind == "add9":
        seventh = None
    if seventh is not None:
        order = [third, seventh, root, fifth]
        if chord.kind in ("dim7", "m7b5", "aug7", "7b5"):
            order = [third, seventh, fifth, root]
    else:
        order = [third, root, fifth]
    order = [p for p in order if p is not None]
    return order[:max(2, n)] if n < len(order) else order


def candidate_voicings(chord: Chord, n: int, lo: int, hi: int, max_span: int = 12) -> list:
    """All n-note sets of chord tones inside [lo, hi] spanning at most ``max_span``."""
    tones = voicing_tones(chord, 4)
    placed = []
    for p in tones:
        q = p.at_or_above(lo)
        while q.midi <= hi:
            placed.append(q)
            q = q.octave_shift(1)
    need = voicing_tones(chord, n)
    need_pcs = [p.pc for p in need]
    out = []
    for combo in combinations(sorted(placed, key=lambda p: p.midi), n):
        pcs = [p.pc for p in combo]
        if len(set(pcs)) < n:
            continue
        if combo[-1].midi - combo[0].midi > max_span:
            continue
        # must contain the most important tones
        must = need_pcs[:min(n, 2)] if n >= 2 else need_pcs[:1]
        if any(m not in pcs for m in must):
            continue
        if n >= 3 and len(tones) == 3 and set(pcs) != {p.pc for p in tones}:
            continue
        # no seconds at the very bottom in a low register (muddy)
        if n >= 2 and combo[1].midi - combo[0].midi <= 2 and combo[0].midi < 55:
            continue
        out.append(tuple(combo))
    return out


def voice_chord(chord: Chord, n: int, lo: int, hi: int, prev: Optional[tuple] = None,
                target: Optional[float] = None, max_span: int = 12) -> tuple:
    """Pick the n-note voicing closest to ``prev`` (smooth voice leading) or to
    the ``target`` centre pitch."""
    cands = candidate_voicings(chord, n, lo, hi, max_span)
    span_try = max_span
    lo2, hi2 = lo, hi
    guard = 0
    while not cands and guard < 6:
        guard += 1
        lo2 -= 2
        hi2 += 1
        span_try = min(14, span_try + 1)
        cands = candidate_voicings(chord, n, lo2, hi2, span_try)
    if not cands:
        if n > 2:
            return voice_chord(chord, n - 1, lo, hi, prev, target, max_span)
        t = chord.tones()
        return tuple(sorted((t[0].nearest_to((lo + hi) / 2), t[1].nearest_to((lo + hi) / 2)), key=lambda p: p.midi))
    centre = target if target is not None else (lo + hi) / 2

    def cost(v):
        c = 0.0
        if prev:
            pm = sorted(p.midi for p in prev)
            vm = sorted(p.midi for p in v)
            if len(pm) == len(vm):
                c += sum(abs(a - b) for a, b in zip(pm, vm))
            else:
                c += abs(sum(pm) / len(pm) - sum(vm) / len(vm)) * len(vm)
            # mild pull back to the centre so voicings do not drift
            c += 0.15 * abs(sum(vm) / len(vm) - centre)
        else:
            vm = [p.midi for p in v]
            c += abs(sum(vm) / len(vm) - centre)
        # prefer the third or seventh on top a little less than root/fifth: neutral
        return c

    return min(cands, key=cost)


def bass_note(chord: Chord, lo: int, hi: int, prev: Optional[int] = None, centre: Optional[float] = None) -> Pitch:
    """Bass pitch (root or slash bass) in [lo, hi], near the previous bass."""
    b = chord.bass_pitch
    opts = []
    q = b.at_or_above(lo)
    while q.midi <= hi:
        opts.append(q)
        q = q.octave_shift(1)
    if not opts:
        opts = [b.nearest_to((lo + hi) / 2)]
    mid = centre if centre is not None else (lo + hi) / 2

    def cost(p):
        c = 0.25 * abs(p.midi - mid)
        if prev is not None:
            c += abs(p.midi - prev) * 0.5
            if abs(p.midi - prev) > 7:
                c += 2
        return c

    return min(opts, key=cost)


def alternate_bass(chord: Chord, root: Pitch, lo: int, hi: int) -> Pitch:
    """The 'other' bass note for oom-pah patterns: usually the fifth, below the
    root when there is room."""
    if chord.bass is not None and not chord.bass.same_class(chord.root):
        # inverted chord: alternate with the root
        alt = chord.root
    elif chord.kind in ("dim", "dim7", "m7b5", "aug", "aug7", "7b5"):
        alt = chord.third
    else:
        alt = chord.fifth
    below = alt.at_or_below(root.midi - 1)
    above = alt.at_or_above(root.midi + 1)
    if below.midi >= lo:
        return below
    if above.midi <= hi:
        return above
    return below if (lo - below.midi) < (above.midi - hi) else above


def approach_tone(key: Key, frm: Pitch, to: Pitch) -> Pitch:
    """A stepwise approach note leading from ``frm`` towards ``to``."""
    if to.midi > frm.midi:
        # come from below: leading tone a half or whole step under the target
        cand = key.spell(to.midi - 1)
        if not key.contains(cand):
            cand2 = key.spell(to.midi - 2)
            if key.contains(cand2):
                cand = cand2
        return cand
    cand = key.spell(to.midi + 2)
    if not key.contains(cand):
        cand = key.spell(to.midi + 1)
    return cand


# ---------------------------------------------------------------------------
# chord inference from a harmonisation (e.g. SATB hymn settings)
# ---------------------------------------------------------------------------
_TEMPLATES = [
    ("", (0, 4, 7), 0.0), ("m", (0, 3, 7), 0.0), ("7", (0, 4, 7, 10), 0.15),
    ("m7", (0, 3, 7, 10), 0.25), ("maj7", (0, 4, 7, 11), 0.35), ("dim", (0, 3, 6), 0.3),
    ("m7b5", (0, 3, 6, 10), 0.45), ("dim7", (0, 3, 6, 9), 0.45), ("aug", (0, 4, 8), 0.6),
    ("sus4", (0, 5, 7), 0.55), ("6", (0, 4, 7, 9), 0.5), ("m6", (0, 3, 7, 9), 0.6),
]


def _slice_weights(bar: TBar, start: Fraction, end: Fraction, meter: Meter):
    """Pitch-class weights and the lowest sounding pitch in a time window."""
    w: dict = {}
    spelled: dict = {}
    lowest = None
    lowest_w = 0.0
    lines = [bar.melody] + list(bar.voices.values())
    for line in lines:
        for off, e in onsets(line):
            if e.is_rest:
                continue
            a, b = max(off, start), min(off + e.dur, end)
            if b <= a:
                continue
            d = float(b - a)
            strong = meter.strength(off) <= 2 or off < start
            wt = d * (1.0 if strong else 0.55)
            for p in e.pitches:
                w[p.pc] = w.get(p.pc, 0.0) + wt
                spelled.setdefault(p.pc, p)
                if lowest is None or p.midi < lowest.midi or (p.midi == lowest.midi and wt > lowest_w):
                    if lowest is None or p.midi < lowest.midi:
                        lowest, lowest_w = p, wt
    # the lowest pitch that sounds at the start of the window is the bass
    bass = None
    for line in lines:
        for off, e in onsets(line):
            if e.is_rest:
                continue
            if off <= start < off + e.dur:
                for p in e.pitches:
                    if bass is None or p.midi < bass.midi:
                        bass = p
    return w, spelled, (bass or lowest)


def _best_chord(w: dict, spelled: dict, bass: Optional[Pitch], key: Key):
    total = sum(w.values())
    if total <= 0:
        return None, 0.0
    best = None
    best_score = -1e9
    for root_pc in range(12):
        if w.get(root_pc, 0) <= 0 and not (bass is not None and bass.pc == root_pc):
            # allow rootless only for dominant sevenths
            pass
        for kind, tpl, penalty in _TEMPLATES:
            pcs = {(root_pc + t) % 12 for t in tpl}
            inside = sum(v for pc, v in w.items() if pc in pcs)
            outside = total - inside
            missing = sum(1 for pc in pcs if w.get(pc, 0) <= 0)
            score = inside - 1.6 * outside - penalty * total - 0.22 * missing * total
            if w.get(root_pc, 0) <= 0:
                score -= 0.5 * total
            third = (root_pc + tpl[1]) % 12
            if w.get(third, 0) <= 0 and kind != "sus4":
                score -= 0.15 * total
            if bass is not None:
                if bass.pc == root_pc:
                    score += 0.25 * total
                elif bass.pc not in pcs:
                    score -= 0.2 * total
            if score > best_score:
                best_score = score
                best = (root_pc, kind, pcs)
    root_pc, kind, pcs = best
    root = spelled.get(root_pc) or key.spell(60 + root_pc)
    root = root.in_octave(4)
    inside = sum(v for pc, v in w.items() if pc in pcs)
    quality = inside / total
    bass_p = None
    if bass is not None and bass.pc != root_pc and bass.pc in pcs:
        bass_p = bass.in_octave(4)
    return Chord(root, kind, bass_p), quality


def infer_chords(tune: Tune, min_unit: Optional[Fraction] = None) -> None:
    """Derive chord symbols from all sounding voices (melody + extra voices).

    Works top-down: a whole bar gets one symbol if nearly everything in it
    belongs to one chord, otherwise the bar is split at the next metric level.
    """
    meter = tune.meter
    unit = min_unit or meter.beat_len
    for b in tune.bars:
        m = b.meter or meter
        if b.meter is not None:
            meter = b.meter
        out: list = []

        def analyse(start: Fraction, end: Fraction, depth: int):
            w, spelled, bass = _slice_weights(b, start, end, meter)
            ch, qual = _best_chord(w, spelled, bass, tune.key)
            if ch is None:
                return
            length = end - start
            if qual >= 0.93 or length <= unit:
                out.append((start, ch))
                return
            # split at the strongest metric point inside
            levels = meter.levels
            cut = None
            for u in levels:
                k = (start // u + 1) * u
                if k < end:
                    cut = k
                    break
            if cut is None or cut - start < unit or end - cut < unit:
                if length >= 2 * unit:
                    cut = start + (length / 2 // unit) * unit
                    if cut <= start or cut >= end:
                        out.append((start, ch))
                        return
                else:
                    out.append((start, ch))
                    return
            analyse(start, cut, depth + 1)
            analyse(cut, end, depth + 1)

        analyse(F(0), b.length, 0)
        ded = []
        for off, ch in out:
            if ded and ded[-1][1] == ch:
                continue
            ded.append((off, ch))
        b.chords = ded
    # across bar lines: nothing to do (bars keep their first chord explicit)
