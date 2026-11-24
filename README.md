# duets

Piano duets — four hands, one piano — by the hundred, plus the generator that makes them.

Everything here is built from public-domain music: Lutheran hymns and Bach chorales, carols, folk songs and
fiddle tunes, the Great American Songbook up to 1930, rags, easy classics, Diabelli's own teacher-and-pupil
duets, nursery songs, rounds, theme-and-variation sets and brand-new pieces composed by the program.
Each duet is engraved with LilyPond, has **chord symbols over both parts**, and carries a **difficulty rating
for each seat**, because the two of you don't play at the same level and shouldn't have to.

## Just give me music

Open **[`index.html`](index.html)** in a browser (from this folder) for a searchable catalog of every duet,
or go straight to the [`books/`](books/) folder. Each book comes in four editions:

| Edition | File | Use it for |
|---|---|---|
| **Print · facing pages** | `…-facing.pdf` | Printing. Secondo is always the left-hand page, Primo the right-hand page; both break lines at the same bars, so the bar numbers at the start of each line match. Print double-sided, or lay two sheets side by side. |
| **Print · full score** | `…-score.pdf` | Seeing how the parts fit; both players read the same four-stave system. |
| **Screen · side by side** | `…-screen.pdf` | A laptop or tablet on the music stand: one 16:10 page shows Secondo left and Primo right, large notes. |
| **Screen · full score** | `…-screen-score.pdf` | The same, as a stacked score. |

Every PDF has bookmarks and a contents page listing the Primo and Secondo difficulty of each piece.

### Reading the ratings

`●○○○○` beginner · `●●○○○` late beginner · `●●●○○` early intermediate · `●●●●○` intermediate ·
`●●●●●` late intermediate. The rating is measured from the notes on the page (speed at the marked tempo,
chords, leaps, rhythm, key, how independent the hands are), separately for each player. Most settings give
one seat the easier part — the contents pages tell you which.

## Make your own

You need Python 3.10+, [LilyPond](https://lilypond.org/) 2.24+ and (recommended) Ghostscript.

```sh
pip install -e .            # or just: pip install pypdf
python -m duets list --search "silent"
python -m duets make "Silent Night"                       # all four editions + MIDI into ./out
python -m duets make "Embraceable You" --flavor easy-secondo --layout screen
python -m duets make "Ode to Joy" --primo 1 --secondo 3 --key G
python -m duets make wachet --flavor setting              # three-stanza hymn setting
python -m duets make "A Mighty Fortress" --flavor organ-piano   # organ (with pedals) + piano
python -m duets variations "Twinkle"                      # theme and variations
python -m duets new --style waltz --seed 42 --count 3     # compose new pieces
python -m duets abc my-tunes.abc                          # your own ABC file (chords optional)
python -m duets sunday --weeks 6                          # hymns for the coming Sundays
python -m duets sunday 2026-11-29 --weeks 4 --build       # ... and a PDF packet of them
python -m duets book advent-christmas                     # rebuild a book; "book all" for everything
python -m duets flavors                                   # list recipes and layouts
```

Useful switches for `make`: `--flavor`, `--primo N`, `--secondo N` (1–5), `--melody p|s|swap`,
`--style waltz|march|alberti|flowing|walking|ballad|stride|chorale|jig|pad`, `--key`, `--layout`,
`--paper letter|a4`.

### Recipes ("flavors")

| Flavor | Primo | Secondo |
|---|---|---|
| `easy-primo` | the tune in octaves | full accompaniment |
| `easy-secondo` | tune with harmony notes | simple bass and chords |
| `both-easy`, `gentle` | tune in octaves | held chords / simple bass-and-chord |
| `tune-below`, `tune-below-flowing` | accompanies from above | plays the tune |
| `trade`, `trade-easy` | the tune passes back and forth by section | |
| `showy-primo` | tune over a running left hand | simple |
| `chorale` (hymns) | soprano and alto | tenor and bass |
| `chorale-octaves`, `chorale-easy`, `chorale-full` | tune in octaves / full | lower voices of the real harmonization |
| `setting`, `setting-easy` (hymns) | several stanzas, each set differently | |
| `variations` | theme, flowing, tune in the bass, minore, jig, decorated, finale | |
| `round` | the Secondo follows the Primo in canon | |
| `organ-piano` (hymns) | **piano**: the tune in octaves over broken chords | **organ**: the hymnal setting on three staves, bass in the pedals |

Easy piano classics (`library/piano`) become "one hand each" duets: the Primo plays the composer's
right-hand part, the Secondo the left-hand part, with octave doublings where a hand is free — not a note
of the original is changed. Diabelli's duets are engraved as he wrote them.

### Add tunes

Put any [ABC](https://abcnotation.com/) file in `library/` (see [`library/README.md`](library/README.md)).
Chord symbols in quotes are used if present; otherwise the program harmonizes the melody itself. Hymns with
four voices (`V:S`, `V:A`, `V:T`, `V:B`) unlock the chorale flavors.

## What's inside

```
duets/        the generator
  theory.py     spelled pitches, keys, meters, chords
  abc.py        ABC reader · abcwrite.py writer · mxl.py MusicXML · midiin.py LilyPond-MIDI reader
  harmony.py    voicings with voice leading, bass lines, chord inference from four-part settings
  arrange.py    the four-hand arranger (textures by level and style), chorale and one-hand-each settings
  variations.py theme and variations, rounds · compose.py new tunes · autoharm.py chords for bare melodies
  difficulty.py ratings and sanity checks (hand collisions, stretches, un-notatable rhythms)
  notate.py     splitting durations the way engravers do · lily.py LilyPond output
  engrave.py    clefs, 8va, shared line/page breaks, the four editions · books.py book assembly
  sundays.py    the church year and hymn suggestions · site.py the catalog page
library/      about a thousand tunes in ABC, with sources and rights (library/README.md)
books/        the finished books
tools/        the importers that built the library
tests/        pytest
```

How an arrangement is made: the tune is transposed to a friendly key that puts the melody where the Primo's
hands fit; the melody is placed (in octaves, with thirds, or handed to the Secondo an octave lower); the
other part is generated from the chord symbols with a texture chosen by style and level — held chords,
oom-pah, Alberti figures, walking bass, stride — keeping each chord close to the last and keeping the two
players out of each other's octave; the result is checked (bar lengths, stretches, collisions) and rated.
Line breaks are planned once per piece and forced identically in both parts.

## Sources and rights

All melodies are in the public domain **in the United States**; songs from 1926–1930 may still be protected
elsewhere. Encodings come from the Open Hymnal Project, the Nottingham Music Database, OpenEWLD, the
music21 corpus and the Mutopia Project — details, and the few share-alike obligations, are in
[`library/README.md`](library/README.md). The generator's code is MIT-licensed. The arrangements it
produced are free to copy, perform and change.

Songs you might look for and not find — "Mona Lisa", "Summertime", "Winter Wonderland", most of Sinatra's
later book — are still under copyright, so they are not here.

## Honest limits

- These are rule-based arrangements, not a human arranger's. They are meant to be sight-readable and
  pleasant; a few will be plain, and now and then an inner chord will be odd. Chord symbols for hymns and
  classics are inferred from the notes and can be fussy.
- Dynamics, slurs, fingering and pedalling are mostly left to you.
- The organ-and-piano settings are a first version: one recipe, hymns only, and no registration hints.
- "One hand each" classics are only as easy as the original hand was.
- Ratings are estimates — good for comparing pieces, not gospel.
