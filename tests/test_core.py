"""Tests for the pieces everything else stands on: spelling, rhythm notation,
ABC reading/writing, the arrangers and the church calendar."""
import datetime as dt
import shutil
from fractions import Fraction as F
from pathlib import Path

import pytest

from duets.abc import parse_abc
from duets.abcwrite import write_abc
from duets.arrange import Options, arrange, arrange_satb
from duets.catalog import FLAVORS, make_piece
from duets.compose import compose
from duets.difficulty import check, rate
from duets.library import load_library, tune_from_abc, validate
from duets.model import N, R, total
from duets.notate import notate, split_note, split_rest
from duets.sundays import advent1, day_for, easter, lectionary_year, thanksgiving
from duets.theory import IV, Chord, Key, Meter, P

TUNE = """X:1
T:Test Waltz
M:3/4
L:1/4
K:G
D | "G"G2 B | "C"c2 e | "D7"d3/2 c/2 A | "G"G2 :|
"""


@pytest.fixture(scope="module")
def library():
    return {t.slug: t for t in load_library()}


def test_pitch_spelling_and_intervals():
    assert P("C4").midi == 60 and P("C4").lily() == "c'"
    assert P("Bb2").lily() == "bes," and P("F#5").lily() == "fis''"
    assert (P("F#4") + IV["M3"]).name == "A#4"
    assert (P("Bb3") + IV["m7"]).name == "Ab4"


@pytest.mark.parametrize("name,sharps", [("C", 0), ("Bb", -2), ("F#m", 3), ("D dor", 0), ("Gmix", 0), ("Eb", -3)])
def test_key_signatures(name, sharps):
    assert Key.parse(name).sharps == sharps


def test_key_spells_chromatic_notes_sensibly():
    d = Key.parse("D")
    assert d.spell(63).name == "D#4" and d.spell(60).name == "C4" and d.spell(65).name == "F4"


def test_chord_parsing_and_tones():
    assert [p.class_name for p in Chord.parse("F#m7b5").tones()] == ["F#", "A", "C", "E"]
    assert Chord.parse("D/f#").name == "D/F#"
    assert Chord.parse("Cd").kind == "dim" and Chord.parse("Ca").kind == "aug"
    assert Chord.parse("Bbm").transpose(IV["M2"]).name == "Cm"
    assert Chord.parse("N.C.") is None


@pytest.mark.parametrize("meter,start,dur,expect", [
    ((4, 4), 0, 3, [3]), ((4, 4), "3/2", 1, ["1/2", "1/2"]), ((4, 4), "1/2", 1, [1]),
    ((4, 4), 0, "5/2", [2, "1/2"]), ((4, 4), 1, "3/2", [1, "1/2"]),
    ((3, 4), 0, "5/2", [2, "1/2"]), ((6, 8), 0, 2, ["3/2", "1/2"]), ((6, 8), 1, 1, ["1/2", "1/2"]),
])
def test_notes_are_split_on_the_beat(meter, start, dur, expect):
    assert split_note(F(start), F(dur), Meter(*meter)) == [F(x) for x in expect]


def test_rests_follow_the_metre():
    assert split_rest(F(1), F(3), Meter(4, 4)) == [F(1), F(2)]
    assert split_rest(F(0), F(2), Meter(3, 4)) == [F(1), F(1)]
    assert split_rest(F(0), F(3, 2), Meter(6, 8)) == [F(3, 2)]


def test_triplets_are_grouped():
    ev = [N(P("C4"), F(1, 3)), N(P("D4"), F(1, 3)), N(P("E4"), F(1, 3)), N(P("F4"), 1)]
    toks = notate(ev, Meter(2, 4))
    assert toks[0][0] == "tuplet" and len(toks[0][2]) == 3 and toks[1].dur == 1


def test_abc_round_trip():
    tune = tune_from_abc(parse_abc(TUNE)[0])
    assert tune.bars[0].pickup and tune.bars[-1].end_repeat
    again = tune_from_abc(parse_abc(write_abc(tune))[0])
    assert [b.melody for b in again.bars] == [b.melody for b in tune.bars]
    assert [b.chords for b in again.bars] == [b.chords for b in tune.bars]


def test_library_loads_and_is_valid(library):
    assert len(library) > 900
    bad = {s: validate(t) for s, t in library.items() if validate(t)}
    assert not bad, list(bad.items())[:5]


@pytest.mark.parametrize("slug", ["savior-of-the-nations-come", "embraceable-you", "the-irish-washerwoman",
                                  "twinkle-twinkle-little-star", "minuet-in-g-petzold", "diabelli-op149-03",
                                  "frere-jacques", "bach-wake-awake-for-night-is-flying"])
def test_every_flavor_fills_every_bar(library, slug):
    tune = library[slug]
    for flavor in FLAVORS:
        piece = make_piece(tune, flavor)
        for i, b in enumerate(piece.bars):
            for hand, voices in b.hands.items():
                for v in voices:
                    assert total(v) == b.length, (slug, flavor, i, hand)
        assert all(1 <= lv <= 5 for lv in piece.levels.values())
        assert not [p for p in piece.stats["problems"] if "duration" in p or "notated" in p]


def test_easy_recipes_are_easier_than_full_ones(library):
    tune = library["ye-banks-and-braes-o-bonnie-doon"]
    easy = make_piece(tune, "both-easy")
    full = make_piece(tune, "easy-primo-rich")
    assert easy.levels["s"] < full.levels["s"]


def test_players_stay_out_of_each_others_way(library):
    for slug in ["ding-dong-merrily-on-high", "what-shall-we-do-with-a-drunken-sailor", "tea-for-two"]:
        piece = arrange(library[slug], Options(primo=2, secondo=3))
        rate(piece)
        assert not [p for p in check(piece) if "reaches into" in p], slug


def test_composer_is_deterministic():
    a, b = compose("waltz", 7), compose("waltz", 7)
    assert write_abc(a) == write_abc(b)
    assert len(a.bars) == 20 and not validate(a)
    assert write_abc(compose("waltz", 8)) != write_abc(a)


def test_church_calendar():
    assert easter(2027) == dt.date(2027, 3, 28)
    assert advent1(2026) == dt.date(2026, 11, 29)
    assert thanksgiving(2026) == dt.date(2026, 11, 26)
    assert day_for(dt.date(2026, 11, 29)).name == "First Sunday of Advent"
    assert day_for(dt.date(2026, 11, 22)).name == "Christ the King"
    assert day_for(dt.date(2027, 5, 16)).name == "Pentecost"
    assert lectionary_year(dt.date(2026, 11, 29)) == "B"


@pytest.mark.skipif(shutil.which("lilypond") is None, reason="LilyPond not installed")
def test_engraving_produces_matching_part_pages(library, tmp_path):
    from duets.engrave import render_layout
    piece = make_piece(library["ding-dong-merrily-on-high"], "easy-primo")
    r = render_layout(piece, "facing", tmp_path, "t")
    assert r["pages"] % 2 == 0 and not [w for w in r["warnings"] if "barcheck" in w]
    r = render_layout(piece, "score", tmp_path, "t")
    assert r["pages"] >= 1 and not [w for w in r["warnings"] if "barcheck" in w]


def test_practice_notes_match_the_piece(library):
    from duets.playdata import TICKS, piece_notes
    tune = library["silent-night"]
    piece = make_piece(tune, "easy-primo")
    data = piece_notes(piece)
    order = piece.play_order()
    assert len(data["bars"]) == len(order)
    assert data["bars"] == sorted(data["bars"]) and data["bars"][0] == 0
    assert data["len"] == round(sum(float(piece.bars[i].length) for i in order) * TICKS)
    assert set(data["h"]) == {"prh", "plh", "srh", "slh"}
    for hand, arr in data["h"].items():
        assert len(arr) % 3 == 0
        starts, durs, midis = arr[0::3], arr[1::3], arr[2::3]
        assert starts, hand
        assert all(0 <= t < data["len"] for t in starts)
        assert all(d >= 1 for d in durs)
        assert all(t + d <= data["len"] for t, d in zip(starts, durs))
        assert all(21 <= m <= 108 for m in midis)            # on the piano
    # the Primo's top line starts on the tune's first note
    first = min(zip(data["h"]["prh"][0::3], data["h"]["prh"][2::3]))
    melody = [e for b in piece.bars for e in b.hands["prh"][0] if e.pitches]
    assert first[1] in {p.midi for p in melody[0].pitches}


def test_practice_notes_join_ties():
    from duets.playdata import TICKS, piece_notes
    tune = tune_from_abc(parse_abc("X:1\nT:Tied\nM:4/4\nL:1/4\nK:C\n\"C\"c4-|\"C\"c2 \"G7\"d2|\"C\"c4|]\n")[0])
    piece = arrange(tune, Options(primo=1, secondo=1, key="original"))
    data = piece_notes(piece)
    prh = list(zip(data["h"]["prh"][0::3], data["h"]["prh"][1::3]))
    assert (0, 6 * TICKS) in prh                              # a whole note tied to a half note sounds once


def test_page_tree_is_nested_without_losing_pages(tmp_path):
    from pypdf import PdfReader, PdfWriter
    from duets.render import balance_page_tree
    w = PdfWriter()
    for k in range(150):
        w.add_blank_page(width=100 + k, height=200)
    w.add_outline_item("Page 101", 100)
    balance_page_tree(w)
    out = tmp_path / "tree.pdf"
    with open(out, "wb") as fh:
        w.write(fh)
    r = PdfReader(str(out), strict=True)
    assert [int(p.mediabox.width) for p in r.pages] == [100 + k for k in range(150)]
    assert r.get_destination_page_number(r.outline[0]) == 100
    root = r.trailer["/Root"]["/Pages"]
    assert len(root["/Kids"]) <= 8 and root["/Count"] == 150
