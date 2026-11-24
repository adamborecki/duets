"""Theme and variations, and rounds.

``variations(tune)`` strings together several arrangements of one tune:
the plain theme, then versions with a flowing accompaniment, the tune in the
bass, a turn to the minor, a jig, a decorated melody and a broad finale.
``round_piece(tune)`` sets a round as a true canon between the two players.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from fractions import Fraction
from typing import Optional

from . import harmony as H
from .arrange import Options, arrange, choose_transposition, join_pieces, transpose_tune
from .model import Ev, F, PBar, Piece, TBar, Tune, merge_ties, total
from .theory import Chord, Key, Meter, Pitch

# ---------------------------------------------------------------------------
# transformations of a lead sheet
# ---------------------------------------------------------------------------


def to_minor(tune: Tune) -> Tune:
    """The parallel minor: lower the third, sixth and seventh degrees (the
    seventh stays raised over dominant harmony)."""
    t = copy.deepcopy(tune)
    if t.key.is_minorish:
        return t
    major = t.key
    minor = Key(major.tonic, "minor")
    maj_sc, min_sc = major.scale(), minor.scale()
    tonic_pc = major.tonic.pc

    def conv_pitch(p: Pitch, dominant: bool) -> Pitch:
        deg = (p.step - major.tonic.step) % 7
        base = maj_sc[deg]
        if p.alter != base.alter:
            return p                     # chromatic note: leave alone
        if deg in (2, 5) or (deg == 6 and not dominant):
            return Pitch(p.d, min_sc[deg].alter)
        return p

    def conv_chord(c: Chord) -> Chord:
        rel = (c.root.pc - tonic_pc) % 12
        root = c.root
        kind = c.kind
        if rel == 0 and kind in ("", "6", "maj7"):
            kind = "m"
        elif rel == 5 and kind in ("", "6", "maj7"):
            kind = "m"
        elif rel == 7:
            kind = "7" if kind in ("", "7") else kind
        elif rel == 9 and kind in ("m", "m7"):          # vi -> bVI
            root, kind = min_sc[5].in_octave(4), ""
        elif rel == 4 and kind in ("m", "m7"):          # iii -> bIII
            root, kind = min_sc[2].in_octave(4), ""
        elif rel == 2 and kind in ("m", "m7"):          # ii -> iv
            root, kind = min_sc[3].in_octave(4), "m"
        bass = c.bass
        if bass is not None:
            bass = conv_pitch(bass.in_octave(4), rel == 7).in_octave(4)
        return Chord(root, kind, bass)

    for b in t.bars:
        b.chords = [(off, conv_chord(c)) for off, c in b.chords]
        out = []
        tt = F(0)
        for e in b.melody:
            ch = b.chord_at(tt)
            dom = ch is not None and (ch.root.pc - tonic_pc) % 12 == 7
            out.append(Ev(e.dur, tuple(conv_pitch(p, dom) for p in e.pitches), e.tie, e.marks))
            tt += e.dur
        b.melody = out
        b.voices = {}
    t.key = minor
    return t


def to_jig(tune: Tune) -> Optional[Tune]:
    """Re-cast a tune in 2/4 or 4/4 as a jig in 6/8: every beat becomes a
    dotted beat, even pairs turn long-short."""
    m = tune.meter
    if m.compound or m.num not in (2, 4) or m.den != 4:
        return None
    t = copy.deepcopy(tune)
    beat = F(1)
    new_bars = []
    for b in t.bars:
        # stretch by 3/2 with a lilt inside each beat
        evs = []
        tt = F(0)
        pos_map = {}
        for e in b.melody:
            start, end = tt, tt + e.dur
            def warp(x):
                whole = x // beat
                frac = x - whole * beat
                # 0 -> 0, 1/2 -> 2/3 of the dotted beat, others proportional
                if frac == 0:
                    f2 = F(0)
                elif frac <= F(1, 2):
                    f2 = frac * 2 * F(2, 3)
                else:
                    f2 = F(2, 3) + (frac - F(1, 2)) * 2 * F(1, 3)
                return whole * F(3, 2) + f2 * F(3, 2)
            evs.append(Ev(warp(end) - warp(start), e.pitches, e.tie, e.marks))
            tt = end
        chords = [(off * F(3, 2), c) for off, c in b.chords]
        length = b.length * F(3, 2)
        # cut the stretched bar into 6/8 bars (3 quarters each)
        if m.num == 4 and b.length == m.bar_len:
            halves = [(F(0), F(3)), (F(3), F(6))]
        else:
            halves = [(F(0), length)]
        for (s, e_) in halves:
            nb = TBar(length=e_ - s)
            nb.melody = _slice(evs, s, e_)
            nb.chords = [(off - s, c) for off, c in chords if s <= off < e_]
            new_bars.append(nb)
        first = new_bars[-len(halves)]
        last = new_bars[-1]
        first.pickup = b.pickup
        first.start_repeat, first.label = b.start_repeat, b.label
        first.volta = last.volta = b.volta
        last.end_repeat, last.double_bar = b.end_repeat, b.double_bar
    t.bars = new_bars
    t.meter = Meter(6, 8)
    t.tempo = 0
    t.style = "jig"
    # reject results with awkward rhythms (sixteenth-note groups do not survive the lilt)
    from .notate import representable, split_note
    for b in t.bars:
        tt = F(0)
        for e in b.melody:
            if e.dur.denominator not in (1, 2, 4):
                return None
            tt += e.dur
    return t


def _slice(events: list, start: Fraction, end: Fraction) -> list:
    out = []
    t = F(0)
    for e in events:
        a, b = max(t, start), min(t + e.dur, end)
        if b > a:
            cut_after = t + e.dur > end
            out.append(Ev(b - a, e.pitches, (e.tie or cut_after) if e.pitches else False, e.marks if a == t else ()))
        t += e.dur
    if total(out) < end - start:
        out.append(Ev(end - start - total(out)))
    return merge_ties(out) if False else out


def decorate(tune: Tune) -> Tune:
    """Melodic diminution: quarter notes are broken into pairs of eighths with
    passing and neighbour notes, in the manner of a classical first variation."""
    t = copy.deepcopy(tune)
    key = t.key
    m = t.meter
    unit = m.beat_len if not m.compound else None
    if unit is None:
        return t
    sc = key.scale()

    def diatonic(p: Pitch, steps: int) -> Pitch:
        d = p.d + steps
        for s in sc:
            if s.step == d % 7:
                return Pitch(d, s.alter)
        return Pitch(d, 0)

    flat = []
    for bi, b in enumerate(t.bars):
        for k, e in enumerate(b.melody):
            flat.append((bi, k, e))
    for idx, (bi, k, e) in enumerate(flat):
        if e.is_rest or e.tie or len(e.pitches) != 1 or e.dur not in (unit, 2 * unit):
            continue
        p = e.pitches[0]
        if not key.contains(p):
            continue
        nxt = None
        for (bj, kj, e2) in flat[idx + 1: idx + 3]:
            if e2.pitches:
                nxt = e2.pitches[0]
                break
        if nxt is None:
            continue
        if idx > 0 and flat[idx - 1][2].tie:
            continue
        step = nxt.d - p.d
        if step == 0:
            mid = diatonic(p, 1)
        elif abs(step) == 2:
            mid = diatonic(p, 1 if step > 0 else -1)
        elif abs(step) == 1:
            mid = diatonic(p, 2 if step > 0 else -2)
        else:
            mid = diatonic(p, 2 if step > 0 else -2)
        half = unit / 2
        if e.dur == unit:
            new = [Ev(half, (p,)), Ev(half, (mid,))]
        else:
            new = [Ev(unit, (p,)), Ev(half, (p,)), Ev(half, (mid,))]
        t.bars[bi].melody[k] = new
    for b in t.bars:
        out = []
        for e in b.melody:
            if isinstance(e, list):
                out.extend(e)
            else:
                out.append(e)
        b.melody = out
        b.voices = {}
    return t


# ---------------------------------------------------------------------------
# theme and variations
# ---------------------------------------------------------------------------
def variations(tune: Tune, count: int = 5, seed: int = 0, primo: int = 2, secondo: int = 3) -> Piece:
    """A theme-and-variations set on a lead-sheet tune."""
    base = copy.deepcopy(tune)
    for b in base.bars:
        b.voices = {}
    if not base.has_chords:
        from .autoharm import harmonize
        harmonize(base)
    theme = arrange(base, Options(primo=min(primo, 2), secondo=min(secondo, 2), melody="p", seed=seed))
    key = theme.key.short if theme.key.mode in ("major", "minor") else "original"
    fixed = dict(key=theme.key.tonic.class_name, seed=seed)
    tempo = theme.tempo
    parts = [theme]
    labels = ["Theme"]

    def add(label, piece, text=None, bpm=None):
        if text is not None:
            piece.tempo_text = text
        if bpm is not None:
            piece.tempo = bpm
        parts.append(piece)
        labels.append(label)

    menu = []
    menu.append(lambda: add("Var. %d", arrange(base, Options(primo=min(primo, 2), secondo=3, melody="p",
                                                             style="flowing", **fixed)), "Flowing", tempo))
    menu.append(lambda: add("Var. %d", arrange(base, Options(primo=3, secondo=max(2, min(secondo, 3)), melody="s",
                                                             **fixed)), "The tune in the Secondo", tempo))
    def minore():
        mt = to_minor(base)
        o = Options(primo=2, secondo=2, melody="p", style="ballad", key=theme.key.tonic.class_name, seed=seed)
        add("Var. %d", arrange(mt, o), "Minore, a little slower", max(48, int(tempo * 0.8)))
    if not base.key.is_minorish:
        menu.append(minore)
    def jig():
        jt = to_jig(base)
        if jt is None:
            pc = arrange(base, Options(primo=min(primo, 2), secondo=3, melody="p", style="alberti", **fixed))
            add("Var. %d", pc, "Alberti bass", tempo)
            return
        pc = arrange(jt, Options(primo=2, secondo=3, melody="p", style="jig", **fixed))
        beat_ratio = float(base.meter.beat_len)       # one old beat -> one dotted beat
        add("Var. %d", pc, "Alla giga", max(60, min(104, int(tempo * (1.0 if base.meter.num == 2 else 1.0)))))
    menu.append(jig)
    def deco():
        dt = decorate(base)
        add("Var. %d", arrange(dt, Options(primo=2, secondo=3, melody="p", **fixed)), "Decorated", int(tempo * 0.92))
    if not base.meter.compound:
        menu.append(deco)
    for fn in menu[:max(0, count - 1)]:
        fn()
    finale = arrange(base, Options(primo=3, secondo=4, melody="p", **fixed))
    add("Finale", finale, "Broadly", int(tempo * 0.9))
    labels = [l % i if "%d" in l else l for i, l in enumerate(labels)]
    piece = join_pieces(parts, labels=labels, title=f"Variations on “{tune.title}”")
    for b in piece.bars:
        if b.mark and b.mark != "Theme" and b.tempo is None:
            pass
    piece.subtitle = "Theme and variations for piano four hands"
    piece.flavor = "Theme and variations"
    piece.arranger = ""
    return piece


# ---------------------------------------------------------------------------
# rounds
# ---------------------------------------------------------------------------
def round_piece(tune: Tune, delay_bars: int = 2, cycles: int = 2, opts: Optional[Options] = None) -> Piece:
    """A round as a duet: the Primo starts (the tune in octaves), the Secondo
    follows ``delay_bars`` later an octave lower over a tonic drone, and both
    go round ``cycles`` times before a final chord."""
    o = opts or Options()
    t = copy.deepcopy(tune)
    H.fill_chords(t)
    iv = choose_transposition(t, 62, 79, 2)
    t = transpose_tune(t, iv)
    bars = [b for b in t.bars]
    n = len(bars)
    L = bars[0].length
    tonic = t.key.tonic
    root = tonic.nearest_to(43)
    if root.midi < 40:
        root = root.octave_shift(1)
    fifth = (root + _P5())
    seq_p = list(range(n)) * cycles + list(range(delay_bars))
    seq_s = [None] * delay_bars + list(range(n)) * cycles
    total_bars = len(seq_p)
    out = []
    for k in range(total_bars):
        pb = PBar(length=L)
        ip, is_ = seq_p[k], seq_s[k]
        mel = [Ev(e.dur, (e.top,), e.tie) if e.pitches else Ev(e.dur) for e in bars[ip].melody]
        pb.hands["prh"] = [[e.shifted(1) for e in mel]]
        pb.hands["plh"] = [mel] if o.primo >= 2 else [[Ev(L)]]
        if is_ is None:
            pb.hands["srh"] = [[Ev(L)]]
        else:
            mel2 = [Ev(e.dur, (e.top,), e.tie) if e.pitches else Ev(e.dur) for e in bars[is_].melody]
            pb.hands["srh"] = [[e.shifted(-1) for e in mel2]]
        # drone: tonic and fifth, kept under the tune
        low = min((e.bottom.midi for e in pb.hands["srh"][0] if e.pitches), default=99)
        r = root if root.midi < low - 2 else root.octave_shift(-1)
        f5 = fifth if fifth.midi < low - 2 else None
        if o.secondo >= 2 and f5 is not None and L % 2 == 0:
            pb.hands["slh"] = [[Ev(L / 2, (r,)), Ev(L / 2, (f5,))]]
        else:
            pb.hands["slh"] = [[Ev(L, (r,))]]
        pb.chords = [(F(0), H.tonic_chord(t.key))] if k == 0 else []
        if k == 0:
            pb.mark = "1"
        if is_ == 0 and k == delay_bars:
            pb.mark = "2"
        out.append(pb)
    # final chord
    fin = PBar(length=L)
    tri = H.tonic_chord(t.key)
    top = tonic.nearest_to(74)
    fin.hands["prh"] = [[Ev(L, (top.octave_shift(1),), marks=("ferm",))]]
    fin.hands["plh"] = [[Ev(L, (top,), marks=("ferm",))]]
    v = H.voice_chord(tri, 3, 50, 62)
    fin.hands["srh"] = [[Ev(L, tuple(v), marks=("ferm",))]]
    fin.hands["slh"] = [[Ev(L, (root.octave_shift(-1) if root.midi - 12 >= 36 else root, root), marks=("ferm",))]]
    fin.chords = [(F(0), tri)]
    fin.final = True
    out.append(fin)
    out[0].dyn = {"p": "mf", "s": "mf"}
    piece = Piece(title=t.title, key=t.key, meter=t.meter, bars=out, tempo=t.tempo or 100,
                  tempo_text=t.tempo_text or "", subtitle="A round for four hands", composer=t.composer,
                  credit=t.credit, category=t.category, tags=list(t.tags), slug=t.slug)
    piece.flavor = "Round: the Secondo follows the Primo %d bars later" % delay_bars
    piece.arranger = piece.flavor
    return piece


def _P5():
    from .theory import IV
    return IV["P5"]


def round_delay(tune: Tune) -> int:
    import re
    m = re.search(r"round\s*(\d+)", tune.notes or "")
    return int(m.group(1)) if m else 2


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------
def cmd_variations(args):
    from pathlib import Path
    from .catalog import finish
    from .cli import _find, _layouts
    from .engrave import build_piece
    from .library import load_library
    from .lily import dots
    tune, _ = _find(load_library(), args.tune)
    if tune is None:
        raise SystemExit(f"no tune matches {args.tune!r}")
    piece = finish(variations(tune, count=args.count, seed=args.seed))
    res = build_piece(piece, Path(args.output), tune.slug + "--variations", layouts=_layouts(args.layout),
                      paper=args.paper)
    print(f"{piece.title}: {len(piece.bars)} bars, Primo {dots(piece.levels['p'])}, Secondo {dots(piece.levels['s'])}")
    for k, v in res.items():
        if k != "info":
            print(f"  {k:13} {v}")
