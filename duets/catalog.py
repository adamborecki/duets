"""Recipes: turning a library tune into a finished, rated duet.

A *flavor* is a named arrangement recipe ("easy primo", "four-part chorale",
"tune in the bass" ...).  ``make_piece`` runs the right arranger, plans the
engraving and rates the difficulty.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import Optional

from .arrange import Options, arrange, arrange_satb, join_pieces
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
    rot = ROTATION["hymn" if tune.has_satb else "lead"]
    return rot[index % len(rot)]


def make_piece(tune: Tune, flavor: str = "", style: str = "auto", key: str = "auto", seed: int = 0,
               primo: Optional[int] = None, secondo: Optional[int] = None, melody: Optional[str] = None) -> Piece:
    """Arrange ``tune`` with a named flavor (levels/melody can be overridden)."""
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
