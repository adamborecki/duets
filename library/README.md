# The tune library

Every `.abc` file here is one tune (or a few) in standard [ABC notation](https://abcnotation.com/wiki/abc:standard),
plus a handful of `%%duets key: value` lines for things ABC has no field for (category, tags, hymn-tune
name, credit). Drop your own ABC files into any folder here and they become available to `python -m duets`.

| Folder | What | Where it came from | Rights |
|---|---|---|---|
| `hymns/` | 287 hymns with their four-part settings (voices `S A T B`) | [Open Hymnal Project](http://openhymnal.org/) (mirror: `mzealey/openhymnal`) via `tools/import_openhymnal.py` | Public domain. Only files the project marks "copyright: public domain" were taken. |
| `bach-chorales/` | 146 chorale harmonizations by J. S. Bach | [music21](https://www.music21.org/) corpus via `tools/import_bach_chorales.py` | Public domain. |
| `folk/`, `carols/` (part) | Traditional tunes with chords | [Nottingham Music Database](https://github.com/jukedeck/nottingham-dataset) via `tools/import_nottingham.py` | Traditional / published before 1931; hand-picked. |
| `standards/`, `oldies/`, `spirituals/`, `rags/`, `classical/` (part), `carols/` (part), `hymns-leadsheet/` | Lead sheets (melody + chords) | [OpenEWLD](https://github.com/00sapo/OpenEWLD) via `tools/import_openewld.py` | Public domain **in the United States**: every title was checked by hand to be traditional or first published in 1930 or earlier. Some may still be protected in countries with life+70 terms. |
| `diabelli/` | Anton Diabelli's own four-hand duets, Op. 149 and Op. 163 | [Mutopia Project](https://www.mutopiaproject.org/), typeset by Alberto Simões, via `tools/import_mutopia_duets.py` | Music public domain; these encodings derive from CC BY-SA 3.0 editions and are **CC BY-SA 3.0**. |
| `piano/` | Easy piano classics (both hands, voices `S`/`rh2`/`lh`/`lh2`) | Mutopia Project via `tools/import_mutopia_piano.py` | Music public domain; each file's credit line names the Mutopia typesetter and licence (public domain, CC BY or CC BY-SA). Files derived from CC BY-SA editions are CC BY-SA. |
| `children/`, `rounds/`, `classical/themes.abc` | Nursery songs, rounds, a few famous themes | Written out by hand for this project | Traditional / public domain; the encodings are CC0. |
| `originals/` | 36 new tunes | Composed by `duets/compose.py` | CC0. |

Not here, on purpose: anything still under copyright in the United States — for example "Mona Lisa" (1950),
"Winter Wonderland" (1934), "Summertime" (1935) or "All of Me" (1931, free from 2027).
