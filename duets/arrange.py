"""The four-hand arranger: lead sheet in, duet out.

A *recipe* says who carries the tune and how hard each seat should be.  The
melody is placed for one player, and the other player's part is generated from
the chord symbols by a *texture* (sustained pads, oom-pah, Alberti figures,
stride, walking bass ...) using smooth voice leading and registers that keep
the two players out of each other's way.
"""
from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Optional

from . import harmony as H
from .model import HANDS, Ev, F, N, PBar, Piece, R, TBar, Tune, fit, merge_ties, onsets, total
from .theory import IV, OCTAVE, Chord, Interval, Key, Meter, Pitch, pitch_from_lof, MODE_LOF, \
    transposition_interval

# ---------------------------------------------------------------------------
# options
# ---------------------------------------------------------------------------


@dataclass
class Options:
    primo: int = 2                 # target difficulty of the Primo seat, 1..5
    secondo: int = 3               # target difficulty of the Secondo seat, 1..5
    melody: str = "p"              # 'p' = Primo plays the tune, 's' = Secondo, 'swap' = trade by section
    style: str = "auto"            # accompaniment style (see STYLES) or 'auto'
    key: str = "auto"              # 'auto', 'original' or a key name like 'G' / 'Em'
    max_accidentals: int = 3       # for automatic key choice
    seed: int = 0
    ending: bool = True
    tempo: int = 0                 # 0 = keep the tune's tempo / style default
    swing: bool = False


STYLES = ("pad", "chorale", "oompah", "waltz", "march", "alberti", "flowing", "jig", "stride",
          "walking", "ballad", "lullaby", "drone")

# tempo defaults (beats per minute of the meter's beat) when the source has none
_STYLE_TEMPO = {"waltz": 132, "march": 112, "jig": 108, "stride": 84, "walking": 120, "ballad": 76,
                "lullaby": 72, "chorale": 84, "alberti": 108, "flowing": 92, "oompah": 108, "pad": 96,
                "drone": 100, "reel": 100}
_STYLE_TEXT = {"waltz": "Tempo di valse", "march": "Tempo di marcia", "jig": "Lively", "stride": "Not fast",
               "walking": "Easy swing", "ballad": "Slowly, with feeling", "lullaby": "Gently",
               "chorale": "Broadly", "alberti": "Allegretto", "flowing": "Flowing", "oompah": "Brightly",
               "pad": "Moderato", "drone": "Steadily"}


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------
class Line:
    """Collects notes at absolute offsets inside a bar and turns them into a
    gap-free event list (rests fill the holes, overlaps are trimmed)."""

    def __init__(self, length: Fraction):
        self.length = F(length)
        self.items: list = []

    def add(self, start, dur, pitches, marks=(), tie=False):
        start, dur = F(start), F(dur)
        if dur <= 0 or start >= self.length or start < 0:
            return
        if isinstance(pitches, Pitch):
            pitches = (pitches,)
        ps = tuple(sorted(set(pitches), key=lambda p: (p.midi, p.d)))
        if not ps:
            return
        self.items.append([start, min(dur, self.length - start), ps, tuple(marks), tie])

    def events(self) -> list:
        items = sorted(self.items, key=lambda x: x[0])
        out = []
        t = F(0)
        for k, (start, dur, ps, marks, tie) in enumerate(items):
            if start < t:
                continue
            if k + 1 < len(items) and items[k + 1][0] < start + dur:
                dur = items[k + 1][0] - start
            if start > t:
                out.append(R(start - t))
            out.append(Ev(dur, ps, tie, marks))
            t = start + dur
        if t < self.length:
            out.append(R(self.length - t))
        return out

    @property
    def empty(self) -> bool:
        return not self.items


def transpose_tune(tune: Tune, iv: Interval) -> Tune:
    t = copy.deepcopy(tune)
    if iv.steps == 0 and iv.semis == 0:
        return t
    t.key = tune.key.transpose(iv)
    for b in t.bars:
        b.melody = [e.transposed(iv) for e in b.melody]
        b.chords = [(off, c.transpose(iv) if c is not None else None) for off, c in b.chords]
        b.voices = {k: [e.transposed(iv) for e in v] for k, v in b.voices.items()}
        if b.key is not None:
            b.key = b.key.transpose(iv)
    return t


def key_candidates(key: Key, max_acc: int) -> list:
    """Keys with the same mode whose signature has at most ``max_acc`` accidentals."""
    out = []
    for sharps in range(-max_acc, max_acc + 1):
        tonic = pitch_from_lof(sharps - MODE_LOF[key.mode])
        if abs(tonic.alter) > 1:
            continue
        out.append(Key(tonic, key.mode))
    return out


def choose_transposition(tune: Tune, lo: int, hi: int, max_acc: int, prefer_original: float = 1.0,
                         max_shift: int = 7, extra_lines=None) -> Interval:
    """Pick the transposition that best fits the melody into [lo, hi] (MIDI)."""
    notes = [(p.midi, float(e.dur)) for b in tune.bars for e in b.melody for p in e.pitches]
    if not notes:
        return Interval(0, 0)
    best = None
    best_cost = None
    cands = key_candidates(tune.key, max_acc)
    if abs(tune.key.sharps) <= max_acc + 1 and tune.key not in cands:
        cands.append(tune.key)
    for dst in cands:
        base = transposition_interval(tune.key, dst)
        for octs in (-1, 0, 1):
            iv = Interval(base.steps + 7 * octs, base.semis + 12 * octs)
            if abs(iv.semis) > max_shift:
                continue
            cost = 0.0
            wsum = 0.0
            for m, d in notes:
                x = m + iv.semis
                wsum += d
                if x < lo:
                    cost += d * (lo - x) ** 1.5 * 3.0
                elif x > hi:
                    cost += d * (x - hi) ** 1.5 * 2.0
            cost = cost / max(wsum, 1e-9)
            mean = sum((m + iv.semis) * d for m, d in notes) / wsum
            cost += 0.02 * abs(mean - (lo + hi) / 2)
            cost += 0.12 * abs(dst.sharps)
            cost += 0.03 * abs(iv.semis)
            if iv.semis == 0:
                cost -= 0.25 * prefer_original
            if best_cost is None or cost < best_cost - 1e-9:
                best, best_cost = iv, cost
    return best or Interval(0, 0)


def pick_style(tune: Tune, opts: Options) -> str:
    if opts.style != "auto":
        return opts.style
    s = (tune.style or "").lower()
    m = tune.meter
    cat = (tune.category or "").lower()
    for name in STYLES:
        if name in s:
            return name
    if "rag" in s or cat == "rag":
        return "stride"
    if "swing" in s or cat == "standard":
        return "walking" if opts.secondo >= 3 else "ballad"
    if "hymn" in s or cat in ("hymn", "chorale"):
        return "chorale"
    if "lullab" in s:
        return "lullaby"
    if m.num == 3 and m.den == 4:
        return "waltz"
    if m.compound:
        return "jig"
    if "reel" in s or "hornpipe" in s or "polka" in s or "march" in s:
        return "march"
    if cat == "classical":
        return "alberti"
    return "oompah"


def pulse_of(meter: Meter, style: str) -> Fraction:
    """The accompaniment's basic time unit."""
    if meter.compound:
        return meter.beat_len / 3
    if style == "stride" and meter.den == 4 and meter.num == 2:
        return F(1, 2)
    if meter.den == 2:
        return F(1)
    return meter.beat_len


def strong_pulses(meter: Meter, pulse: Fraction) -> set:
    """Positions (in quarters from the bar start) that take a bass note."""
    bar = meter.bar_len
    n = int(bar / pulse)
    if meter.compound:
        per = 3
        return {pulse * i for i in range(0, n, per)}
    if n == 3:
        return {F(0)}
    if n in (4, 8):
        return {pulse * i for i in range(0, n, 2)}
    if n == 2:
        return {F(0)}
    if n == 6:
        return {F(0), pulse * 3} if meter.num == 6 else {F(0), pulse * 2, pulse * 4}
    return {F(0)}


# ---------------------------------------------------------------------------
# the arranger
# ---------------------------------------------------------------------------
class Arranger:
    def __init__(self, tune: Tune, opts: Options):
        self.opts = opts
        self.rng = random.Random(f"{opts.seed}|{tune.title}|{opts.primo}|{opts.secondo}|{opts.melody}")
        t = copy.deepcopy(tune)
        H.fill_chords(t)
        self.style = pick_style(t, opts)
        # chord complexity follows the harder seat
        level = max(opts.primo, opts.secondo)
        cl = 0 if level <= 1 else (1 if level <= 4 else 2)
        if self.style in ("walking", "ballad", "stride"):
            cl = max(cl, 1)
        inferred = tune.has_satb
        for b in t.bars:
            b.chords = _dedupe([(off, plain_chord(c) if inferred else c.simplified(cl)) for off, c in b.chords])
        # key
        if opts.key == "original":
            iv = Interval(0, 0)
        elif opts.key != "auto":
            iv = transposition_interval(t.key, Key(Key.parse(opts.key).tonic, t.key.mode))
            iv = _best_octave(t, iv, 62, 79)
        else:
            iv = choose_transposition(t, 62, 79, opts.max_accidentals)
        self.tune = transpose_tune(t, iv)
        self.shift = iv
        self.key = self.tune.key
        self.meter = self.tune.meter
        self.bars = self.tune.bars
        self.n = len(self.bars)
        self.pulse = pulse_of(self.meter, self.style)
        self._mpos = self._measure_positions()
        self._meters = self._bar_meters()

    # -- geometry -----------------------------------------------------------
    def _bar_meters(self) -> list:
        out = []
        m = self.meter
        for b in self.bars:
            if b.meter is not None:
                m = b.meter
            out.append(m)
        return out

    def _measure_positions(self) -> list:
        """Position inside the measure at which each bar starts."""
        out = []
        m = self.meter
        for i, b in enumerate(self.bars):
            if b.meter is not None:
                m = b.meter
            if b.pickup and b.length < m.bar_len:
                out.append(m.bar_len - b.length)
            else:
                out.append(F(0))
        return out

    def melody_bar(self, i: int) -> list:
        """Melody of bar i as single notes (top pitch of any chords)."""
        out = []
        for e in self.bars[i].melody:
            if e.is_rest:
                out.append(Ev(e.dur))
            else:
                out.append(Ev(e.dur, (e.top,), e.tie, tuple(m for m in e.marks if m == "ferm")))
        return out

    def is_last(self, i: int) -> bool:
        return i == self.n - 1

    def next_chord(self, i: int) -> Optional[Chord]:
        """First chord of the bar played after bar i."""
        b = self.bars[i]
        if b.end_repeat:
            j = i
            while j > 0 and not self.bars[j].start_repeat:
                j -= 1
            return self.bars[j].chords[0][1]
        if i + 1 < self.n:
            return self.bars[i + 1].chords[0][1]
        return None

    # -- run ----------------------------------------------------------------
    def run(self) -> Piece:
        o = self.opts
        roles = self._roles()
        pbars = [PBar(length=b.length) for b in self.bars]
        # melody carriers first, because the accompaniment needs to know where they are
        st = {"prev_rh": None, "prev_bass": None, "alt": 0, "prev_fig": None, "prev_up": None}
        st2 = dict(st)
        for i, b in enumerate(self.bars):
            pb = pbars[i]
            pb.pickup = b.pickup
            pb.start_repeat, pb.end_repeat, pb.volta = b.start_repeat, b.end_repeat, b.volta
            pb.double_bar = b.double_bar
            pb.meter, pb.key = b.meter, b.key
            pb.chords = list(b.chords)
            pb.mark = b.label if (b.label and len(b.label) <= 12) else ""
            if roles[i] == "p":
                prh, plh = self.primo_melody(i)
                pb.hands["prh"], pb.hands["plh"] = [prh], [plh]
            else:
                srh = self.secondo_melody_rh(i)
                pb.hands["srh"] = [srh]
        for i, b in enumerate(self.bars):
            pb = pbars[i]
            if roles[i] == "p":
                ceil = self._secondo_ceiling(pbars, i)
                rh, lh = self.secondo_accompaniment(i, ceil, st)
                pb.hands["srh"], pb.hands["slh"] = [rh], [lh]
            else:
                lh = self.secondo_bass_under_melody(i, pb.hands["srh"][0], st)
                pb.hands["slh"] = [lh]
                floor = self._primo_floor(pbars, i)
                rh, plh = self.primo_accompaniment(i, floor, st2)
                pb.hands["prh"], pb.hands["plh"] = [rh], [plh]
        # dynamics
        first = next((i for i, b in enumerate(self.bars) if not b.pickup), 0)
        pbars[0].dyn = {"p": "mf", "s": "mp"} if roles[0] == "p" else {"p": "mp", "s": "mf"}
        for i in range(1, self.n):
            if roles[i] != roles[i - 1]:
                pbars[i].dyn = {"p": "mf", "s": "mp"} if roles[i] == "p" else {"p": "mp", "s": "mf"}
        pbars[-1].final = True
        tune = self.tune
        tempo = o.tempo or tune.tempo or _STYLE_TEMPO.get(self.style, 100)
        text = tune.tempo_text or _STYLE_TEXT.get(self.style, "")
        piece = Piece(title=tune.title, key=self.key, meter=self.meter, bars=pbars, tempo=tempo,
                      tempo_text=text, subtitle=tune.subtitle, composer=tune.composer,
                      credit=tune.credit, category=tune.category, tags=list(tune.tags),
                      slug=tune.slug, free_meter=tune.free_meter)
        piece.swing = o.swing or self.style == "walking"
        piece.flavor = self.describe(roles)
        return piece

    def describe(self, roles) -> str:
        who = {"p": "tune in Primo", "s": "tune in Secondo"}
        if len(set(roles)) > 1:
            return f"tune shared between the players · {self.style}"
        return f"{who[roles[0]]} · {self.style}"

    def _roles(self) -> list:
        """Who has the melody in each bar."""
        mode = self.opts.melody
        if mode in ("p", "s"):
            return [mode] * self.n
        # swap: change hands at section boundaries (labels, double bars, repeats)
        roles = []
        cur = "p"
        sections = 0
        for i, b in enumerate(self.bars):
            boundary = i > 0 and (b.label or self.bars[i - 1].double_bar or
                                  (b.start_repeat and not b.pickup) or
                                  (self.bars[i - 1].end_repeat and not b.volta))
            if boundary and not (b.pickup and i == 0):
                sections += 1
                cur = "s" if cur == "p" else "p"
            roles.append(cur)
        if sections == 0:
            # no marked sections: swap half way, at a phrase boundary
            half = self._half_point()
            roles = ["p" if i < half else "s" for i in range(self.n)]
        # pickup bars belong to the bar they lead into
        for i in range(self.n - 1):
            if self.bars[i].pickup:
                roles[i] = roles[i + 1]
        return roles

    def _half_point(self) -> int:
        full = [i for i, b in enumerate(self.bars) if not b.pickup]
        if len(full) < 8:
            return self.n
        mid = full[len(full) // 2]
        k = full.index(mid)
        k -= k % 4 if k % 4 <= 2 else (k % 4) - 4
        return full[min(max(k, 4), len(full) - 1)]

    # -- registers ------------------------------------------------------------
    def _secondo_ceiling(self, pbars, i: int) -> int:
        """Highest pitch the Secondo right hand may use in bar i without
        bumping into the Primo."""
        lows = []
        for j in (i - 1, i, i + 1):
            if 0 <= j < self.n:
                for h in ("plh", "prh"):
                    for v in pbars[j].hands.get(h, []):
                        for e in v:
                            if e.pitches:
                                lows.append(e.bottom.midi)
        floor = min(lows) if lows else 72
        return max(55, min(64, floor - 3))

    def _primo_floor(self, pbars, i: int) -> int:
        highs = []
        for j in (i - 1, i, i + 1):
            if 0 <= j < self.n:
                for v in pbars[j].hands.get("srh", []):
                    for e in v:
                        if e.pitches:
                            highs.append(e.top.midi)
        top = max(highs) if highs else 60
        return max(67, top + 3)

    # -- Primo with the melody ------------------------------------------------
    def primo_melody(self, i: int):
        level = self.opts.primo
        mel = self.melody_bar(i)
        b = self.bars[i]
        lh = [e for e in mel]
        rh = [e.shifted(1) for e in mel]
        if level >= 3:
            rh = self._add_thirds(i, rh, dense=(level >= 4))
        if level >= 4 and not b.pickup:
            lh = self._primo_figuration(i, rh)
        if level <= 1:
            lh = self._simplify_double(i, lh)
        if self.is_last(i) and self.opts.ending and not b.end_repeat:
            rh = _fermata_last(rh)
            lh = _fermata_last(lh)
        return rh, lh

    def _simplify_double(self, i: int, lh: list) -> list:
        """Level 1: the left hand doubles the tune only where it is slow enough;
        runs of short notes are left to the right hand alone."""
        pulse = self.pulse
        if all(e.dur >= pulse for e in lh if not e.is_rest):
            return lh
        out = []
        for e in lh:
            if e.is_rest or e.dur >= pulse:
                out.append(e)
            else:
                out.append(Ev(e.dur))
        return merge_ties(out)

    def _add_thirds(self, i: int, rh: list, dense: bool) -> list:
        """Put a third or sixth under melody notes where the harmony allows."""
        b = self.bars[i]
        mp = self._mpos[i]
        m = self._meters[i]
        out = []
        t = F(0)
        for e in rh:
            if e.is_rest or len(e.pitches) != 1:
                out.append(e)
                t += e.dur
                continue
            pos = mp + t
            on_pulse = pos % self.pulse == 0
            strong = m.strength(pos) <= (2 if dense else 1)
            ok = e.dur >= self.pulse and on_pulse and (strong or e.dur >= 2 * self.pulse)
            if ok:
                ch = H.chord_at(b, t)
                top = e.pitches[0]
                add = None
                if ch is not None and ch.has_pc(top.pc):
                    deg = None
                    for steps in (2, 5):          # a third, then a sixth, below
                        cand = _diatonic_below(self.key, top, steps)
                        if ch.has_pc(cand.pc) and 3 <= top.midi - cand.midi <= 9:
                            add = ch.spell_pc(cand.pc).nearest_to(cand.midi)
                            break
                if add is not None:
                    out.append(Ev(e.dur, tuple(sorted((add, top), key=lambda p: p.midi)), e.tie, e.marks))
                    t += e.dur
                    continue
            out.append(e)
            t += e.dur
        # a tie needs identical pitch content on both sides: drop added notes that break ties
        fixed = []
        for k, e in enumerate(out):
            if k > 0 and out[k - 1].tie and len(out[k - 1].pitches) != len(e.pitches):
                prev = fixed[-1]
                top_prev = prev.top
                fixed[-1] = Ev(prev.dur, (top_prev,), prev.tie, prev.marks)
                e = Ev(e.dur, (e.top,), e.tie, e.marks) if e.pitches else e
            fixed.append(e)
        return fixed

    def _primo_figuration(self, i: int, rh: list) -> list:
        """Level 4+: broken-chord figure in the Primo left hand."""
        b = self.bars[i]
        lows = [e.bottom.midi for e in rh if e.pitches]
        top = min(74, (min(lows) - 3) if lows else 74)
        lo = top - 14
        line = Line(b.length)
        mp = self._mpos[i]
        m = self._meters[i]
        sub = self.pulse / 2 if not m.compound else self.pulse
        for (s, e_, ch) in H.spans(b):
            v = H.voice_chord(ch, 3, lo, top, None, target=(lo + top) / 2 + 1)
            low, mid, high = v[0], v[1], v[-1]
            if m.compound:
                cyc = [low, mid, high]
            elif m.num == 3:
                cyc = [low, high, mid, high, mid, high]
            else:
                cyc = [low, high, mid, high]
            t = s
            k = int(((mp + s) / sub)) % len(cyc)
            while t < e_:
                line.add(t, min(sub, e_ - t), cyc[k % len(cyc)])
                k += 1
                t += sub
        if self.is_last(i) and self.opts.ending:
            ch = b.chords[-1][1]
            v = H.voice_chord(ch, 3, lo, top, None)
            line = Line(b.length)
            line.add(0, _final_len(b, self.melody_bar(i)), v)
        return line.events()

    # -- Secondo with the melody ----------------------------------------------
    def secondo_melody_rh(self, i: int) -> list:
        mel = [e.shifted(-1) for e in self.melody_bar(i)]
        if self.is_last(i) and self.opts.ending and not self.bars[i].end_repeat:
            mel = _fermata_last(mel)
        return mel

    def secondo_bass_under_melody(self, i: int, rh: list, st: dict) -> list:
        b = self.bars[i]
        level = self.opts.secondo
        line = Line(b.length)
        if b.pickup and b.length <= self._meters[i].bar_len / 2:
            return line.events()
        lows = [e.bottom.midi for e in rh if e.pitches]
        hi = min(50, (min(lows) - 3) if lows else 50)
        lo = 36
        m = self._meters[i]
        mp = self._mpos[i]
        strong = strong_pulses(m, self.pulse)
        last = self.is_last(i) and self.opts.ending
        for (s, e_, ch) in H.spans(b):
            root = H.bass_note(ch, lo, hi, st["prev_bass"], centre=43)
            st["prev_bass"] = root.midi
            if last:
                line.add(s, _final_len(b, rh) - s if s == 0 else e_ - s, root,
                         marks=("ferm",) if (s == H.spans(b)[-1][0] and not b.end_repeat) else ())
                continue
            if level <= 1:
                line.add(s, e_ - s, root)
            elif level == 2:
                # root, then the fifth on the next strong pulse
                alt = H.alternate_bass(ch, root, lo, max(hi, root.midi + 7))
                pts = [p - mp for p in sorted(strong) if s <= p - mp < e_]
                if not pts or pts[0] != s:
                    pts.insert(0, s)
                for k, p in enumerate(pts):
                    nxt = pts[k + 1] if k + 1 < len(pts) else e_
                    line.add(p, nxt - p, root if k % 2 == 0 else alt)
            else:
                # broken root-fifth-octave figure in pulses
                fifth = ch.fifth.at_or_above(root.midi + 1)
                if fifth.midi > hi + 5:
                    fifth = root
                octave = root.octave_shift(1)
                if octave.midi > hi + 4:
                    octave = fifth
                cyc = [root, fifth, octave] if m.compound or m.num == 3 else [root, fifth, octave, fifth]
                t = s
                k = 0
                while t < e_:
                    line.add(t, min(self.pulse, e_ - t), cyc[k % len(cyc)])
                    k += 1
                    t += self.pulse
        return line.events()

    # -- Primo accompanying from above -----------------------------------------
    def primo_accompaniment(self, i: int, floor: int, st: dict):
        b = self.bars[i]
        level = self.opts.primo
        m = self._meters[i]
        mp = self._mpos[i]
        rh, lh = Line(b.length), Line(b.length)
        if b.pickup and b.length <= m.bar_len / 2:
            return rh.events(), lh.events()
        lo_l, hi_l = floor, floor + 9
        lo_r, hi_r = floor + 8, floor + 22
        last = self.is_last(i) and self.opts.ending
        strong = strong_pulses(m, self.pulse)
        for (s, e_, ch) in H.spans(b):
            v = H.voice_chord(ch, 3 if level >= 2 else 2, lo_r, hi_r, st["prev_up"], target=lo_r + 6)
            st["prev_up"] = v
            third = ch.third.nearest_to((lo_l + hi_l) / 2)
            if third.midi < lo_l:
                third = third.octave_shift(1)
            root = ch.root.nearest_to(third.midi - 4)
            if root.midi < lo_l - 2:
                root = root.octave_shift(1)
            low_note = third if third.midi < v[0].midi - 1 else ch.root.at_or_below(v[0].midi - 3)
            if last:
                span_len = (_final_len(b, self.bars[i].melody) - s) if s == 0 else (e_ - s)
                marks = ("ferm",) if not b.end_repeat and s == H.spans(b)[-1][0] else ()
                rh.add(s, span_len, v, marks=marks)
                lh.add(s, span_len, low_note, marks=marks)
                continue
            if level <= 1:
                rh.add(s, e_ - s, v)
                lh.add(s, e_ - s, low_note)
            elif level == 2:
                # left hand on the strong pulses, right-hand chords after the beat
                t = s
                while t < e_:
                    pos = mp + t
                    if pos in strong:
                        nxt = t + self.pulse
                        while nxt < e_ and (mp + nxt) not in strong:
                            nxt += self.pulse
                        lh.add(t, min(nxt, e_) - t, low_note)
                    else:
                        rh.add(t, min(self.pulse, e_ - t), v)
                    t += self.pulse
            else:
                # flowing broken chords in the right hand, held notes below
                sub = self.pulse / 2 if not m.compound else self.pulse
                low, mid, high = v[0], v[len(v) // 2], v[-1]
                if m.compound:
                    cyc = [low, mid, high]
                elif m.num == 3:
                    cyc = [low, mid, high, mid, high, mid]
                else:
                    cyc = [low, high, mid, high]
                t = s
                k = int((mp + s) / sub) % len(cyc)
                while t < e_:
                    rh.add(t, min(sub, e_ - t), cyc[k % len(cyc)])
                    k += 1
                    t += sub
                lh.add(s, e_ - s, low_note)
        return rh.events(), lh.events()

    # -- Secondo accompanying from below ------------------------------------------
    def secondo_accompaniment(self, i: int, ceil: int, st: dict):
        b = self.bars[i]
        level = self.opts.secondo
        style = self.style
        m = self._meters[i]
        mp = self._mpos[i]
        rh, lh = Line(b.length), Line(b.length)
        if b.pickup and b.length <= m.bar_len / 2:
            return rh.events(), lh.events()
        hi = ceil
        lo = hi - 13
        blo, bhi = 40, min(52, lo + 2)
        last = self.is_last(i) and self.opts.ending
        n_notes = 2 if (level <= 2 or hi <= 58) else 3
        aim = hi - 4.5
        strong = strong_pulses(m, self.pulse)
        sp = H.spans(b)
        pulse = self.pulse

        if last:
            ch = sp[-1][2]
            s0 = sp[-1][0]
            for (s, e_, c) in sp[:-1]:
                root = H.bass_note(c, blo, bhi, st["prev_bass"], centre=45)
                v = H.voice_chord(c, n_notes, max(lo, root.midi + 3), hi, st["prev_rh"], target=aim)
                st["prev_rh"] = v
                st["prev_bass"] = root.midi
                rh.add(s, e_ - s, v)
                lh.add(s, e_ - s, root)
            root = H.bass_note(ch, blo, bhi, st["prev_bass"], centre=43)
            v = H.voice_chord(ch, n_notes, max(lo, root.midi + 3), hi, st["prev_rh"], target=aim)
            fl = _final_len(b, self.melody_bar(i))
            marks = ("ferm",) if not b.end_repeat else ()
            bass = (root,)
            if level >= 3 and root.midi - 12 >= 36:
                bass = (root.octave_shift(-1), root)
            elif level >= 3 and root.midi + 12 <= v[0].midi - 2:
                bass = (root, root.octave_shift(1))
            rh.add(s0, max(fl - s0, pulse), v, marks=marks)
            lh.add(s0, max(fl - s0, pulse), bass, marks=marks)
            return rh.events(), lh.events()

        for si, (s, e_, ch) in enumerate(sp):
            root = H.bass_note(ch, blo, bhi, st["prev_bass"], centre=45)
            v = H.voice_chord(ch, n_notes, max(lo, root.midi + 3), hi, st["prev_rh"], target=aim)
            st["prev_rh"] = v
            alt = H.alternate_bass(ch, root, blo - 1, bhi + 2)
            if alt.midi >= v[0].midi:
                alt = alt.octave_shift(-1)
            st["prev_bass"] = root.midi
            span = e_ - s
            nxt_ch = sp[si + 1][2] if si + 1 < len(sp) else self.next_chord(i)

            if style in ("pad", "drone") or level <= 1:
                rh.add(s, span, v)
                lh.add(s, span, root)
                continue

            if style in ("chorale", "ballad", "lullaby") and level <= 2:
                # bass and chord together, re-struck on each strong pulse
                pts = [p - mp for p in sorted(strong) if s <= p - mp < e_]
                if not pts or pts[0] != s:
                    pts.insert(0, s)
                for k, p in enumerate(pts):
                    nx = pts[k + 1] if k + 1 < len(pts) else e_
                    lh.add(p, nx - p, root if k % 2 == 0 else alt)
                    rh.add(p, nx - p, v)
                continue

            if style == "chorale":
                # level 3+: moving bass in pulses under held chords
                pts = [p - mp for p in sorted(strong) if s <= p - mp < e_]
                if not pts or pts[0] != s:
                    pts.insert(0, s)
                for k, p in enumerate(pts):
                    nx = pts[k + 1] if k + 1 < len(pts) else e_
                    rh.add(p, nx - p, v)
                self._walk(lh, s, e_, ch, nxt_ch, root, blo, bhi, st, simple=True, top=v[0].midi - 2)
                continue

            if style in ("ballad", "lullaby", "flowing") or (style == "alberti" and level == 2):
                self._broken(rh, lh, s, e_, mp, m, v, root, alt, level, style)
                continue

            if style == "alberti":
                self._alberti(rh, lh, s, e_, mp, m, v, root, alt, level)
                continue

            if style == "walking":
                self._walk(lh, s, e_, ch, nxt_ch, root, blo, bhi, st, simple=False, top=v[0].midi - 2)
                t = s
                while t < e_:
                    pos = mp + t
                    if pos not in strong:
                        rh.add(t, min(pulse, e_ - t), v, marks=("stacc",) if level >= 4 else ())
                    t += pulse
                continue

            # oom-pah family: oompah, waltz, march, jig, stride
            short_bass = style in ("march", "stride", "jig") and level >= 3
            octave_bass = style == "stride" and level >= 4
            t = s
            bass_count = 0
            while t < e_:
                pos = mp + t
                if pos in strong:
                    note = root if (bass_count % 2 == 0 or level <= 2) else alt
                    bass_count += 1
                    nx = t + pulse
                    while nx < e_ and (mp + nx) not in strong:
                        nx += pulse
                    nx = min(nx, e_)
                    # approach tone on the last pulse before a change of harmony
                    dur = pulse if short_bass else nx - t
                    if (level >= 3 and nx == e_ and nxt_ch is not None and nx - t >= 2 * pulse
                            and nxt_ch.bass_pitch.pc != note.pc and self.rng.random() < 0.3
                            and not m.compound):
                        target = H.bass_note(nxt_ch, blo, bhi, note.midi, centre=45)
                        app = H.approach_tone(self.key, note, target, ch)
                        if (blo - 2 <= app.midi <= bhi + 2 and abs(app.midi - target.midi) <= 2
                                and app.pc != note.pc and app.pc != target.pc):
                            lh.add(nx - pulse, pulse, app)
                            dur = min(dur, nx - pulse - t)
                    ps = (note,)
                    if octave_bass and note.midi - 12 >= 31:
                        ps = (note.octave_shift(-1), note)
                    lh.add(t, dur, ps)
                else:
                    # in compound time the chord normally falls only on the last
                    # third of the beat (oom - pah); fuller at higher levels
                    if m.compound and level <= 3 and (pos + pulse) not in strong and (pos + pulse) != m.bar_len:
                        t += pulse
                        continue
                    rh.add(t, min(pulse, e_ - t), v, marks=("stacc",) if (style == "stride" and level >= 4) else ())
                t += pulse
            if lh.empty and rh.empty is False and s == 0 and False:
                pass
        # a bar whose pattern produced no bass at all (chord change on weak pulses only)
        if lh.empty and not rh.empty:
            ch0 = sp[0][2]
            lh.add(0, min(pulse, b.length), H.bass_note(ch0, blo, bhi, st["prev_bass"], centre=43))
        return rh.events(), lh.events()

    # -- accompaniment figures ---------------------------------------------------
    def _broken(self, rh, lh, s, e_, mp, m, v, root, alt, level, style):
        """Held bass with a gently rocking right hand (level 2-3)."""
        pulse = self.pulse
        lh.add(s, e_ - s, root)
        low, mid, high = v[0], v[len(v) // 2], v[-1]
        if level <= 2:
            # the chord enters after the bass and is held
            t = s + pulse
            if t >= e_:
                rh.add(s, e_ - s, v)
                return
            if m.compound:
                rh.add(t, e_ - t, v)
            else:
                while t < e_:
                    rh.add(t, min(pulse, e_ - t), v)
                    t += pulse
            return
        sub = pulse / 2 if not m.compound else pulse
        cyc = [low, mid, high, mid]
        t = s + sub
        k = 0
        while t < e_:
            rh.add(t, min(sub, e_ - t), cyc[k % len(cyc)])
            k += 1
            t += sub

    def _alberti(self, rh, lh, s, e_, mp, m, v, root, alt, level):
        pulse = self.pulse
        sub = pulse / 2 if not m.compound else pulse
        low, mid, high = v[0], v[len(v) // 2], v[-1]
        if m.compound:
            cyc = [low, mid, high]
        elif m.num == 3:
            cyc = [low, high, mid, high, mid, high]
        else:
            cyc = [low, high, mid, high]
        t = s
        k = int((mp + s) / sub) % len(cyc)
        while t < e_:
            rh.add(t, min(sub, e_ - t), cyc[k % len(cyc)])
            k += 1
            t += sub
        strong = strong_pulses(m, pulse)
        pts = [p - mp for p in sorted(strong) if s <= p - mp < e_]
        if not pts or pts[0] != s:
            pts.insert(0, s)
        for k2, p in enumerate(pts):
            nx = pts[k2 + 1] if k2 + 1 < len(pts) else e_
            lh.add(p, nx - p, root if k2 % 2 == 0 else alt)

    def _walk(self, lh, s, e_, ch, nxt_ch, root, blo, bhi, st, simple, top=None):
        """Bass moving in pulses: root, chord tones, then a step into the next root."""
        pulse = self.pulse
        n = int((e_ - s) / pulse)
        if n <= 0:
            lh.add(s, e_ - s, root)
            return
        tones = [p for p in ch.tones()[:4]]
        target = H.bass_note(nxt_ch, blo, bhi, root.midi, centre=43) if nxt_ch is not None else root
        seq = [root]
        cur = root
        for k in range(1, n):
            if k == n - 1 and nxt_ch is not None and target.pc != cur.pc:
                app = H.approach_tone(self.key, cur, target, ch)
                if abs(app.midi - target.midi) <= 2 and blo - 3 <= app.midi <= bhi + 4:
                    seq.append(app)
                    cur = app
                    continue
            # nearest chord tone that is not the current note, moving towards the target
            direction = 1 if target.midi >= cur.midi else -1
            if simple and n <= 2:
                seq.append(cur)
                continue
            cands = []
            for tpc in tones:
                for q in (tpc.nearest_to(cur.midi + 3 * direction), tpc.nearest_to(cur.midi)):
                    if q.midi != cur.midi and blo - 3 <= q.midi <= bhi + 5:
                        cands.append(q)
            if not cands:
                seq.append(cur)
                continue
            nxt = min(cands, key=lambda q: (abs(q.midi - (cur.midi + 3 * direction)), abs(q.midi - cur.midi)))
            seq.append(nxt)
            cur = nxt
        if top is not None:
            # stay under the right hand
            seq = [q if q.midi <= top else q.octave_shift(-1) for q in seq]
        # merge repeated notes into longer ones
        t = s
        k = 0
        while k < len(seq):
            j = k
            while j + 1 < len(seq) and seq[j + 1].midi == seq[k].midi:
                j += 1
            dur = pulse * (j - k + 1)
            lh.add(t, dur, seq[k])
            t += dur
            k = j + 1
        if t < e_:
            lh.add(t, e_ - t, seq[-1])
        st["prev_bass"] = seq[-1].midi


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _dedupe(pts):
    out = []
    for off, c in pts:
        if out and out[-1][1] == c:
            continue
        out.append((off, c))
    return out


def _best_octave(tune: Tune, iv: Interval, lo: int, hi: int) -> Interval:
    notes = [p.midi for p in tune.melody_pitches()]
    if not notes:
        return iv
    best = iv
    best_cost = None
    for octs in (-1, 0, 1):
        c = Interval(iv.steps + 7 * octs, iv.semis + 12 * octs)
        cost = sum(max(0, lo - (m + c.semis)) + max(0, (m + c.semis) - hi) for m in notes)
        if best_cost is None or cost < best_cost:
            best, best_cost = c, cost
    return best


def _diatonic_below(key: Key, p: Pitch, steps: int) -> Pitch:
    """The scale note ``steps`` letter-steps below p (keeps p's own chromatic
    inflection out of it)."""
    d = p.d - steps
    sc = key.scale()
    for s in sc:
        if s.step == d % 7:
            return Pitch(d, s.alter)
    return Pitch(d, 0)


def _fermata_last(events: list) -> list:
    for k in range(len(events) - 1, -1, -1):
        if not events[k].is_rest:
            # walk back over a tied chain to its last link (which is k itself)
            events = list(events)
            events[k] = events[k].with_marks("ferm")
            return events
    return events


def _final_len(bar, melody) -> Fraction:
    """How long the accompaniment should hold in the final bar: to the end of
    the melody's last note."""
    t = F(0)
    end = F(0)
    for e in melody:
        t += e.dur
        if not e.is_rest:
            end = t
    return end if end > 0 else bar.length


def arrange(tune: Tune, opts: Optional[Options] = None) -> Piece:
    """Arrange a lead sheet for piano four hands."""
    return Arranger(tune, opts or Options()).run()


# ---------------------------------------------------------------------------
# hymns: arranging from an existing four-part setting
# ---------------------------------------------------------------------------
def plain_chord(c: Chord) -> Chord:
    """A chord symbol that can be taken in at a glance: no inversion, no
    added sixth (chords inferred from four-part writing are fussy otherwise)."""
    c = c.simplified(1)
    kind = {"6": "", "m6": "m", "sus4": "", "aug": "", "7sus4": "7"}.get(c.kind, c.kind)
    return Chord(c.root, kind, None)


def _same_rhythm(a: list, b: list) -> bool:
    if len(a) != len(b):
        return False
    return all(x.dur == y.dur and x.is_rest == y.is_rest and x.tie == y.tie for x, y in zip(a, b))


def combine_voices(upper: list, lower: list, max_span: int = 12) -> list:
    """Put two lines into one hand.  Returns a list of voices: a single voice
    of chords when the rhythms match, otherwise two voices."""
    if not lower or all(e.is_rest for e in lower):
        return [upper]
    if not upper or all(e.is_rest for e in upper):
        return [lower]
    if _same_rhythm(upper, lower):
        out = []
        for u, l in zip(upper, lower):
            if u.is_rest:
                out.append(u)
                continue
            ps = set(u.pitches)
            for p in l.pitches:
                if u.top.midi - p.midi <= max_span and p.midi <= u.top.midi:
                    ps.add(p)
            out.append(Ev(u.dur, tuple(sorted(ps, key=lambda p: (p.midi, p.d))), u.tie, u.marks))
        return [out]
    # different rhythms: drop lower notes that would need a stretch
    low2 = []
    tu = F(0)
    for e in lower:
        if e.pitches:
            top_here = _sounding_top(upper, tu)
            keep = tuple(p for p in e.pitches if top_here is None or 0 <= top_here - p.midi <= max_span)
            low2.append(Ev(e.dur, keep, e.tie if keep else False, e.marks if keep else ()))
        else:
            low2.append(e)
        tu += e.dur
    if all(e.is_rest for e in low2):
        return [upper]
    return [upper, merge_ties(low2)]


def _sounding_top(events: list, pos: Fraction):
    t = F(0)
    for e in events:
        if t <= pos < t + e.dur:
            return e.top.midi if e.pitches else None
        t += e.dur
    return None


def _shift(events: list, octaves: int) -> list:
    return [e.shifted(octaves) for e in events]


def _strip_marks(events: list, keep=("ferm",)) -> list:
    return [Ev(e.dur, e.pitches, e.tie, tuple(m for m in e.marks if m in keep)) for e in events]


def arrange_satb(tune: Tune, opts: Optional[Options] = None) -> Piece:
    """Four-hand setting of a hymn that keeps its real harmonisation.

    primo <= 2 : the Primo plays the tune in octaves; the Secondo has tenor and
                 bass (plus the alto at secondo >= 3).
    primo == 3 : soprano and alto for the Primo (one line per hand, an octave
                 up), tenor and bass for the Secondo.
    primo >= 4 : soprano+alto in the Primo right hand, the tune doubled below;
                 the Secondo bass moves in octaves at secondo >= 4.
    """
    o = opts or Options()
    t = copy.deepcopy(tune)
    if not t.has_chords:
        H.infer_chords(t)
    H.fill_chords(t)
    for b in t.bars:
        b.chords = _dedupe([(off, plain_chord(c)) for off, c in b.chords])
    if o.key == "original":
        iv = Interval(0, 0)
    elif o.key != "auto":
        iv = transposition_interval(t.key, Key(Key.parse(o.key).tonic, t.key.mode))
    else:
        iv = choose_transposition(t, 60, 77, o.max_accidentals, prefer_original=3.0, max_shift=3)
    t = transpose_tune(t, iv)
    bars = []
    n = len(t.bars)
    for i, b in enumerate(t.bars):
        S = _strip_marks(b.melody)
        A = _strip_marks(b.voices.get("A", [Ev(b.length)]), keep=())
        T = _strip_marks(b.voices.get("T", [Ev(b.length)]), keep=())
        B = _strip_marks(b.voices.get("B", [Ev(b.length)]), keep=())
        # copy the soprano's fermatas to the other parts
        if any("ferm" in e.marks for e in S):
            A, T, B = (_copy_fermatas(S, v) for v in (A, T, B))
        pb = PBar(length=b.length)
        pb.pickup = b.pickup
        pb.start_repeat, pb.end_repeat, pb.volta = b.start_repeat, b.end_repeat, b.volta
        pb.double_bar, pb.meter, pb.key = b.double_bar, b.meter, b.key
        pb.chords = list(b.chords)
        if o.primo <= 2:
            pb.hands["prh"] = [_shift(S, 1)]
            pb.hands["plh"] = [S] if o.primo == 2 else [_only_long(S, t.meter)]
            if o.secondo >= 3:
                floor = min((e.bottom.midi for e in S if e.pitches), default=72)
                A2 = [Ev(e.dur, tuple(p for p in e.pitches if p.midi < floor - 1), e.tie) for e in A]
                A2 = [e if e.pitches else Ev(e.dur) for e in A2]
                # alto above, tenor below, if one hand can hold both
                pb.hands["srh"] = combine_voices(merge_ties(A2), T) if not all(e.is_rest for e in A2) else [T]
                if len(pb.hands["srh"]) == 1 and all(e.is_rest for e in pb.hands["srh"][0]):
                    pb.hands["srh"] = [T]
            else:
                pb.hands["srh"] = [T if not all(e.is_rest for e in T) else A]
            pb.hands["slh"] = [B]
        elif o.primo == 3:
            pb.hands["prh"] = [_shift(S, 1)]
            pb.hands["plh"] = [_shift(A, 1)] if not all(e.is_rest for e in A) else [S]
            pb.hands["srh"] = [T]
            pb.hands["slh"] = [B]
        else:
            pb.hands["prh"] = combine_voices(_shift(S, 1), _shift(A, 1))
            pb.hands["plh"] = [S]
            pb.hands["srh"] = [T]
            pb.hands["slh"] = [B]
        for a, c in (("prh", "plh"), ("srh", "slh")):
            if len(pb.hands[a]) == 1 and len(pb.hands[c]) == 1:
                pb.hands[a][0], pb.hands[c][0] = _uncross(pb.hands[a][0], pb.hands[c][0])
        if o.secondo >= 4:
            pb.hands["slh"] = [[Ev(e.dur, tuple(sorted({e.bottom.octave_shift(-1), e.bottom}, key=lambda p: p.midi))
                                   if (e.pitches and e.bottom.midi - 12 >= 36) else e.pitches, e.tie, e.marks)
                                for e in B]]
        bars.append(pb)
    bars[0].dyn = {"p": "mf", "s": "mf"}
    bars[-1].final = True
    tempo = o.tempo or t.tempo or 88
    piece = Piece(title=t.title, key=t.key, meter=t.meter, bars=bars, tempo=tempo,
                  tempo_text=t.tempo_text or "", subtitle=t.subtitle, composer=t.composer,
                  credit=t.credit, category=t.category, tags=list(t.tags), slug=t.slug,
                  free_meter=t.free_meter)
    piece.flavor = {True: "four-part setting · tune in octaves",
                    False: "four-part setting"}[o.primo <= 2]
    return piece


def _uncross(upper: list, lower: list) -> tuple:
    """Where two single lines with the same rhythm cross (the 'lower' one goes
    above the 'upper'), swap the notes so each hand stays on its own side."""
    if not _same_rhythm(upper, lower):
        return upper, lower
    up, lo = [], []
    for u, l in zip(upper, lower):
        if u.pitches and l.pitches and len(u.pitches) == 1 and len(l.pitches) == 1 \
                and l.pitches[0].midi > u.pitches[0].midi and not (u.tie or l.tie):
            up.append(Ev(u.dur, l.pitches, u.tie, u.marks))
            lo.append(Ev(l.dur, u.pitches, l.tie, l.marks))
        else:
            up.append(u)
            lo.append(l)
    return up, lo


def _only_long(events: list, meter: Meter) -> list:
    pulse = meter.beat_len if not meter.compound else meter.beat_len / 3
    if all(e.dur >= pulse for e in events if e.pitches):
        return events
    return merge_ties([e if (e.is_rest or e.dur >= pulse) else Ev(e.dur) for e in events])


def _copy_fermatas(src: list, dst: list) -> list:
    """Give ``dst`` a fermata wherever ``src`` has one at the same moment."""
    marks_at = set()
    tt = F(0)
    for e in src:
        if "ferm" in e.marks:
            marks_at.add(tt)
        tt += e.dur
    out = []
    tt = F(0)
    for e in dst:
        if e.pitches and any(tt <= m < tt + e.dur for m in marks_at):
            out.append(e.with_marks("ferm"))
        else:
            out.append(e)
        tt += e.dur
    return out


# ---------------------------------------------------------------------------
# joining arrangements end to end (stanzas, variations)
# ---------------------------------------------------------------------------
def join_pieces(parts: list, labels: Optional[list] = None, title: Optional[str] = None) -> Piece:
    """Concatenate arrangements of the same tune into one piece.  Each part
    gets a rehearsal mark from ``labels``."""
    first = parts[0]
    bars = []
    key = first.key
    meter = first.meter
    tempo = first.tempo
    for k, pc in enumerate(parts):
        seg = copy.deepcopy(pc.bars)
        for b in seg:
            b.final = False
        # remove inner fermatas except at the very end
        if k < len(parts) - 1:
            for b in seg[-1:]:
                for h in list(b.hands):
                    b.hands[h] = [[Ev(e.dur, e.pitches, e.tie, tuple(m for m in e.marks if m != "ferm"))
                                   for e in v] for v in b.hands[h]]
            seg[-1].double_bar = True
        if labels and k < len(labels) and labels[k]:
            anchor = next((b for b in seg if not b.pickup), seg[0])
            anchor.mark = labels[k]
        if k > 0:
            head = seg[0]
            if pc.key != key:
                head.key = pc.key
                key = pc.key
            if pc.meter != meter:
                head.meter = pc.meter
                meter = pc.meter
            if pc.tempo != tempo or pc.tempo_text != parts[k - 1].tempo_text:
                head.tempo = (pc.tempo_text, pc.tempo)
                tempo = pc.tempo
            if not head.dyn and pc.bars[0].dyn:
                head.dyn = dict(pc.bars[0].dyn)
        bars.extend(seg)
    bars[-1].final = True
    out = copy.copy(first)
    out.bars = bars
    out.clefs, out.ottava, out.levels, out.stats = {}, {}, {}, {}
    if title:
        out.title = title
    return out


# ---------------------------------------------------------------------------
# "one hand each": a solo piano piece shared between two players
# ---------------------------------------------------------------------------
def _two_hands(voices: list, length: Fraction) -> Optional[tuple]:
    """If a part is too much for one hand in this bar (two voices, or chords
    wider than an octave) share it between two hands: returns (upper, lower)."""
    voices = [v for v in voices if any(e.pitches for e in v)]
    if len(voices) >= 2:
        hi, lo = sorted(voices[:2], key=_mean_pitch, reverse=True)
        return hi, lo
    if not voices:
        return None
    v = voices[0]
    if not any(e.pitches and e.top.midi - e.bottom.midi > 12 for e in v):
        return None
    up, down = [], []
    for e in v:
        if not e.pitches:
            up.append(e)
            down.append(e)
            continue
        hi = tuple(p for p in e.pitches if e.top.midi - p.midi <= 9)
        lo = tuple(p for p in e.pitches if p not in hi)
        if lo and lo[-1].midi - lo[0].midi > 12:
            lo = lo[-2:] if len(lo) > 1 and lo[-1].midi - lo[-2].midi <= 12 else lo[:1]
        up.append(Ev(e.dur, hi, e.tie, e.marks))
        down.append(Ev(e.dur, lo, e.tie, ()) if lo else Ev(e.dur))
    return up, _fix_ties(down)


def _fix_ties(events: list) -> list:
    out = []
    for k, e in enumerate(events):
        nxt = events[k + 1] if k + 1 < len(events) else None
        if e.tie and (nxt is None or nxt.pitches != e.pitches):
            e = Ev(e.dur, e.pitches, False, e.marks)
        out.append(e)
    return merge_ties(out)


def arrange_split(tune: Tune, opts: Optional[Options] = None) -> Piece:
    """Turn a two-hand piano piece into a duet without changing a note of it:
    the Primo plays the right-hand part (an octave up), the Secondo plays the
    left-hand part.  Where a part is a single line, the player's free hand
    doubles it at the octave (melody below for the Primo, bass below for the
    Secondo); where it has two voices or wide chords, the two hands share it.
    The tune must carry its left hand in the voice ``lh`` (and optionally
    ``rh2`` / ``lh2`` for second voices)."""
    o = opts or Options()
    t = copy.deepcopy(tune)
    if not t.has_chords:
        H.infer_chords(t, min_unit=t.meter.beat_len)
    H.fill_chords(t)
    highs = [p.midi for b in t.bars for e in b.melody for p in e.pitches]
    up = 1 if (not highs or max(highs) + 12 <= 98) else 0
    pulse = t.meter.beat_len / 3 if t.meter.compound else t.meter.beat_len
    bars = []
    for i, b in enumerate(t.bars):
        pb = PBar(length=b.length)
        pb.pickup = b.pickup
        pb.start_repeat, pb.end_repeat, pb.volta = b.start_repeat, b.end_repeat, b.volta
        pb.double_bar, pb.meter, pb.key = b.double_bar, b.meter, b.key
        pb.mark = b.label
        pb.chords = _dedupe([(off, plain_chord(c)) for off, c in b.chords if c is not None])
        rh = [b.melody] + ([b.voices["rh2"]] if "rh2" in b.voices else [])
        rh = [v for v in rh if any(e.pitches for e in v)] or [[Ev(b.length)]]
        lh = [b.voices.get("lh", [Ev(b.length)])] + ([b.voices["lh2"]] if "lh2" in b.voices else [])
        lh = [v for v in lh if any(e.pitches for e in v)] or [[Ev(b.length)]]
        # ---- Secondo: the left-hand part ----
        shared = _two_hands(lh, b.length)
        if shared is not None:
            pb.hands["srh"], pb.hands["slh"] = [shared[0]], [shared[1]]
        else:
            pb.hands["srh"] = lh
            mp = (t.meter.bar_len - b.length) if (b.pickup and b.length < t.meter.bar_len) else F(0)
            line = []
            tt = F(0)
            for e in lh[0]:
                strong = (mp + tt) % pulse == 0
                if e.pitches and (strong or e.dur >= pulse) and e.bottom.midi - 12 >= 36 and o.secondo >= 2 \
                        and e.dur >= pulse / 2:
                    line.append(Ev(e.dur, (e.bottom.octave_shift(-1),), e.tie, ()))
                else:
                    line.append(Ev(e.dur))
                tt += e.dur
            pb.hands["slh"] = [_fix_ties(line)]
        sec_top = max((e.top.midi for v in pb.hands["srh"] for e in v if e.pitches), default=0)
        # ---- Primo: the right-hand part, an octave up ----
        shared = _two_hands(rh, b.length)
        if shared is not None:
            hi, lo = _shift(shared[0], up), _shift(shared[1], up)
            if min((e.bottom.midi for e in lo if e.pitches), default=127) <= sec_top + 1:
                lo = [Ev(b.length)]
                hi_all = [_shift(v, up) for v in rh]
                pb.hands["prh"] = hi_all
            else:
                pb.hands["prh"] = [hi]
            pb.hands["plh"] = [lo]
        else:
            pb.hands["prh"] = [_shift(v, up) for v in rh]
            top = [Ev(e.dur, (e.top,), e.tie, ()) if e.pitches else Ev(e.dur) for e in rh[0]]
            dbl = _shift(top, up - 1)
            low = min((e.bottom.midi for e in dbl if e.pitches), default=127)
            if o.primo <= 1 or low <= sec_top + 1 or low < 55:
                dbl = [Ev(b.length)]
            pb.hands["plh"] = [dbl]
        bars.append(pb)
    bars[0].dyn = {"p": "mf", "s": "mp"}
    bars[-1].final = True
    piece = Piece(title=t.title, key=t.key, meter=t.meter, bars=bars, tempo=o.tempo or t.tempo or 100,
                  tempo_text=t.tempo_text, subtitle=t.subtitle, composer=t.composer, credit=t.credit,
                  category=t.category, tags=list(t.tags), slug=t.slug, free_meter=t.free_meter)
    piece.flavor = "one hand each: Primo plays the right-hand part, Secondo the left"
    return piece


def _mean_pitch(events: list) -> float:
    ms = [p.midi for e in events for p in e.pitches]
    return sum(ms) / len(ms) if ms else 999.0
