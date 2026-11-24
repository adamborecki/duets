"""Duet books: themed collections assembled into one PDF per layout.

Every piece is rendered separately (and cached), then the pages are joined,
numbered, given a title page, a how-to page, a table of contents and PDF
bookmarks, and the fonts are embedded once for the whole book.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from pypdf import PdfReader, PdfWriter
from pypdf._page import PageObject

from . import render
from .catalog import FLAVORS, ROTATION, SATB_FLAVORS, Entry, entry_piece
from .engrave import LAYOUTS, PAPERS, SCREEN_FULL, SCREEN_HALF, render_layout
from .library import load_library
from .lily import dots, q
from .model import Tune

ROOT = Path(__file__).resolve().parent.parent
BOOKS_DIR = ROOT / "books"


@dataclass
class BookDef:
    id: str
    title: str
    subtitle: str
    blurb: str
    select: Callable            # (list[Tune]) -> list[Entry]
    order: int = 50


# ---------------------------------------------------------------------------
# selection helpers
# ---------------------------------------------------------------------------
def sort_key(t: Tune) -> str:
    s = re.sub(r"^(the|a|an)\s+", "", t.title.lower())
    return re.sub(r"[^a-z0-9 ]", "", s)


def rotate(tunes: list, section: str = "", offset: int = 0, flavors: Optional[list] = None,
           specials: Optional[dict] = None) -> list:
    """One entry per tune, cycling through the flavor rotation so the two
    seats get a mix of easier and fuller parts."""
    out = []
    k = offset
    for t in tunes:
        if specials and t.slug in specials:
            fl = specials[t.slug]
        elif flavors:
            fl = flavors[k % len(flavors)]
        else:
            rot = ROTATION["hymn" if t.has_satb else "lead"]
            fl = rot[k % len(rot)]
        if fl in SATB_FLAVORS and not t.has_satb:
            fl = ROTATION["lead"][k % len(ROTATION["lead"])]
        out.append(Entry(slug=t.slug, flavor=fl, section=section, seed=k))
        k += 1
    return out


def with_tag(tunes, *tags, category=None, collection=None):
    out = []
    for t in tunes:
        if category and t.category not in ((category,) if isinstance(category, str) else category):
            continue
        if collection and t.collection not in ((collection,) if isinstance(collection, str) else collection):
            continue
        if tags and not any(tag in t.tags for tag in tags):
            continue
        out.append(t)
    return sorted(out, key=sort_key)


def unique(entries: list) -> list:
    """Drop repeats: the same tune twice, or two versions of one song under
    slightly different titles ("God Rest Ye/You Merry ...")."""
    seen = set()
    out = []
    for e in entries:
        key = re.sub(r"\b(ye|you|a|the|o|oh|upon)\b", "", e.slug.replace("-", " "))
        key = re.sub(r"greensleeves|[^a-z0-9]", "", key)
        if e.slug in seen or key in seen:
            continue
        seen.add(e.slug)
        seen.add(key)
        out.append(e)
    return out


# ---------------------------------------------------------------------------
# book definitions
# ---------------------------------------------------------------------------
SETTINGS = {  # hymns that get a three-stanza setting in the seasonal books
    "savior-of-the-nations-come": "setting", "wake-awake-for-night-is-flying": "setting",
    "o-come-o-come-emmanuel": "setting", "comfort-comfort-ye-my-people": "setting",
    "on-jordans-bank-the-baptists-cry": "setting-easy", "from-heaven-above": "setting",
    "lo-how-a-rose-eer-blooming": "setting", "now-thank-we-all-our-god": "setting",
    "a-mighty-fortress-is-our-god": "setting", "praise-to-the-lord-the-almighty": "setting",
    "silent-night": "setting-easy", "o-come-all-ye-faithful": "setting",
    "joy-to-the-world": "setting-easy", "hark-the-herald-angels-sing": "setting",
    "come-ye-thankful-people-come": "setting", "we-gather-together": "setting-easy",
    "for-the-beauty-of-the-earth": "setting-easy", "of-the-fathers-love-begotten": "setting-easy",
}


def _advent_christmas(tunes):
    hymns = [t for t in tunes if t.collection == "hymns"]
    adv = with_tag(hymns, "advent") + [t for t in hymns if t.slug in ("wake-awake-for-night-is-flying",
                                                                  "the-day-is-surely-drawing-near")]
    e = rotate(sorted(adv, key=sort_key), "Advent", 0, specials=SETTINGS)
    xmas = with_tag(tunes, "christmas", collection=("hymns", "carols"))
    e += rotate(xmas, "Christmas", 3, specials=SETTINGS)
    e += rotate(with_tag(hymns, "epiphany"), "Epiphany", 1, specials=SETTINGS)
    e += rotate([t for t in tunes if t.slug in ("auld-lang-syne",)], "New Year", 0)
    return unique(e)


THANKSGIVING = [
    "now-thank-we-all-our-god", "come-ye-thankful-people-come", "we-gather-together",
    "for-the-beauty-of-the-earth", "praise-to-the-lord-the-almighty", "all-creatures-of-our-god-and-king",
    "praise-god-from-whom-all-blessings-flow", "simple-gifts", "the-ash-grove", "harvest-home",
    "america-the-beautiful", "shine-on-harvest-moon", "over-the-river-and-through-the-wood",
    "we-plow-the-fields-and-scatter", "let-all-things-now-living", "holy-god-we-praise-thy-name",
    "great-is-thy-faithfulness", "praise-my-soul-the-king-of-heaven", "o-god-our-help-in-ages-past",
    "our-god-our-help-in-ages-past", "sing-to-the-lord-of-harvest", "turkey-in-the-straw",
    "home-sweet-home", "bless-this-house", "doxology",
]


def _thanksgiving(tunes):
    by = {t.slug: t for t in tunes}
    chosen = [by[s] for s in THANKSGIVING if s in by]
    extra = [t for t in with_tag(tunes, "thanksgiving") if t not in chosen]
    return unique(rotate(chosen + extra, "", 0, specials=SETTINGS))


CHURCH_YEAR = [("Lent", ("lent",)), ("Palm Sunday", ("palm-sunday",)), ("Maundy Thursday", ("maundy-thursday",)),
               ("Good Friday", ("good-friday",)), ("Easter", ("easter",)), ("Ascension", ("ascension",)),
               ("Pentecost", ("pentecost",)), ("Trinity", ("trinity",)), ("Transfiguration", ("transfiguration",)),
               ("Reformation", ("reformation",)), ("End Times", ("end-times",))]


def _church_year(tunes):
    hymns = [t for t in tunes if t.collection == "hymns"]
    e = []
    for k, (name, tags) in enumerate(CHURCH_YEAR):
        e += rotate(with_tag(hymns, *tags), name, k, specials=SETTINGS)
    return unique(e)


PRAISE_TAGS = [("Praise", ("praise",)), ("Thanksgiving", ("thanksgiving",)), ("Opening & Closing", ("opening", "closing")),
               ("Morning & Evening", ("morning", "evening")), ("The Word & the Church", ("word", "church", "missions"))]
COMFORT_TAGS = [("Trust", ("trust",)), ("Redeemer", ("redeemer",)), ("Cross & Comfort", ("comfort",)),
                ("Justification", ("justification", "confession")), ("Baptism & Supper", ("baptism", "communion")),
                ("Prayer & Consecration", ("prayer", "consecration", "obedience", "stewardship")),
                ("Home, Life & Heaven", ("home", "life", "heaven", "funeral"))]
_SEASONAL = {"advent", "christmas", "epiphany", "lent", "palm-sunday", "maundy-thursday", "good-friday", "easter",
             "ascension", "pentecost", "trinity", "transfiguration", "reformation", "end-times"}


def _general(groups):
    def select(tunes):
        hymns = [t for t in tunes if t.collection == "hymns" and not (_SEASONAL & set(t.tags))]
        e = []
        for k, (name, tags) in enumerate(groups):
            e += rotate(with_tag(hymns, *tags), name, 2 * k, specials=SETTINGS)
        return unique(e)
    return select


def _folk_songs(tunes):
    songs = [t for t in tunes if t.category in ("folk", "patriotic") and ("song" in t.tags or t.source != "Nottingham Music Database")]
    return rotate(sorted(songs, key=sort_key), "", 0)


def _dances(tunes):
    d = [t for t in tunes if t.category == "folk" and t.source == "Nottingham Music Database" and "song" not in t.tags]
    secs = [("Jigs", lambda t: t.meter.compound), ("Reels, Hornpipes & Marches", lambda t: not t.meter.compound and t.meter.num != 3),
            ("Waltzes & Airs", lambda t: t.meter.num == 3 and not t.meter.compound)]
    e = []
    for k, (name, f) in enumerate(secs):
        e += rotate(sorted([t for t in d if f(t)], key=sort_key), name, k)
    return unique(e)


def _crooners(tunes):
    s = [t for t in tunes if t.category == "standard" and {"ella", "sinatra", "natkingcole"} & set(t.tags)]
    return rotate(sorted(s, key=sort_key), "", 0)


def _jazz_age(tunes):
    s = [t for t in tunes if t.category == "standard" and not ({"ella", "sinatra", "natkingcole"} & set(t.tags))]
    return rotate(sorted(s, key=sort_key), "", 2)


def _oldies(tunes):
    s = [t for t in tunes if t.category == "oldies"]
    return rotate(sorted(s, key=sort_key), "", 1)


def _spirituals(tunes):
    s = [t for t in tunes if t.category == "spiritual" or t.collection == "hymns-leadsheet" or "gospel" in t.tags]
    return rotate(sorted(s, key=sort_key), "", 0)


def _classical(tunes):
    s = [t for t in tunes if t.category == "classical"]
    return rotate(sorted(s, key=sort_key), "", 0)


def _rags(tunes):
    s = [t for t in tunes if t.category in ("rag", "march") or "rag" in t.tags or ("march" in t.tags and t.category != "folk")]
    return rotate(sorted(s, key=sort_key), "", 0, flavors=["easy-primo", "easy-secondo", "trade", "easy-primo-rich"])


def _children(tunes):
    s = [t for t in tunes if "children" in t.tags or t.category == "children"]
    return rotate(sorted(s, key=sort_key), "", 0, flavors=["both-easy", "gentle", "easy-primo", "trade-easy", "easy-secondo", "tune-below"])


BACH_SECTIONS = [("Advent", ("advent",)), ("Christmas & New Year", ("christmas", "newyear")), ("Epiphany", ("epiphany",)),
                 ("Lent & Passion", ("lent", "good-friday", "confession")), ("Palm Sunday & Easter", ("palm-sunday", "easter")),
                 ("Pentecost & Trinity", ("pentecost", "trinity")), ("Reformation", ("reformation",)),
                 ("Praise & Thanksgiving", ("praise", "thanksgiving")), ("Trust & Prayer", ("trust", "prayer", "redeemer", "communion", "opening")),
                 ("Morning & Evening", ("morning", "evening")), ("The Last Things", ("end-times", "funeral"))]


def _bach(tunes):
    ch = [t for t in tunes if t.collection == "bach-chorales"]
    e = []
    for k, (name, tags) in enumerate(BACH_SECTIONS):
        e += rotate(with_tag(ch, *tags), name, k, flavors=["chorale", "chorale-octaves", "chorale-easy", "chorale", "chorale-full"])
    return unique(e)


def _diabelli(tunes):
    d = sorted([t for t in tunes if t.collection == "diabelli"], key=lambda t: t.slug)
    e = [Entry(slug=t.slug, flavor="original", section="Melodious Pieces, Op. 149" if "op149" in t.slug
               else "Pleasures of Youth, Op. 163", cap=0) for t in d]
    return e


CLASSIC_SECTIONS = [("Bach & His Circle", ("bach", "petzold")), ("Mozart", ("mozart",)), ("Beethoven", ("beethoven",)),
                    ("Clementi & Kuhlau", ("clementi", "kuhlau")), ("Schubert", ("schubert",)),
                    ("Schumann: Album for the Young", ("schumann",)), ("Burgmüller: Easy Studies, Op. 100", ("burgmuller",)),
                    ("Chopin", ("chopin",)), ("Brahms", ("brahms",)), ("Tchaikovsky", ("tchaikovsky",)),
                    ("Grieg", ("grieg",)), ("Satie", ("satie",))]


def _classics(tunes):
    p = [t for t in tunes if t.collection == "piano"]
    e = []
    for name, tags in CLASSIC_SECTIONS:
        sec = sorted([t for t in p if set(tags) & set(t.tags)], key=lambda t: t.slug if "burgmuller" in tags or "schumann" in tags else sort_key(t))
        e += [Entry(slug=t.slug, flavor="original", section=name, cap=0) for t in sec]
    return unique(e)


def _joplin(tunes):
    p = sorted([t for t in tunes if t.collection == "piano" and ({"joplin", "hayden"} & set(t.tags))], key=sort_key)
    return [Entry(slug=t.slug, flavor="original", section="", cap=0) for t in p]


VARIATION_TUNES = ["twinkle-twinkle-little-star", "ode-to-joy", "surprise-symphony-andante", "simple-gifts",
                   "yankee-doodle", "what-shall-we-do-with-a-drunken-sailor", "au-clair-de-la-lune",
                   "when-the-saints-go-marching-in", "oh-susanna", "good-king-wenceslas", "deck-the-halls",
                   "old-macdonald-had-a-farm", "pachelbel-canon-in-d", "amazing-grace", "lightly-row",
                   "skip-to-my-lou", "joy-to-the-world", "the-ash-grove", "london-bridge-is-falling-down",
                   "mary-had-a-little-lamb"]


def _variations(tunes):
    by = {t.slug: t for t in tunes}
    return [Entry(slug=s, flavor="variations", cap=0) for s in VARIATION_TUNES if s in by]


def _rounds(tunes):
    r = sorted([t for t in tunes if t.category == "round"], key=sort_key)
    return [Entry(slug=t.slug, flavor="round", cap=0) for t in r]


def _originals(tunes):
    o = sorted([t for t in tunes if t.category == "original"], key=lambda t: t.slug)
    return rotate(o, "", 0, flavors=["easy-primo", "easy-secondo", "trade", "gentle", "tune-below", "both-easy",
                                     "easy-primo-rich", "trade-easy"])


ORGAN_PIANO = ["savior-of-the-nations-come", "wake-awake-for-night-is-flying", "o-come-o-come-emmanuel",
               "comfort-comfort-ye-my-people", "on-jordans-bank-the-baptists-cry", "from-heaven-above",
               "lo-how-a-rose-eer-blooming", "of-the-fathers-love-begotten", "silent-night", "joy-to-the-world",
               "o-come-all-ye-faithful", "hark-the-herald-angels-sing", "now-thank-we-all-our-god",
               "come-ye-thankful-people-come", "we-gather-together", "praise-to-the-lord-the-almighty",
               "a-mighty-fortress-is-our-god", "holy-holy-holy", "beautiful-savior", "abide-with-me",
               "amazing-grace", "for-the-beauty-of-the-earth", "jesus-christ-is-risen-today",
               "o-sacred-head-now-wounded", "crown-him-with-many-crowns", "the-churchs-one-foundation"]


def _organ_piano(tunes):
    by = {t.slug: t for t in tunes}
    return [Entry(slug=s, flavor="organ-piano", cap=0) for s in ORGAN_PIANO if s in by and by[s].has_satb]


BOOKS = [
    BookDef("organ-piano", "Hymns for Organ & Piano", "Two instruments, two players",
            "The organ plays each hymn as it stands in the hymnal, with pedals; the piano adds the tune in "
            "octaves over flowing broken chords. Hymnal keys are kept. In the facing-pages edition the organ "
            "part is on the left-hand pages and the piano part on the right.", _organ_piano, 6),
    BookDef("variations", "Themes & Variations", "Familiar tunes with variations, for piano four hands",
            "Each tune is played plainly, then with a flowing accompaniment, with the tune in the bass, in the minor, "
            "as a jig, decorated, and in a broad finale.", _variations, 15),
    BookDef("rounds", "Rounds", "Canons for two players", "The Secondo chases the Primo.", _rounds, 16),
    BookDef("originals", "New Pieces", "Thirty-six original duets composed by the generator",
            "Waltzes, marches, minuets, jigs, lullabies and songs that nobody has ever played before. "
            "Run 'python -m duets new' for more.", _originals, 17),
    BookDef("bach-chorales", "Bach Chorales", "Four-part chorales of J. S. Bach set for piano four hands",
            "Bach's own harmonizations of the great Lutheran chorales, arranged by season, with chord symbols.", _bach, 3),
    BookDef("diabelli", "Diabelli: Melodious Pieces", "Original duets by Anton Diabelli, Op. 149 and Op. 163",
            "The classic teacher-and-pupil duets: the Primo stays within five notes, the Secondo supplies the harmony. "
            "Newly engraved with chord symbols.", _diabelli, 12),
    BookDef("classics", "Classics, One Hand Each", "Piano pieces by the masters shared between two players",
            "Each player takes one hand of the original: not a note is changed. Bach minuets, Schumann's "
            "Album for the Young, Burgmüller studies, Satie's Gymnopédies and more.", _classics, 12),
    BookDef("joplin-rags", "Joplin Rags, One Hand Each", "Scott Joplin's rags shared between two players",
            "The Entertainer and other rags, complete, with the right hand for the Primo and the left for the Secondo.",
            _joplin, 13),
    BookDef("advent-christmas", "Advent & Christmas", "Hymns and carols for piano four hands",
            "Advent chorales, Christmas hymns from the Lutheran tradition and favourite carols.", _advent_christmas, 1),
    BookDef("thanksgiving", "Thanksgiving & Harvest", "Hymns and songs of gratitude for piano four hands",
            "Hymns of thanks and praise and a few harvest-time songs.", _thanksgiving, 2),
    BookDef("church-year", "Through the Church Year", "Hymns from Lent to the Last Sunday, for piano four hands",
            "Chorales and hymns for Lent, Holy Week, Easter, Pentecost, Trinity, Reformation and the end of the church year.",
            _church_year, 3),
    BookDef("hymns-of-praise", "Hymns of Praise", "Hymns for any Sunday, volume 1, for piano four hands",
            "Praise and thanksgiving, opening and closing hymns, morning and evening, the Word and the Church.",
            _general(PRAISE_TAGS), 4),
    BookDef("hymns-of-trust", "Hymns of Trust & Comfort", "Hymns for any Sunday, volume 2, for piano four hands",
            "Hymns of trust, comfort, prayer and the Christian life.", _general(COMFORT_TAGS), 5),
    BookDef("spirituals-gospel", "Spirituals & Gospel Songs", "for piano four hands",
            "African-American spirituals and gospel-song favourites.", _spirituals, 6),
    BookDef("ella-frank-nat", "Songs Ella, Frank & Nat Sang", "Standards from 1912 to 1930 for piano four hands",
            "Gershwin, Kern, Rodgers, Youmans, Donaldson: songs recorded by Ella Fitzgerald, Frank Sinatra and "
            "Nat King Cole that are now in the public domain in the United States.", _crooners, 7),
    BookDef("jazz-age", "Jazz Age Standards", "More songs of the 1920s for piano four hands",
            "Hits of the 1920s, from Fats Waller to Isham Jones.", _jazz_age, 8),
    BookDef("oldies", "Gaslight & Tin Pan Alley", "Parlour songs, waltzes and marches, 1860–1925, for piano four hands",
            "Sweetheart waltzes, vaudeville numbers, Cohan marches and Neapolitan songs.", _oldies, 9),
    BookDef("folk-songs", "Folk Songs & Shanties", "Songs from the British Isles, America and beyond, for piano four hands",
            "Traditional songs, Stephen Foster, sea shanties and patriotic airs.", _folk_songs, 10),
    BookDef("jigs-reels", "Jigs, Reels & Hornpipes", "Fiddle tunes for piano four hands",
            "Dance tunes from Ireland, Scotland, England and North America.", _dances, 11),
    BookDef("classical-themes", "Classical Themes", "Famous melodies for piano four hands",
            "Well-loved themes from Bach to Brahms.", _classical, 12),
    BookDef("rags-marches", "Rags & Marches", "for piano four hands",
            "Joplin, Sousa and friends.", _rags, 13),
    BookDef("childrens-songs", "Nursery Songs & Singing Games", "Very easy duets for piano four hands",
            "Children's songs in the easiest settings.", _children, 14),
]


def book_by_id(book_id: str) -> BookDef:
    for b in BOOKS:
        if b.id == book_id:
            return b
    raise KeyError(f"no book {book_id!r}; available: {', '.join(b.id for b in BOOKS)}")


# ---------------------------------------------------------------------------
# rendering workers
# ---------------------------------------------------------------------------
_TUNES: Optional[dict] = None


def _tunes() -> dict:
    global _TUNES
    if _TUNES is None:
        _TUNES = {t.slug: t for t in load_library()}
    return _TUNES


def _render_chunk(job: tuple) -> list:
    """Render several entries in all requested layouts.  The first-attempt
    LilyPond sources of the whole chunk are compiled in a single run."""
    entry_ds, layouts, workdir, paper = job
    from .engrave import first_texts
    pieces = {}
    texts = []
    out = []
    for ed in entry_ds:
        entry = Entry(**ed)
        try:
            piece = entry_piece(entry, _tunes())
            pieces[entry.id] = (entry, piece)
            for layout in layouts:
                texts += first_texts(piece, layout, paper)
        except Exception as exc:
            import traceback
            for layout in layouts:
                out.append({"ok": False, "id": entry.id, "slug": entry.slug, "layout": layout,
                            "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-1500:]})
    try:
        render.compile_batch(texts)
    except Exception:
        pass
    for entry, piece in pieces.values():
        for layout in layouts:
            out.append(_render_one(entry, piece, layout, workdir, paper))
    return out


def _render_one(entry: Entry, piece, layout: str, workdir: str, paper: str) -> dict:
    t0 = time.time()
    try:
        r = render_layout(piece, layout, Path(workdir), entry.id, paper=paper)
        return {"ok": True, "id": entry.id, "slug": entry.slug, "layout": layout, "path": str(r["path"]),
                "pages": r["pages"], "warnings": r["warnings"], "title": piece.title,
                "subtitle": piece.subtitle, "composer": piece.composer, "levels": dict(piece.levels),
                "key": piece.key.short, "meter": piece.meter.text, "bars": len(piece.bars),
                "flavor": entry.flavor, "flavor_text": piece.flavor, "section": entry.section,
                "problems": piece.stats.get("problems", []), "secs": round(time.time() - t0, 1)}
    except Exception as exc:  # keep the book going; report at the end
        import traceback
        return {"ok": False, "id": entry.id, "slug": entry.slug, "layout": layout,
                "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-1500:]}


# ---------------------------------------------------------------------------
# front matter
# ---------------------------------------------------------------------------
ABOUT = [
    ("How to use this book",
     "These are duets for one piano, four hands. The SECONDO player sits on the left and plays the lower "
     "part; the PRIMO player sits on the right and plays the upper part. In the facing-pages edition the "
     "Secondo part is always on the left-hand page and the Primo part on the right-hand page, and both pages "
     "break their lines at the same bars, so the bar numbers at the start of each line always match."),
    ("Difficulty",
     "The dots beside each part rate it from one (beginner) to five (late intermediate). The two seats "
     "are rated separately, and most pieces give one player an easier part than the other — look at the "
     "contents page to choose who sits where. Ratings are measured from the notes themselves: speed, "
     "chords, leaps, rhythm, key and how independent the hands are."),
    ("Chord symbols",
     "Chord symbols are printed above both parts. They show the harmony the arrangement is built on, "
     "so either player can fill in, simplify or improvise."),
    ("8va",
     "The Primo part often lies high. A dotted bracket marked 8 means: play one octave higher than written."),
    ("About the music",
     "Every melody here is in the public domain in the United States. The duet settings were made by "
     "“duets”, an open-source arranger; they are free to copy, share, perform and change. "
     "Sources are credited at the foot of each piece."),
]


def _front_ly(book: BookDef, toc: list, paper: tuple, edition: str, per_page: int, numbers_note: str) -> str:
    w, h = paper
    lw = w - 36
    out = ['\\version "2.24.0"', "#(set-global-staff-size 18)", "\\paper {",
           "  #(set! paper-alist (cons '(\"duet\" . (cons (* %.2f mm) (* %.2f mm))) paper-alist))" % (w, h),
           '  #(set-paper-size "duet")',
           "  top-margin = 16\\mm bottom-margin = 14\\mm left-margin = 18\\mm right-margin = 18\\mm",
           "  print-page-number = ##f oddHeaderMarkup = ##f evenHeaderMarkup = ##f",
           "  oddFooterMarkup = ##f evenFooterMarkup = ##f",
           "  ragged-bottom = ##t ragged-last-bottom = ##t",
           "  markup-markup-spacing.basic-distance = #2.6",
           "  markup-markup-spacing.padding = #0.35",
           "}", "\\header { tagline = ##f }", ""]
    # title page
    out += [
        "\\markup \\vspace #%d" % max(4, int(h / 22)),
        "\\markup \\fill-line { \\fontsize #11 \\bold %s }" % q(book.title),
        "\\markup \\vspace #1.5",
        "\\markup \\fill-line { \\fontsize #3 \\italic %s }" % q(book.subtitle),
        "\\markup \\vspace #4",
        "\\markup \\fill-line { \\fontsize #6 \"●●○○○\" }",
        "\\markup \\vspace #4",
        "\\markup \\fill-line { \\fontsize #1 %s }" % q(f"{len(toc)} duets for one piano, four hands"),
        "\\markup \\vspace #0.6",
        "\\markup \\fill-line { \\fontsize #0 \\italic %s }" % q(edition),
        "\\markup \\vspace #%d" % max(3, int(h / 30)),
        "\\markup \\fill-line { \\fontsize #-1 %s }" % q(book.blurb if len(book.blurb) < 110 else ""),
        "\\pageBreak",
    ]
    # how-to page
    for head, body in ABOUT:
        out.append("\\markup \\fontsize #2 \\bold %s" % q(head))
        out.append("\\markup \\vspace #0.2")
        out.append("\\markup \\override #'(line-width . %d) \\fontsize #0 \\wordwrap-string %s" % (int(lw / 1.75), q(body)))
        out.append("\\markup \\vspace #0.9")
    out.append("\\pageBreak")
    # contents
    count = 0
    section = None
    first = True
    dotw = 15
    for item in toc:
        if count % per_page == 0:
            if not first:
                out.append("\\pageBreak")
            out.append("\\markup \\fill-line { \\fontsize #5 \\bold %s }" %
                       q("Contents" if first else "Contents (continued)"))
            out.append("\\markup \\fill-line { \\fontsize #-2 \\italic %s }" % q(numbers_note))
            out.append("\\markup \\vspace #0.8")
            first = False
            section = None
        if item["section"] and item["section"] != section:
            section = item["section"]
            out.append("\\markup \\vspace #0.35")
            out.append("\\markup \\fontsize #1 \\bold \\caps %s" % q(section))
            count += 1
        title = item["title"]
        sub = item.get("subtitle") or ""
        left = "\\line { %s %s }" % (q(title), ("\\fontsize #-2 \\italic %s" % q(sub)) if sub else "")
        right = ("\\line { \\fontsize #-2 \\concat { \\pad-to-box #'(0 . %d) #'(0 . 1) %s "
                 "\\pad-to-box #'(0 . %d) #'(0 . 1) %s } \\pad-to-box #'(0 . 5) #'(0 . 1) \\bold %s }"
                 % (dotw, q("P " + dots(item["levels"]["p"])), dotw, q("S " + dots(item["levels"]["s"])),
                    q(str(item["page"]))))
        out.append("\\markup \\fontsize #-0.5 \\fill-with-pattern #1 #RIGHT \".\" %s %s" % (left, right))
        count += 1
    return "\n".join(out) + "\n"


def _blank(path: Path, paper: tuple) -> Path:
    w = PdfWriter()
    w.add_page(PageObject.create_blank_page(width=paper[0] * 72 / 25.4, height=paper[1] * 72 / 25.4))
    with open(path, "wb") as fh:
        w.write(fh)
    return path


def _pair_up(src: Path, dst: Path, paper: tuple) -> int:
    """Lay consecutive pages side by side (for the 16:10 screen editions)."""
    r = PdfReader(str(src))
    w = PdfWriter()
    pages = list(r.pages)
    pw, ph = paper[0] * 72 / 25.4, paper[1] * 72 / 25.4
    from pypdf import Transformation
    for i in range(0, len(pages), 2):
        sheet = PageObject.create_blank_page(width=2 * pw, height=ph)
        sheet.merge_transformed_page(pages[i], Transformation().translate(0, 0))
        if i + 1 < len(pages):
            sheet.merge_transformed_page(pages[i + 1], Transformation().translate(pw, 0))
        w.add_page(sheet)
    with open(dst, "wb") as fh:
        w.write(fh)
    return len(w.pages)


EDITION = {
    "facing": "Print edition · facing pages: Secondo on the left, Primo on the right",
    "score": "Print edition · full score, both parts together",
    "screen": "Screen edition · both parts side by side",
    "screen-score": "Screen edition · full score",
}


def _front_matter(book: BookDef, toc: list, layout: str, paper: str, workdir: Path) -> tuple:
    """Build the front pages.  Returns (pdf path, number of sheets)."""
    if layout in ("facing", "score"):
        size = PAPERS[paper]
        per_page = 40
    else:
        size = SCREEN_HALF
        per_page = 34
    sections = len({t["section"] for t in toc if t["section"]})
    n_lines = len(toc) + sections
    toc_pages = max(1, math.ceil(n_lines / per_page))
    note = {"facing": "page numbers are those of the Secondo (left-hand) page",
            "score": "", "screen": "numbers are screen pages", "screen-score": "numbers are screen pages"}[layout]
    ly = _front_ly(book, toc, size, EDITION[layout], per_page, note)
    raw = workdir / f"front.{layout}.raw.pdf"
    info = render.compile_ly(ly, raw)
    n = info["pages"]
    out = workdir / f"front.{layout}.pdf"
    if layout == "facing":
        # an odd number of front pages puts the first Secondo page on the left
        parts = [raw]
        if n % 2 == 0:
            parts.append(_blank(workdir / "blank.letter.pdf", size))
            n += 1
        render.concat(parts, out)
        return out, n
    if layout == "score":
        shutil.copyfile(raw, out)
        return out, n
    sheets = _pair_up(raw, out, size)
    return out, sheets


def front_page_count(n_items: int, n_sections: int, layout: str) -> int:
    """How many sheets the front matter will take (needed to number the contents)."""
    per_page = 40 if layout in ("facing", "score") else 34
    toc_pages = max(1, math.ceil((n_items + n_sections) / per_page))
    n = 2 + toc_pages
    if layout == "facing":
        return n + (1 if n % 2 == 0 else 0)
    if layout == "score":
        return n
    return math.ceil(n / 2)


# ---------------------------------------------------------------------------
# building
# ---------------------------------------------------------------------------
def build_book(book: BookDef, layouts=LAYOUTS, paper: str = "letter", jobs: int = 0,
               outdir: Optional[Path] = None, limit: int = 0, verbose: bool = True) -> dict:
    tunes = load_library()
    entries = book.select(tunes)
    if limit:
        entries = entries[:limit]
    if not entries:
        return {"id": book.id, "pieces": 0}
    outdir = Path(outdir or BOOKS_DIR / book.id)
    outdir.mkdir(parents=True, exist_ok=True)
    work = ROOT / ".cache" / "books" / book.id
    work.mkdir(parents=True, exist_ok=True)
    jobs = jobs or max(1, (os.cpu_count() or 2))
    chunk = 6
    job_list = [([e.__dict__ for e in entries[i:i + chunk]], tuple(layouts), str(work), paper)
                for i in range(0, len(entries), chunk)]
    t0 = time.time()
    results = {}
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for rs in ex.map(_render_chunk, job_list):
            for r in rs:
                results[(r["id"], r["layout"])] = r
    failures = [r for r in results.values() if not r["ok"]]
    report = {"id": book.id, "title": book.title, "subtitle": book.subtitle, "blurb": book.blurb,
              "pieces": 0, "layouts": {}, "failures": failures,
              "warnings": [], "items": []}
    good = [e for e in entries if all(results[(e.id, l)]["ok"] for l in layouts)]
    report["pieces"] = len(good)
    for layout in layouts:
        items = [results[(e.id, layout)] for e in good]
        n_sections = len({it["section"] for it in items if it["section"]})
        front_n = front_page_count(len(items), n_sections, layout)
        page = front_n + 1
        toc = []
        for it in items:
            toc.append({"title": it["title"], "subtitle": it["subtitle"], "levels": it["levels"],
                        "section": it["section"], "page": page})
            page += it["pages"]
        front, n_front = _front_matter(book, toc, layout, paper, work)
        if n_front != front_n:
            # contents ran to a different number of pages than predicted: renumber once
            shift = n_front - front_n
            for t in toc:
                t["page"] += shift
            front, n_front = _front_matter(book, toc, layout, paper, work)
        joined = work / f"{book.id}.{layout}.joined.pdf"
        render.concat([front] + [Path(it["path"]) for it in items], joined)
        numbered = work / f"{book.id}.{layout}.numbered.pdf"
        render.stamp_page_numbers(joined, numbered, start_index=n_front, first_number=n_front + 1,
                                  outer=(layout == "facing"))
        final = outdir / f"{book.id}-{layout}.pdf"
        _finalize_with_outline(numbered, final, toc)
        report["layouts"][layout] = {"path": str(final), "pages": render.page_count(final),
                                     "bytes": final.stat().st_size}
        for it in items:
            report["warnings"] += [f"{it['id']}: {w}" for w in it["warnings"]]
        if layout == layouts[0]:
            for it, t in zip(items, toc):
                report["items"].append({"slug": it["slug"], "title": it["title"], "subtitle": it["subtitle"],
                                        "composer": it["composer"], "levels": it["levels"], "key": it["key"],
                                        "meter": it["meter"], "bars": it["bars"], "flavor": it["flavor"],
                                        "flavor_text": it["flavor_text"], "section": it["section"],
                                        "problems": it["problems"], "pages": {layout: t["page"]}})
        else:
            for item, t in zip(report["items"], toc):
                item["pages"][layout] = t["page"]
    report["seconds"] = round(time.time() - t0, 1)
    (outdir / "contents.json").write_text(json.dumps(
        {k: v for k, v in report.items() if k not in ("failures", "warnings")}, indent=1), encoding="utf-8")
    _write_book_readme(book, report, outdir)
    if verbose:
        sizes = ", ".join(f"{l}: {v['pages']}p {v['bytes'] // 1024}KB" for l, v in report["layouts"].items())
        print(f"[{book.id}] {report['pieces']} pieces in {report['seconds']}s — {sizes}"
              + (f" — {len(failures)} FAILED" if failures else ""))
        for f in failures[:5]:
            print("   failed:", f["id"], f["layout"], f["error"])
    return report


def _finalize_with_outline(src: Path, dst: Path, toc: list) -> None:
    tmp = src.with_suffix(".embedded.pdf")
    render.finalize(src, tmp)
    r = PdfReader(str(tmp))
    w = PdfWriter()
    for pg in r.pages:
        w.add_page(pg)
    section = None
    parent = None
    for t in toc:
        idx = min(max(t["page"] - 1, 0), len(w.pages) - 1)
        if t["section"] and t["section"] != section:
            section = t["section"]
            parent = w.add_outline_item(section, idx)
        w.add_outline_item(t["title"], idx, parent=parent if t["section"] else None)
    w.add_metadata({"/Title": "", "/Creator": "duets"})
    with open(dst, "wb") as fh:
        w.write(fh)
    tmp.unlink(missing_ok=True)


def _write_book_readme(book: BookDef, report: dict, outdir: Path) -> None:
    lines = [f"# {book.title}", "", f"*{book.subtitle}*", "", book.blurb, "",
             f"**{report['pieces']} duets.** Pick the edition that suits how you play:", ""]
    names = {"facing": "Print · facing pages (Secondo left, Primo right)", "score": "Print · full score",
             "screen": "Screen · parts side by side (16:10)", "screen-score": "Screen · full score (16:10)"}
    for layout, v in report["layouts"].items():
        lines.append(f"- [{names[layout]}]({Path(v['path']).name}) — {v['pages']} pages")
    lines += ["", "| # | Title | Key | Primo | Secondo | Setting |", "|---|---|---|---|---|---|"]
    section = None
    for i, it in enumerate(report["items"], 1):
        if it["section"] and it["section"] != section:
            section = it["section"]
            lines.append(f"| | **{section}** | | | | |")
        sub = f" <br><sub>{it['subtitle']}</sub>" if it["subtitle"] else ""
        lines.append(f"| {i} | {it['title']}{sub} | {it['key']} | {dots(it['levels']['p'])} {it['levels']['p']} | "
                     f"{dots(it['levels']['s'])} {it['levels']['s']} | {it['flavor_text']} |")
    (outdir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
