"""Note data for the practice page: what each hand plays, in performance
order (repeats played out, ties joined), as small integer arrays."""
from __future__ import annotations

from fractions import Fraction

from .lily import hands_of
from .model import F, Piece

TICKS = 24          # per quarter note


def _ticks(x: Fraction) -> int:
    return int(round(float(x) * TICKS))


def piece_notes(piece: Piece) -> dict:
    """{'q': quarter-notes per minute, 'tm': [[tick, qpm], ...] tempo changes,
    'ts': [num, den], 'bars': [start tick of each bar played], 'len': ticks,
    'swing': bool, 'h': {hand: [tick, dur, midi, tick, dur, midi, ...]}}"""
    hands = hands_of(piece)
    order = piece.play_order()
    meter = piece.meter
    out = {h: [] for h in hands}
    opened: dict = {}
    bars = []
    tempo_map = []
    qpm = piece.tempo * float(meter.beat_len)
    t = F(0)

    def flush(key):
        cur = opened.pop(key, None)
        if cur is None:
            return
        start, dur, pitches = cur
        for p in pitches:
            out[key[0]] += [_ticks(start), max(1, _ticks(dur)), p.midi]

    for idx in order:
        b = piece.bars[idx]
        if b.meter is not None:
            meter = b.meter
        if b.tempo is not None:
            tempo_map.append([_ticks(t), round(b.tempo[1] * float(meter.beat_len), 1)])
        bars.append(_ticks(t))
        for h in hands:
            for vi, voice in enumerate(b.hands.get(h, [])):
                key = (h, vi)
                tt = t
                for e in voice:
                    cur = opened.get(key)
                    if e.pitches:
                        if cur is not None and cur[2] == e.pitches and cur[0] + cur[1] == tt:
                            cur[1] += e.dur
                        else:
                            flush(key)
                            opened[key] = [tt, e.dur, e.pitches]
                        if not e.tie:
                            flush(key)
                    else:
                        flush(key)
                    tt += e.dur
        t += b.length
    for key in list(opened):
        flush(key)
    first = piece.bars[order[0]] if order else None
    pickup = _ticks(first.length) if (first is not None and first.pickup) else 0
    data = {"q": round(qpm, 1), "tm": tempo_map, "ts": [piece.meter.num, piece.meter.den],
            "bars": bars, "len": _ticks(t), "swing": bool(piece.swing), "pick": pickup,
            "h": out}
    if getattr(piece, "part_names", None):
        data["names"] = dict(piece.part_names)       # e.g. Piano / Organ
    return data
