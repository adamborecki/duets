"""Reading MIDI files (as written by LilyPond) back into bars and voices.

Used to bring existing scores - Diabelli's four-hand duets, easy piano
classics - into the project so they can be engraved in the duet layouts.
Timing is exact (LilyPond's MIDI is not a performance); pitch spelling is
recovered from the key and the melodic direction.
"""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from typing import Optional

from .model import Ev, F, merge_ties
from .theory import Key, Meter, Pitch, pitch_from_lof

GRID = F(1, 24)       # finest rhythmic value kept: a triplet thirty-second


def read_midi(path: Path) -> dict:
    """Return {'staves': [[(onset, dur, midi), ...], ...], 'meters': [(t, Meter)],
    'keys': [(t, Key)], 'tempo': bpm or None, 'end': total length} in quarters."""
    import mido
    mid = mido.MidiFile(str(path))
    tpq = mid.ticks_per_beat
    staves = []
    meters, keys = [], []
    tempo = None
    end = F(0)
    for track in mid.tracks:
        t = 0
        on = defaultdict(list)
        notes = []
        for msg in track:
            t += msg.time
            now = Fraction(t, tpq)
            if msg.type == "time_signature":
                meters.append((now, Meter(msg.numerator, msg.denominator)))
            elif msg.type == "key_signature":
                name = msg.key
                minor = name.endswith("m")
                try:
                    keys.append((now, Key.parse(name[:-1] + " minor" if minor else name)))
                except ValueError:
                    pass
            elif msg.type == "set_tempo" and tempo is None:
                tempo = int(round(60_000_000 / msg.tempo))
            elif msg.type == "note_on" and msg.velocity > 0:
                on[msg.note].append(now)
            elif msg.type in ("note_off", "note_on"):
                if on[msg.note]:
                    s = on[msg.note].pop(0)
                    if now > s:
                        notes.append((s, now - s, msg.note))
                        end = max(end, now)
        if notes:
            staves.append(sorted(notes))
    return {"staves": staves, "meters": _dedupe(meters), "keys": _dedupe(keys), "tempo": tempo, "end": end}


def _dedupe(seq):
    out = []
    for t, v in sorted(seq, key=lambda x: x[0]):
        if out and out[-1][1] == v:
            continue
        if out and out[-1][0] == t:
            out[-1] = (t, v)
        else:
            out.append((t, v))
    return out


def clean_notes(notes: list) -> list:
    """Drop grace notes and repair the notes they stole time from."""
    def on_grid(x):
        return (x / GRID).denominator == 1

    kept = [n for n in notes if on_grid(n[0])]
    onsets = sorted({n[0] for n in kept})
    out = []
    import bisect
    for s, d, m in kept:
        e = s + d
        if not on_grid(e):
            # extend to the next grid point that makes musical sense: the next onset if close
            i = bisect.bisect_left(onsets, e)
            nxt = onsets[i] if i < len(onsets) else None
            up = (e // F(1, 4) + 1) * F(1, 4)
            if nxt is not None and nxt - e <= F(1, 4):
                e = nxt
            else:
                e = up
        if e > s:
            out.append((s, e - s, m))
    return out


def bar_grid(meters: list, end: Fraction, partial: Fraction = F(0)) -> list:
    """Bar start times and lengths: list of (start, length, meter, meter_changed)."""
    if not meters:
        meters = [(F(0), Meter(4, 4))]
    bars = []
    t = F(0)
    mi = 0
    cur = meters[0][1]
    changed = False
    first = True
    while t < end:
        while mi + 1 < len(meters) and meters[mi + 1][0] <= t:
            mi += 1
            cur = meters[mi][1]
            changed = True
        length = cur.bar_len
        if first and partial and partial < length:
            length = partial
        bars.append((t, length, cur, changed and not first))
        changed = False
        first = False
        t += length
    return bars


def split_voices(notes: list, max_voices: int = 2) -> list:
    """Distribute a staff's notes over voices.  Notes that start together and
    last equally long form a chord; a note that starts while another still
    sounds goes to a second voice.  Returns a list of voices, each a list of
    (onset, dur, [midi...]) units."""
    units = defaultdict(list)
    for s, d, m in notes:
        units[(s, d)].append(m)
    items = sorted(units.items(), key=lambda kv: (kv[0][0], -max(kv[1]), -kv[0][1]))
    voices = [[] for _ in range(max_voices)]
    ends = [F(0)] * max_voices
    for (s, d), ms in items:
        free = [v for v in range(max_voices) if ends[v] <= s]
        if free:
            # keep high material in the first voice when both are free
            if len(free) > 1 and voices[1] and voices[0]:
                last0 = max(voices[0][-1][2])
                last1 = max(voices[1][-1][2])
                top = max(ms)
                v = free[0] if abs(top - last0) <= abs(top - last1) or ends[1] < s - 4 else free[1]
                # only use the second voice if it was active very recently
                if ends[1] < s - 2:
                    v = 0
            else:
                v = free[0]
        else:
            # everything is busy: cut the voice that ends first
            v = min(range(max_voices), key=lambda k: ends[k])
            ps, pd, pm = voices[v][-1]
            if s > ps:
                voices[v][-1] = (ps, s - ps, pm)
            else:
                # same onset as a different-length unit already there: merge as chord (shorter length)
                voices[v][-1] = (ps, min(pd, d), sorted(set(pm + ms)))
                ends[v] = ps + min(pd, d)
                continue
        voices[v].append((s, d, sorted(set(ms))))
        ends[v] = s + d
    return [v for v in voices if v]


def spell(midi: int, key: Key, nxt: Optional[int]) -> Pitch:
    """Spell a MIDI pitch in a key; chromatic notes follow where they lead."""
    p = key.spell(midi)
    if key.contains(p) or nxt is None or nxt == midi:
        return p
    step = nxt - midi
    if step in (1, 2) or step > 2:
        # heading upward: a raised note (sharp, or a natural cancelling a flat)
        below = key.spell(midi - 1)
        if key.contains(below):
            cand = Pitch(below.d, below.alter + 1)
            if abs(cand.alter) <= 1 and cand.midi == midi:
                return cand
    if step in (-1, -2) or step < -2:
        above = key.spell(midi + 1)
        if key.contains(above):
            cand = Pitch(above.d, above.alter - 1)
            if abs(cand.alter) <= 1 and cand.midi == midi:
                return cand
    return p


def voice_bars(units: list, bars: list, keys: list) -> list:
    """Cut one voice into bars of events (rests fill the gaps, notes that
    cross a bar line are tied)."""
    def key_at(t):
        cur = keys[0][1] if keys else Key.parse("C")
        for kt, k in keys:
            if kt <= t:
                cur = k
        return cur

    out = []
    ui = 0
    n = len(units)
    carry = None            # (remaining_dur, pitches) of a note tied over the bar line
    for (start, length, meter, _) in bars:
        end = start + length
        evs = []
        t = start
        if carry is not None:
            d, ps = carry
            take = min(d, length)
            evs.append(Ev(take, ps, tie=(d > take)))
            t += take
            carry = (d - take, ps) if d > take else None
        while ui < n and units[ui][0] < end:
            s, d, ms = units[ui]
            if s < t:
                # overlaps what is already written (should not happen after split_voices)
                ui += 1
                continue
            if s > t:
                evs.append(Ev(s - t))
                t = s
            nxt_top = None
            for j in range(ui + 1, min(ui + 4, n)):
                if max(units[j][2]) != max(ms):
                    nxt_top = max(units[j][2])
                    break
            k = key_at(s)
            ps = tuple(sorted((spell(m, k, (nxt_top + (m - max(ms))) if nxt_top is not None else None) for m in ms),
                              key=lambda p: (p.midi, p.d)))
            take = min(d, end - s)
            evs.append(Ev(take, ps, tie=(d > take)))
            t = s + take
            if d > take:
                carry = (d - take, ps)
            ui += 1
        if t < end:
            evs.append(Ev(end - t))
        out.append(merge_ties(evs))
    return out


def staff_bars(notes: list, bars: list, keys: list, max_voices: int = 2) -> list:
    """Bars of a staff: list (per bar) of lists of voices (each a list of Ev)."""
    voices = split_voices(clean_notes(notes), max_voices)
    per_voice = [voice_bars(v, bars, keys) for v in voices]
    out = []
    for i in range(len(bars)):
        vs = [pv[i] for pv in per_voice]
        live = [v for v in vs if any(e.pitches for e in v)]
        out.append(live if live else [[Ev(bars[i][1])]])
    return out


# ---------------------------------------------------------------------------
# finding repeats in written-out music
# ---------------------------------------------------------------------------
def fold_repeats(keys: list, min_len: int = 4, pickup: bool = False) -> list:
    """Given one hashable key per bar (equal keys = identical bars), find
    immediate repetitions and return a list of segments:
        ('plain', [i, ...])
        ('repeat', body_indices, first_ending_indices, second_ending_indices)
    Second passes are dropped; endings that differ become 1st/2nd endings."""
    n = len(keys)
    out = []
    i = 1 if pickup else 0
    if pickup:
        out.append(("plain", [0]))
    plain: list = []
    while i < n:
        best = None
        max_len = (n - i) // 2
        for L in range(max_len, min_len - 1, -1):
            for k in (0, 1, 2):
                if L - k < min_len - 1:
                    continue
                if keys[i:i + L - k] == keys[i + L:i + 2 * L - k]:
                    if k and keys[i + L - k:i + L] == keys[i + 2 * L - k:i + 2 * L]:
                        continue
                    best = (L, k)
                    break
            if best:
                break
        if best:
            L, k = best
            if plain:
                out.append(("plain", plain))
                plain = []
            body = list(range(i, i + L - k))
            first = list(range(i + L - k, i + L))
            second = list(range(i + 2 * L - k, i + 2 * L))
            out.append(("repeat", body, first, second))
            i += 2 * L
        else:
            plain.append(i)
            i += 1
    if plain:
        out.append(("plain", plain))
    return out


def bar_keys(staves: list, bars: list) -> list:
    """One hashable fingerprint per bar, taken from the raw notes of all staves
    (independent of how the notes were later divided into voices)."""
    import bisect
    starts = [b[0] for b in bars]
    keys = [set() for _ in bars]
    for si, notes in enumerate(staves):
        for (s, d, m) in clean_notes(notes):
            i = bisect.bisect_right(starts, s) - 1
            if 0 <= i < len(bars):
                keys[i].add((si, s - starts[i], d, m))
    return [frozenset(k) for k in keys]
