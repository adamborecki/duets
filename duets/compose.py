"""Brand-new tunes, composed by rule.

``compose(style, seed)`` writes a 20-bar piece in rounded binary form
(A - B - A') over a stock harmonic plan, with a melody built from two short
rhythmic cells so that it hangs together, cadences in the right places and
stays easy to play.  The result is an ordinary lead sheet, so every
arrangement recipe works on it.
"""
from __future__ import annotations

import random
from fractions import Fraction
from typing import Optional

from .model import Ev, F, TBar, Tune, total
from .theory import Chord, Key, Meter, Pitch

STYLES = {
    "waltz": dict(meter=(3, 4), tempo=132, text="Tempo di valse", acc="waltz", keys=["C", "G", "F", "D", "Bb"]),
    "minuet": dict(meter=(3, 4), tempo=108, text="Tempo di menuetto", acc="alberti", keys=["G", "C", "F", "D"]),
    "march": dict(meter=(4, 4), tempo=112, text="Tempo di marcia", acc="march", keys=["C", "G", "D", "F", "Bb"]),
    "polka": dict(meter=(2, 4), tempo=104, text="Polka", acc="march", keys=["G", "C", "F", "D"]),
    "song": dict(meter=(4, 4), tempo=84, text="Singing", acc="flowing", keys=["C", "F", "G", "D", "Am", "Dm", "Em"]),
    "sonatina": dict(meter=(4, 4), tempo=116, text="Allegro", acc="alberti", keys=["C", "G", "F", "D"]),
    "lullaby": dict(meter=(6, 8), tempo=56, text="Gently rocking", acc="lullaby", keys=["F", "C", "G", "D", "Bb"]),
    "jig": dict(meter=(6, 8), tempo=104, text="Lively", acc="jig", keys=["G", "D", "C", "Am", "Em"]),
    "elegy": dict(meter=(4, 4), tempo=66, text="Slowly", acc="ballad", keys=["Am", "Dm", "Em", "Gm"]),
}

CELLS = {
    (3, 4): [[1, 1, 1], [2, 1], [F(3, 2), F(1, 2), 1], [1, F(1, 2), F(1, 2), 1], [F(1, 2), F(1, 2), 1, 1],
             [1, 1, F(1, 2), F(1, 2)], [F(1, 2), F(1, 2), F(1, 2), F(1, 2), 1]],
    (4, 4): [[1, 1, 1, 1], [2, 1, 1], [1, 1, 2], [F(3, 2), F(1, 2), 1, 1], [1, F(1, 2), F(1, 2), 1, 1],
             [F(1, 2), F(1, 2), 1, 2], [1, 1, F(1, 2), F(1, 2), 1], [F(3, 2), F(1, 2), 2]],
    (2, 4): [[1, 1], [F(1, 2), F(1, 2), 1], [1, F(1, 2), F(1, 2)], [F(1, 2), F(1, 2), F(1, 2), F(1, 2)],
             [F(3, 2), F(1, 2)]],
    (6, 8): [[1, F(1, 2), 1, F(1, 2)], [F(3, 2), 1, F(1, 2)], [1, F(1, 2), F(3, 2)],
             [F(1, 2), F(1, 2), F(1, 2), 1, F(1, 2)], [F(1, 2), F(1, 2), F(1, 2), F(3, 2)],
             [1, F(1, 2), F(1, 2), F(1, 2), F(1, 2)]],
}
CADENCE = {(3, 4): [[2, 1], [3]], (4, 4): [[2, 2], [3, 1], [4]], (2, 4): [[1, 1], [2]], (6, 8): [[F(3, 2), F(3, 2)], [3]]}

# harmonic plans, as scale degrees (0 = tonic); "7" marks a dominant seventh
MAJOR_A1 = [["I", "IV", "I", "V"], ["I", "vi", "ii", "V7"], ["I", "V7", "I", "V"], ["I", "I", "IV", "V"]]
MAJOR_A2 = [["I", "IV", "V7", "I"], ["I", "ii", "V7", "I"], ["vi", "ii", "V7", "I"], ["I", "IV", "V7", "I"]]
MAJOR_B = [["V", "I", "V", "I", "IV", "I", "ii", "V7"], ["IV", "I", "IV", "I", "ii", "vi", "V", "V7"],
           ["vi", "ii", "V", "I", "vi", "ii", "V", "V7"]]
MINOR_A1 = [["i", "iv", "i", "V"], ["i", "VI", "iv", "V7"], ["i", "V7", "i", "V"]]
MINOR_A2 = [["i", "iv", "V7", "i"], ["VI", "iv", "V7", "i"], ["i", "iv", "V7", "i"]]
MINOR_B = [["III", "VII", "III", "VI", "iv", "i", "iv", "V7"], ["iv", "i", "iv", "i", "VI", "III", "V", "V7"]]
ROMAN = {"I": (0, ""), "ii": (1, "m"), "iii": (2, "m"), "IV": (3, ""), "V": (4, ""), "V7": (4, "7"), "vi": (5, "m"),
         "i": (0, "m"), "iv": (3, "m"), "III": (2, ""), "VI": (5, ""), "VII": (6, "")}

ADJ = ["Little", "Morning", "Evening", "Rainy-Day", "Sunday", "Garden", "Winter", "Summer", "Autumn", "Spring",
       "Kitchen", "Porch-Swing", "Candlelight", "Riverside", "Hilltop", "Lakeside", "Snowy", "Harvest", "Meadow",
       "Starlight", "Fireside", "Orchard", "Maple", "Willow", "Lantern", "Clockwork", "Paper-Boat", "Teacup",
       "Bluebird", "Barefoot"]
NOUN = {"waltz": "Waltz", "minuet": "Minuet", "march": "March", "polka": "Polka", "song": "Song",
        "sonatina": "Sonatina", "lullaby": "Lullaby", "jig": "Jig", "elegy": "Elegy"}


def _chord(key: Key, roman: str) -> Chord:
    deg, kind = ROMAN[roman]
    root = key.scale()[deg].in_octave(4)
    return Chord(root, kind)


class _Melody:
    """Walks through the bars choosing pitches as diatonic steps from the tonic."""

    def __init__(self, key: Key, meter: Meter, rng: random.Random):
        self.key, self.meter, self.rng = key, meter, rng
        tonic = key.tonic.in_octave(4)
        if tonic.midi < 62:
            tonic = tonic.octave_shift(1)
        if tonic.midi > 67:
            tonic = tonic.octave_shift(-1)
        self.base = tonic                 # degree 0
        self.lo, self.hi = -3, 9          # allowed range in scale steps
        self.cur = rng.choice([2, 4, 0])  # start on the third, fifth or tonic

    def pitch(self, idx: int) -> Pitch:
        sc = self.key.scale()
        t = sc[0]
        p = sc[idx % 7].octave_shift(idx // 7)
        shift = self.base.octave - t.in_octave(4).octave
        p = p.octave_shift(shift)
        return p

    def chord_steps(self, chord: Chord) -> list:
        out = []
        for idx in range(self.lo, self.hi + 1):
            if chord.has_pc(self.pitch(idx).pc):
                out.append(idx)
        return out

    def bar(self, cell: list, chord: Chord, direction: int, target: Optional[int] = None,
            final_pcs: Optional[set] = None) -> list:
        rng = self.rng
        tones = self.chord_steps(chord)
        notes = []
        t = F(0)
        n = len(cell)
        for k, d in enumerate(cell):
            strong = (k == 0) or (self.meter.strength(t) <= 1) or d >= self.meter.beat_len * 2
            last = k == n - 1
            if last and target is not None:
                idx = target
            elif strong:
                want = self.cur + (direction if k else 0)
                cands = sorted(tones, key=lambda x: (abs(x - want), rng.random()))
                idx = cands[0] if cands else self.cur
                if k == 0 and idx == self.cur and len(cands) > 1 and rng.random() < 0.35:
                    idx = cands[1]
            else:
                idx = self.cur + direction
                if rng.random() < 0.18:
                    idx = self.cur - direction
            idx = max(self.lo, min(self.hi, idx))
            if idx in (self.lo, self.hi):
                direction = -direction
            # the note must be diatonic; over a dominant in minor raise the seventh
            notes.append((d, idx))
            self.cur = idx
            t += d
        return notes


def compose(style: str = "waltz", seed: int = 1, key: Optional[str] = None) -> Tune:
    rng = random.Random(f"{style}|{seed}")
    if style not in STYLES:
        style = rng.choice(sorted(STYLES))
    st = STYLES[style]
    meter = Meter(*st["meter"])
    k = Key.parse(key or rng.choice(st["keys"]))
    minor = k.is_minorish
    a1 = rng.choice(MINOR_A1 if minor else MAJOR_A1)
    a2 = rng.choice(MINOR_A2 if minor else MAJOR_A2)
    bplan = rng.choice(MINOR_B if minor else MAJOR_B)
    cells = CELLS[st["meter"]]
    c1, c2, c3 = rng.sample(cells, 3)
    cad_half = CADENCE[st["meter"]][0]
    cad_full = CADENCE[st["meter"]][-1]
    mel = _Melody(k, meter, rng)

    def chord_of(r):
        return _chord(k, r)

    def degree_targets(chord, prefer):
        steps = mel.chord_steps(chord)
        steps = [s for s in steps if s % 7 in prefer] or steps
        return min(steps, key=lambda s: abs(s - mel.cur))

    bars_spec = []          # (cell, roman, direction, cadence kind)
    # A: antecedent + consequent
    start_cur = mel.cur
    ant = []
    ant.append(mel.bar(c1, chord_of(a1[0]), +1))
    ant.append(mel.bar(c2, chord_of(a1[1]), +1))
    ant.append(mel.bar(c1 if rng.random() < 0.5 else c3, chord_of(a1[2]), -1))
    ch = chord_of(a1[3])
    ant.append(mel.bar(cad_half, ch, -1, target=degree_targets(ch, {1, 4, 6})))
    cons = [list(ant[0]), list(ant[1])]
    mel.cur = ant[1][-1][1]
    cons.append(mel.bar(c3, chord_of(a2[2]), -1))
    chf = chord_of(a2[3])
    cons.append(mel.bar(cad_full, chf, -1, target=degree_targets(chf, {0})))
    # B: a new idea, sequenced, then a climb to the dominant
    mel.cur = min(mel.hi - 1, mel.cur + 4)
    bsec = []
    bsec.append(mel.bar(c2, chord_of(bplan[0]), -1))
    bsec.append(mel.bar(c1, chord_of(bplan[1]), -1))
    bsec.append(mel.bar(c2, chord_of(bplan[2]), +1))
    bsec.append(mel.bar(c1, chord_of(bplan[3]), -1))
    bsec.append(mel.bar(c3, chord_of(bplan[4]), +1))
    bsec.append(mel.bar(c3, chord_of(bplan[5]), +1))
    bsec.append(mel.bar(c2, chord_of(bplan[6]), -1))
    chv = chord_of(bplan[7])
    bsec.append(mel.bar(cad_half, chv, +1, target=degree_targets(chv, {4, 1})))
    # A': the opening again, closing on the tonic
    mel.cur = ant[1][-1][1]
    ret = [list(ant[0]), list(ant[1])]
    ret.append(mel.bar(c3, chord_of(a2[2]), +1))
    ret.append(mel.bar(cad_full, chf, -1, target=degree_targets(chf, {0})))
    romans = a1 + a2[:2] + [a2[2], a2[3]] + bplan + a1[:2] + [a2[2], a2[3]]
    romans[4], romans[5] = a1[0], a1[1]
    all_bars = ant + cons + bsec + ret
    tune = Tune(title="", key=k, meter=meter)
    lead = k.scale()[6]
    for i, (notes, r) in enumerate(zip(all_bars, romans)):
        ch = chord_of(r)
        tb = TBar(length=meter.bar_len)
        evs = []
        for d, idx in notes:
            p = mel.pitch(idx)
            if minor and r in ("V", "V7") and p.step == lead.step:
                p = Pitch(p.d, p.alter + 1)          # leading tone
            evs.append(Ev(F(d), (p,)))
        tb.melody = evs
        tb.chords = [(F(0), ch)]
        if i in (8, 16):
            tb.label = "B" if i == 8 else "A"
        tune.bars.append(tb)
    tune.bars[7].double_bar = True
    tune.bars[15].double_bar = True
    tune.bars[0].start_repeat = True
    tune.bars[7].end_repeat = True
    adj = rng.choice(ADJ)
    tune.title = f"{adj} {NOUN[style]}"
    tune.subtitle = f"No. {seed}"
    tune.composer = "composed by the duets generator"
    tune.category = "original"
    tune.tags = ["original", style]
    tune.style = st["acc"]
    tune.tempo = st["tempo"]
    tune.tempo_text = st["text"]
    tune.credit = f"An original piece generated by duets (style: {style}, seed {seed}). Public domain (CC0)."
    tune.source = "duets generator"
    from .library import slugify
    tune.slug = slugify(f"{tune.title}-no-{seed}")
    return tune


def cmd_new(args):
    from pathlib import Path
    from .catalog import make_piece
    from .cli import _layouts
    from .engrave import build_piece
    from .lily import dots
    styles = sorted(STYLES)
    for n in range(args.count):
        seed = args.seed + n
        style = args.style if args.style in STYLES else styles[seed % len(styles)]
        tune = compose(style, seed)
        piece = make_piece(tune, "easy-primo", primo=args.primo, secondo=args.secondo)
        res = build_piece(piece, Path(args.output), tune.slug, layouts=_layouts(args.layout), paper=args.paper)
        print(f"{tune.title} (No. {seed}, {style}, {tune.key.name}): Primo {dots(piece.levels['p'])} "
              f"Secondo {dots(piece.levels['s'])}")
        for k, v in res.items():
            if k != "info":
                print(f"  {k:13} {v}")
