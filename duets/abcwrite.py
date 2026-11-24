"""Writing tunes back out as ABC notation (the library's storage format).

The output is plain, standard ABC plus a few ``%%duets key: value`` lines for
metadata that ABC has no field for.  ``duets.library`` reads it back.
"""
from __future__ import annotations

from fractions import Fraction

from .model import Ev, F, TBar, Tune, onsets
from .theory import STEP_NAMES, Key, Pitch

_UNIT = F(1, 2)          # L:1/8


def _len(dur: Fraction) -> str:
    m = Fraction(dur) / _UNIT
    if m == 1:
        return ""
    if m.denominator == 1:
        return str(m.numerator)
    if m.numerator == 1:
        return "/" + str(m.denominator)
    return f"{m.numerator}/{m.denominator}"


def _is_pow2(n: int) -> bool:
    return n > 0 and n & (n - 1) == 0


class _VoiceWriter:
    def __init__(self, key: Key):
        self.key = key
        self.acc: dict = {}

    def new_bar(self):
        self.acc = {}

    def set_key(self, key: Key):
        self.key = key

    def _key_alter(self, step: int) -> int:
        for p in self.key.scale():
            if p.step == step:
                return p.alter
        return 0

    def pitch(self, p: Pitch) -> str:
        step, octave = p.step, p.octave
        cur = self.acc.get((step, octave), self._key_alter(step))
        s = ""
        if p.alter != cur:
            s = {1: "^", 2: "^^", -1: "_", -2: "__", 0: "="}[p.alter]
            self.acc[(step, octave)] = p.alter
        letter = STEP_NAMES[step]
        if octave >= 5:
            s += letter.lower() + "'" * (octave - 5)
        else:
            s += letter + "," * (4 - octave)
        return s

    def event(self, e: Ev, dur: Fraction) -> str:
        s = ""
        if "ferm" in e.marks:
            s += "!fermata!"
        if e.is_rest:
            return s + "z" + _len(dur)
        if len(e.pitches) == 1:
            s += self.pitch(e.pitches[0]) + _len(dur)
        else:
            s += "[" + "".join(self.pitch(p) for p in e.pitches) + "]" + _len(dur)
        if e.tie:
            s += "-"
        return s

    def bar(self, events, chords=()) -> str:
        """One bar of one voice; chord symbols are attached at their offsets."""
        self.new_bar()
        events = _split_at(events, [off for off, _ in chords])
        cmap = {}
        for off, c in chords:
            if c is not None:
                cmap.setdefault(off, []).append(c)
        out = []
        t = F(0)
        i = 0
        n = len(events)
        while i < n:
            e = events[i]
            pre = "".join('"%s"' % c.name for c in cmap.get(t, []))
            if e.dur.denominator % 3 == 0 or t.denominator % 3 == 0:
                j = i
                span = F(0)
                group = []
                while j < n:
                    group.append(events[j])
                    span += events[j].dur
                    j += 1
                    if span.denominator % 3 != 0 and (t + span).denominator % 3 != 0 \
                            and _is_pow2(span.denominator) and _is_pow2(span.numerator):
                        break
                toks = []
                tt = t
                for k, g in enumerate(group):
                    p2 = "".join('"%s"' % c.name for c in cmap.get(tt, [])) if k else ""
                    toks.append(p2 + self.event(g, g.dur * 3 / 2))
                    tt += g.dur
                r = len(group)
                head = "(3" if r == 3 else f"(3:2:{r}"
                out.append(pre + head + "".join(toks))
                t += span
                i = j
                continue
            out.append(pre + self.event(e, e.dur))
            t += e.dur
            i += 1
        return " ".join(out)


def _split_at(events, offsets) -> list:
    """Split notes so that an event starts at each offset (pieces are tied)."""
    cuts = sorted(set(o for o in offsets if o > 0))
    if not cuts:
        return list(events)
    out = []
    t = F(0)
    for e in events:
        start, end = t, t + e.dur
        inner = [c for c in cuts if start < c < end]
        if not inner:
            out.append(e)
        else:
            pts = [start] + inner + [end]
            for k in range(len(pts) - 1):
                d = pts[k + 1] - pts[k]
                last = k == len(pts) - 2
                if e.is_rest:
                    out.append(Ev(d))
                else:
                    out.append(Ev(d, e.pitches, True if not last else e.tie, e.marks if k == 0 else ()))
        t = end
    return out


def _barline(b: TBar, nxt, last: bool) -> str:
    if last:
        return ":|" if b.end_repeat else "|]"
    if b.end_repeat and nxt is not None and nxt.start_repeat:
        return "::"
    if b.end_repeat:
        return ":|"
    if nxt is not None and nxt.start_repeat:
        return "||:" if b.double_bar else "|:"
    if b.double_bar:
        return "||"
    return "|"


def write_abc(tune: Tune, index: int = 1) -> str:
    """Serialise a tune (melody, chords, optional extra voices) as ABC."""
    lines = [f"X:{index}", f"T:{tune.title}"]
    if tune.subtitle:
        lines.append(f"T:{tune.subtitle}")
    if tune.composer:
        lines.append(f"C:{tune.composer}")
    if tune.source:
        lines.append(f"S:{tune.source}")
    if tune.style:
        lines.append(f"R:{tune.style}")
    meta = [("category", tune.category), ("tags", ", ".join(tune.tags)), ("tune", tune.tune_name),
            ("year", str(tune.year) if tune.year else ""), ("credit", tune.credit),
            ("lyricist", tune.lyricist), ("tempo-text", tune.tempo_text), ("notes", tune.notes),
            ("slug", tune.slug)]
    for k, v in meta:
        if v:
            lines.append(f"%%duets {k}: {v}")
    if tune.free_meter:
        lines.append("%%duets free-meter: yes")
    lines.append(f"M:{tune.meter.num}/{tune.meter.den}")
    lines.append("L:1/8")
    if tune.tempo:
        beat = tune.meter.beat_len / 4
        lines.append(f"Q:{beat.numerator}/{beat.denominator}={tune.tempo}")
    voice_names = []
    for b in tune.bars:
        for name in b.voices:
            if name not in voice_names:
                voice_names.append(name)
    mode = {"major": "", "minor": "m"}.get(tune.key.mode, tune.key.mode[:3])
    lines.append(f"K:{tune.key.tonic.class_name}{mode}")
    names = ["S"] + voice_names if voice_names else [None]
    n = len(tune.bars)
    for vn in names:
        if vn is not None:
            lines.append(f"V:{vn}")
        w = _VoiceWriter(tune.key)
        row = []
        if tune.bars and tune.bars[0].start_repeat:
            row.append("|:")
        for i, b in enumerate(tune.bars):
            pre = ""
            if b.label and (vn is None or vn == "S"):
                pre += f"[P:{b.label}]"
            if b.key is not None:
                w.set_key(b.key)
                md = {"major": "", "minor": "m"}.get(b.key.mode, b.key.mode[:3])
                pre += f"[K:{b.key.tonic.class_name}{md}]"
            if b.meter is not None:
                pre += f"[M:{b.meter.num}/{b.meter.den}]"
            if b.volta and (i == 0 or tune.bars[i - 1].volta != b.volta):
                pre += f"[{b.volta} "
            if vn is None or vn == "S":
                body = w.bar(b.melody, b.chords)
            else:
                ev = b.voices.get(vn) or [Ev(b.length)]
                body = w.bar(ev)
            nxt = tune.bars[i + 1] if i + 1 < n else None
            row.append(pre + body + " " + _barline(b, nxt, i == n - 1))
            if len(row) >= 4 or i == n - 1:
                lines.append(" ".join(row))
                row = []
        if row:
            lines.append(" ".join(row))
    return "\n".join(lines) + "\n"
