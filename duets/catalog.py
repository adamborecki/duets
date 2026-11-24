"""Recipes: turning a library tune into a finished, rated duet.

A *flavor* is a named arrangement recipe ("easy primo", "four-part chorale",
"tune in the bass" ...).  ``make_piece`` runs the right arranger, plans the
engraving and rates the difficulty.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import Optional

from .arrange import Options, arrange, arrange_satb, arrange_split, join_pieces
from .difficulty import check, rate
from .engrave import plan_clefs
from .model import Piece, Tune

# name -> (description, Options template)
FLAVORS = {
    "easy-primo": ("Primo: the tune in octaves · Secondo: full accompaniment",
                   Options(primo=2, secondo=3, melody="p")),
    "easy-primo-rich": ("Primo: the tune in octaves · Secondo: busier accompaniment",
                        Options(primo=2, secondo=4, melody="p")),
    "easy-secondo": ("Primo: tune with harmony notes · Secondo: simple bass and chords",
                     Options(primo=3, secondo=2, melody="p")),
    "both-easy": ("Both parts easy: tune in octaves over held chords",
                  Options(primo=1, secondo=1, melody="p")),
    "gentle": ("Tune in octaves over a simple bass-and-chord pattern",
               Options(primo=2, secondo=2, melody="p")),
    "tune-below": ("Secondo plays the tune · Primo accompanies above",
                   Options(primo=2, secondo=2, melody="s")),
    "tune-below-flowing": ("Secondo plays the tune · Primo has flowing broken chords",
                           Options(primo=3, secondo=3, melody="s")),
    "trade": ("The tune passes between the players",
              Options(primo=2, secondo=3, melody="swap")),
    "trade-easy": ("The tune passes between the players (easy)",
                   Options(primo=2, secondo=2, melody="swap")),
    "showy-primo": ("Primo: tune over a running left hand · Secondo: simple",
                    Options(primo=4, secondo=2, melody="p")),
    # hymn flavors that use the real four-part setting
    "chorale": ("Four-part setting: soprano & alto (Primo), tenor & bass (Secondo)",
                Options(primo=3, secondo=2)),
    "chorale-octaves": ("Primo: the tune in octaves · Secondo: alto, tenor and bass",
                        Options(primo=2, secondo=3)),
    "chorale-easy": ("Primo: the tune in octaves · Secondo: tenor and bass",
                     Options(primo=2, secondo=2)),
    "chorale-full": ("Full four-part setting with octave bass",
                     Options(primo=4, secondo=4)),
    "setting": ("Three stanzas: chorale · tune in the Secondo · full", Options(primo=3, secondo=3)),
    "setting-easy": ("Two stanzas: tune in octaves · tune in the Secondo", Options(primo=2, secondo=2)),
    "original": ("Original duet, as the composer wrote it", Options()),
    "round": ("Round: the Secondo follows the Primo", Options(primo=2, secondo=2)),
    "variations": ("Theme and variations", Options(primo=2, secondo=3)),
}
SATB_FLAVORS = ("chorale", "chorale-octaves", "chorale-easy", "chorale-full", "setting", "setting-easy")

# what a book rotates through, by kind of tune (weights favour the easier side)
ROTATION = {
    "hymn": ["chorale", "chorale-octaves", "easy-primo", "chorale-easy", "tune-below-flowing",
             "chorale", "easy-secondo", "chorale-octaves", "trade", "chorale-full"],
    "lead": ["easy-primo", "easy-secondo", "trade", "gentle", "tune-below", "easy-primo",
             "tune-below-flowing", "both-easy", "easy-primo-rich", "trade-easy", "showy-primo"],
}


@dataclass
class Entry:
    slug: str
    flavor: str = "easy-primo"
    style: str = "auto"
    key: str = "auto"
    section: str = ""
    seed: int = 0
    title: str = ""
    cap: float = 4.2            # books keep both seats at or below this level when they can

    @property
    def id(self) -> str:
        return f"{self.slug}--{self.flavor}" + (f"-{self.style}" if self.style != "auto" else "")


def flavor_options(flavor: str, style: str = "auto", key: str = "auto", seed: int = 0) -> Options:
    desc, o = FLAVORS[flavor]
    return replace(o, style=style, key=key, seed=seed)


def default_flavor(tune: Tune, index: int = 0) -> str:
    if tune.category == "round":
        return "round"
    if tune.category in ("duet", "piano"):
        return "original"
    rot = ROTATION["hymn" if tune.has_satb else "lead"]
    return rot[index % len(rot)]


def make_piece(tune: Tune, flavor: str = "", style: str = "auto", key: str = "auto", seed: int = 0,
               primo: Optional[int] = None, secondo: Optional[int] = None, melody: Optional[str] = None) -> Piece:
    """Arrange ``tune`` with a named flavor (levels/melody can be overridden)."""
    if tune.category == "duet":
        piece = piece_from_duet(tune)
        finish(piece)
        return piece
    if tune.category == "piano":
        o = Options(primo=primo if primo is not None else 2, secondo=secondo if secondo is not None else 2)
        piece = arrange_split(tune, o)
        piece.arranger = "Duet version: each player takes one hand of the original"
        finish(piece)
        return piece
    if flavor == "round" and tune.category != "round":
        flavor = "trade-easy"
    if flavor == "round" or (not flavor and tune.category == "round"):
        from .variations import round_delay, round_piece
        piece = round_piece(tune, round_delay(tune), opts=Options(primo=primo or 2, secondo=secondo or 2))
        finish(piece)
        return piece
    if flavor == "variations":
        from .variations import variations
        piece = variations(tune, seed=seed)
        finish(piece)
        return piece
    flavor = flavor or default_flavor(tune)
    if flavor not in FLAVORS:
        raise KeyError(f"unknown flavor {flavor!r}; choose from {', '.join(FLAVORS)}")
    if flavor in SATB_FLAVORS and not tune.has_satb:
        flavor = {"chorale": "gentle", "chorale-octaves": "easy-primo", "chorale-easy": "gentle",
                  "chorale-full": "easy-primo-rich", "setting": "trade", "setting-easy": "trade-easy"}[flavor]
    desc, _ = FLAVORS[flavor]
    o = flavor_options(flavor, style, key, seed)
    if primo is not None:
        o.primo = primo
    if secondo is not None:
        o.secondo = secondo
    if melody is not None:
        o.melody = melody
    if flavor == "setting":
        a = arrange_satb(tune, replace(o, primo=3, secondo=2))
        k = a.key.short
        b = arrange(tune, replace(o, primo=3, secondo=2, melody="s", style="flowing", key=k))
        c = arrange_satb(tune, replace(o, primo=4, secondo=4, key=k))
        piece = join_pieces([a, b, c], labels=["1", "2", "3"])
    elif flavor == "setting-easy":
        a = arrange_satb(tune, replace(o, primo=2, secondo=2))
        k = a.key.short
        b = arrange(tune, replace(o, primo=2, secondo=2, melody="s", key=k))
        piece = join_pieces([a, b], labels=["1", "2"])
    elif flavor in SATB_FLAVORS:
        piece = arrange_satb(tune, o)
    else:
        piece = arrange(tune, o)
    piece.flavor = desc
    piece.arranger = desc
    finish(piece)
    return piece


def piece_from_duet(tune: Tune) -> Piece:
    """A tune stored with all four hands written out (voices prh/plh/srh/slh,
    with optional second voices prh2 ...) becomes a piece as it stands."""
    import copy
    from . import harmony as H
    from .model import PBar
    t = copy.deepcopy(tune)
    if not t.has_chords:
        H.infer_chords(t, min_unit=t.meter.beat_len * (1 if t.meter.compound else 2) if t.meter.beats >= 4 else None)
    bars = []
    for b in t.bars:
        pb = PBar(length=b.length)
        pb.pickup, pb.start_repeat, pb.end_repeat, pb.volta = b.pickup, b.start_repeat, b.end_repeat, b.volta
        pb.double_bar, pb.meter, pb.key = b.double_bar, b.meter, b.key
        pb.mark = b.label
        pb.chords = [(off, c.simplified(1)) for off, c in b.chords if c is not None]
        pb.hands["prh"] = [b.melody] + ([b.voices["prh2"]] if "prh2" in b.voices else [])
        for h in ("plh", "srh", "slh"):
            pb.hands[h] = [b.voices.get(h, [])] + ([b.voices[h + "2"]] if h + "2" in b.voices else [])
            pb.hands[h] = [v for v in pb.hands[h] if v]
        bars.append(pb)
    bars[0].dyn = {"p": "mf", "s": "mf"}
    bars[-1].final = True
    if "dacapo" in t.tags:
        marks = [i for i, b in enumerate(bars) if b.mark]
        if marks:
            bars[marks[0] - 1].text = "Fine"
            bars[-1].text = "D.C. al Fine"
    piece = Piece(title=t.title, key=t.key, meter=t.meter, bars=bars, tempo=t.tempo or 100,
                  tempo_text=t.tempo_text, subtitle=t.subtitle, composer=t.composer, credit=t.credit,
                  category=t.category, tags=list(t.tags), slug=t.slug, free_meter=t.free_meter)
    piece.flavor = FLAVORS["original"][0]
    piece.arranger = ""
    return piece


def finish(piece: Piece) -> Piece:
    plan_clefs(piece)
    rate(piece)
    piece.stats["problems"] = check(piece)
    return piece


# when a flavor turns out harder than a book wants, step down through these
_EASIER = {"showy-primo": "easy-secondo", "easy-primo-rich": "easy-primo", "tune-below-flowing": "tune-below",
           "trade": "trade-easy", "easy-secondo": "gentle", "easy-primo": "gentle", "tune-below": "gentle",
           "trade-easy": "gentle", "gentle": "both-easy", "chorale-full": "chorale", "setting": "setting-easy",
           "chorale": "chorale-easy", "chorale-octaves": "chorale-easy", "setting-easy": "chorale-easy"}


def entry_piece(entry: Entry, tunes: dict) -> Piece:
    """The piece for a book entry.  If the requested flavor comes out harder
    than ``entry.cap`` for either seat, easier flavors are tried instead."""
    tune = tunes[entry.slug]
    flavor = entry.flavor
    piece = None
    for _ in range(4):
        piece = make_piece(tune, flavor, entry.style, entry.key, entry.seed)
        if not entry.cap or max(piece.levels.values()) <= entry.cap or flavor not in _EASIER:
            break
        flavor = _EASIER[flavor]
    if entry.title:
        piece.title = entry.title
    return piece
