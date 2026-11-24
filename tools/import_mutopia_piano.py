#!/usr/bin/env python3
"""Import easy piano classics from the Mutopia Project into ``library/piano``
so they can be turned into "one hand each" duets.

    python tools/import_mutopia_piano.py /path/to/MutopiaProject/ftp

Every source is compiled by LilyPond itself to MIDI (repeats written out, one
track per staff) and read back.  Mutopia editions carry their own licences
(public domain, CC BY or CC BY-SA); the licence and the name of the person
who typeset each piece are copied into the credit line of the file written.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from duets import midiin                                            # noqa: E402
from duets.abc import parse_abc                                     # noqa: E402
from duets.abcwrite import write_abc                                # noqa: E402
from duets.library import slugify, tune_from_abc                    # noqa: E402
from duets.model import Ev, F, TBar, Tune                           # noqa: E402

HERE = Path(__file__).resolve().parent
B, S, BU = "Johann Sebastian Bach", "Robert Schumann", "Friedrich Burgmüller"
AM = "Notebook for Anna Magdalena Bach"
# path under ftp/ | title | composer | subtitle | tempo text | bpm (per beat)
TABLE = [
    ("BachJS/BWVAnh114/anna-magdalena-04/anna-magdalena-04.ly", "Minuet in G", "Christian Petzold (attrib. J. S. Bach)", AM + ", BWV Anh. 114", "Tempo di menuetto", 112),
    ("BachJS/BWVAnh115/anna-magdalena-05/anna-magdalena-05.ly", "Minuet in G minor", "Christian Petzold (attrib. J. S. Bach)", AM + ", BWV Anh. 115", "Tempo di menuetto", 108),
    ("BachJS/BWVAnh116/anna-magdalena-07/anna-magdalena-07.ly", "Minuet in G (No. 7)", B + " (attrib.)", AM + ", BWV Anh. 116", "Tempo di menuetto", 116),
    ("BachJS/BWVAnh113/anna-magdalena-03/anna-magdalena-03.ly", "Minuet in F", B + " (attrib.)", AM + ", BWV Anh. 113", "Tempo di menuetto", 112),
    ("BachJS/BWVAnh126/anna-magdalena-22/anna-magdalena-22.ly", "Musette in D", B + " (attrib.)", AM + ", BWV Anh. 126", "Allegretto", 96),
    ("BachJS/BWVAnh118/BWV-118/BWV-118.ly", "Minuet in B-flat", B + " (attrib.)", AM + ", BWV Anh. 118", "Tempo di menuetto", 112),
    ("BachJS/BWVAnh119/BWV-119/BWV-119.ly", "Polonaise in G minor", B + " (attrib.)", AM + ", BWV Anh. 119", "Alla polacca", 84),
    ("BachJS/BWVAnh120/BWV-120/BWV-120.ly", "Minuet in A minor", B + " (attrib.)", AM + ", BWV Anh. 120", "Tempo di menuetto", 108),
    ("BachJS/BWVAnh121/BWV-121/BWV-121.ly", "Minuet in C minor", B + " (attrib.)", AM + ", BWV Anh. 121", "Tempo di menuetto", 104),
    ("BachJS/BWVAnh127/BWV-127/BWV-127.ly", "March in E-flat", B + " (attrib.)", AM + ", BWV Anh. 127", "Tempo di marcia", 100),
    ("BachJS/BWVAnh128/BWV-128/BWV-128.ly", "Polonaise in D minor", B + " (attrib.)", AM + ", BWV Anh. 128", "Alla polacca", 84),
    ("BachJS/BWVAnh131/air/air.ly", "Air in F", B + " (attrib.)", AM + ", BWV Anh. 131", "Andante", 80),
    ("BachJS/BWV846/wtk1-prelude1/wtk1-prelude1.ly", "Prelude in C", B, "The Well-Tempered Clavier I, BWV 846", "Moderato", 72),
    ("BachJS/BWV772/bach-invention-01/bach-invention-01.ly", "Invention No. 1 in C", B, "Two-Part Inventions, BWV 772", "Allegro moderato", 76),
    ("BachJS/BWV779/bach-invention-08/bach-invention-08.ly", "Invention No. 8 in F", B, "Two-Part Inventions, BWV 779", "Allegro", 96),
    ("BachJS/BWV784/bach-invention-13/bach-invention-13.ly", "Invention No. 13 in A minor", B, "Two-Part Inventions, BWV 784", "Allegro moderato", 72),
    ("SchumannR/O68/schumann-op68-01-melodie/schumann-op68-01-melodie.ly", "Melody", S, "Album for the Young, Op. 68 No. 1", "Not fast", 92),
    ("SchumannR/O68/schumann-op68-02-marche-militaire/schumann-op68-02-marche-militaire.ly", "Soldiers' March", S, "Album for the Young, Op. 68 No. 2", "Lively and crisp", 112),
    ("SchumannR/O68/schumann-op68-03-chanson-fredonnee/schumann-op68-03-chanson-fredonnee.ly", "Humming Song", S, "Album for the Young, Op. 68 No. 3", "Not fast", 96),
    ("SchumannR/O68/schumann-op68-04-choral/schumann-op68-04-choral.ly", "Chorale", S, "Album for the Young, Op. 68 No. 4", "Broadly", 72),
    ("SchumannR/O68/schumann-op68-05-petite-piece/schumann-op68-05-petite-piece.ly", "A Little Piece", S, "Album for the Young, Op. 68 No. 5", "Not fast", 100),
    ("SchumannR/O68/schumann-op68-06-pauvre-orpheline/schumann-op68-06-pauvre-orpheline.ly", "The Poor Orphan", S, "Album for the Young, Op. 68 No. 6", "Slowly", 76),
    ("SchumannR/O68/schumann-op68-07-chanson-du-chasseur/schumann-op68-07-chanson-du-chasseur.ly", "Hunting Song", S, "Album for the Young, Op. 68 No. 7", "Fresh and cheerful", 100),
    ("SchumannR/O68/schumann-op68-08-cavalier-sauvage/schumann-op68-08-cavalier-sauvage.ly", "The Wild Rider", S, "Album for the Young, Op. 68 No. 8", "Lively", 104),
    ("SchumannR/O68/schumann-op68-09-chanson-populaire/schumann-op68-09-chanson-populaire.ly", "Folk Song", S, "Album for the Young, Op. 68 No. 9", "In a plaintive tone", 80),
    ("SchumannR/O68/schumann-op68-10-gai-laboureur/schumann-op68-10-gai-laboureur.ly", "The Happy Farmer", S, "Album for the Young, Op. 68 No. 10", "Fresh and cheerful", 108),
    ("SchumannR/O68/schumann-op68-11-sicilienne/schumann-op68-11-sicilienne.ly", "Sicilienne", S, "Album for the Young, Op. 68 No. 11", "Playfully", 84),
    ("SchumannR/O68/schumann-op68-14-petite-etude/schumann-op68-14-petite-etude.ly", "Little Study", S, "Album for the Young, Op. 68 No. 14", "Softly and evenly", 72),
    ("SchumannR/O68/schumann-op68-16-premier-chagrin/schumann-op68-16-premier-chagrin.ly", "First Loss", S, "Album for the Young, Op. 68 No. 16", "Not fast", 84),
    ("SchumannR/O68/schumann-op68-18-moissonneurs/schumann-op68-18-moissonneurs.ly", "The Reaper's Song", S, "Album for the Young, Op. 68 No. 18", "Not very fast", 76),
    ("BurgmullerJFF/O100/25EF-01/25EF-01.ly", "La candeur (Openness)", BU, "25 Easy and Progressive Studies, Op. 100 No. 1", "Allegro moderato", 120),
    ("BurgmullerJFF/O100/25EF-02/25EF-02.ly", "Arabesque", BU, "Op. 100 No. 2", "Allegro scherzando", 132),
    ("BurgmullerJFF/O100/25EF-03/25EF-03.ly", "Pastorale", BU, "Op. 100 No. 3", "Andantino", 60),
    ("BurgmullerJFF/O100/25EF-04/25EF-04.ly", "The Little Party", BU, "Op. 100 No. 4", "Allegro non troppo", 120),
    ("BurgmullerJFF/O100/25EF-05/25EF-05.ly", "Innocence", BU, "Op. 100 No. 5", "Moderato", 92),
    ("BurgmullerJFF/O100/25EF-06/25EF-06.ly", "Progress", BU, "Op. 100 No. 6", "Allegro", 120),
    ("BurgmullerJFF/O100/25EF-07/25EF-07.ly", "The Clear Stream", BU, "Op. 100 No. 7", "Allegro vivace", 152),
    ("BurgmullerJFF/O100/25EF-08/25EF-08.ly", "La gracieuse (Gracefulness)", BU, "Op. 100 No. 8", "Moderato", 88),
    ("BurgmullerJFF/O100/25EF-09/25EF-09.ly", "The Hunt", BU, "Op. 100 No. 9", "Allegro vivace", 100),
    ("BurgmullerJFF/O100/25EF-10/25EF-10.ly", "Tender Flower", BU, "Op. 100 No. 10", "Moderato", 108),
    ("BurgmullerJFF/O100/25EF-11/25EF-11.ly", "The Wagtail", BU, "Op. 100 No. 11", "Allegretto", 120),
    ("BurgmullerJFF/O100/25EF-12/25EF-12.ly", "The Farewell", BU, "Op. 100 No. 12", "Allegro molto agitato", 132),
    ("BurgmullerJFF/O100/25EF-13/25EF-13.ly", "Consolation", BU, "Op. 100 No. 13", "Allegro moderato", 132),
    ("BurgmullerJFF/O100/25EF-14/25EF-14.ly", "Styrian Dance", BU, "Op. 100 No. 14", "Mouvement de valse", 152),
    ("BurgmullerJFF/O100/25EF-15/25EF-15.ly", "Ballade", BU, "Op. 100 No. 15", "Allegro con brio", 96),
    ("BurgmullerJFF/O100/25EF-16/25EF-16.ly", "Sweet Sorrow", BU, "Op. 100 No. 16", "Allegro moderato", 112),
    ("BurgmullerJFF/O100/25EF-17/25EF-17.ly", "The Chatterbox", BU, "Op. 100 No. 17", "Allegretto", 76),
    ("BurgmullerJFF/O100/25EF-18/25EF-18.ly", "Restlessness", BU, "Op. 100 No. 18", "Allegro agitato", 126),
    ("TchaikovskyPI/O39/01MorningPrayer/01MorningPrayer.ly", "Morning Prayer", "Pyotr Ilyich Tchaikovsky", "Album for the Young, Op. 39 No. 1", "Andante", 60),
    ("TchaikovskyPI/O39/05MarchOfTheWoodenSoldiers/05MarchOfTheWoodenSoldiers.ly", "March of the Wooden Soldiers", "Pyotr Ilyich Tchaikovsky", "Album for the Young, Op. 39 No. 5", "Tempo di marcia", 120),
    ("TchaikovskyPI/O39/16OldFrenchSong/16OldFrenchSong.ly", "Old French Song", "Pyotr Ilyich Tchaikovsky", "Album for the Young, Op. 39 No. 16", "Molto moderato", 66),
    ("BeethovenLv/WoO59/fur_Elise_WoO59/fur_Elise_WoO59.ly", "Für Elise (complete)", "Ludwig van Beethoven", "Bagatelle in A minor, WoO 59", "Poco moto", 60),
    ("BeethovenLv/WoO82/menuett_WoO82/menuett_WoO82.ly", "Minuet in E-flat", "Ludwig van Beethoven", "WoO 82", "Tempo di menuetto", 108),
    ("BeethovenLv/O49/LVB_Sonate_49no2_2/LVB_Sonate_49no2_2.ly", "Minuet from Sonata Op. 49 No. 2", "Ludwig van Beethoven", "Tempo di Menuetto", "Tempo di menuetto", 112),
    ("MozartWA/KV2/menuet_k2/menuet_k2.ly", "Minuet in F, K. 2", "Wolfgang Amadeus Mozart", "written at the age of six", "Tempo di menuetto", 112),
    ("MozartWA/KV545/K545-1/K545-1.ly", "Sonata in C, K. 545: Allegro", "Wolfgang Amadeus Mozart", "Sonata facile, first movement", "Allegro", 120),
    ("MozartWA/KV545/K545-2/K545-2.ly", "Sonata in C, K. 545: Andante", "Wolfgang Amadeus Mozart", "Sonata facile, second movement", "Andante", 60),
    ("MozartWA/KV331/KV331_1_1_tema/KV331_1_1_tema.ly", "Theme from Sonata in A, K. 331", "Wolfgang Amadeus Mozart", "Andante grazioso", "Andante grazioso", 50),
    ("ChopinFF/O28/Chop-28-4/Chop-28-4.ly", "Prelude in E minor", "Frédéric Chopin", "Op. 28 No. 4", "Largo", 50),
    ("ChopinFF/O28/Chop-28-6/Chop-28-6.ly", "Prelude in B minor", "Frédéric Chopin", "Op. 28 No. 6", "Lento assai", 52),
    ("ChopinFF/O28/Chop-28-7/Chop-28-7.ly", "Prelude in A", "Frédéric Chopin", "Op. 28 No. 7", "Andantino", 76),
    ("ChopinFF/O28/Chop-28-20/Chop-28-20.ly", "Prelude in C minor", "Frédéric Chopin", "Op. 28 No. 20", "Largo", 44),
    ("SatieE/gymnopedie_1/gymnopedie_1.ly", "Gymnopédie No. 1", "Erik Satie", "Lent et douloureux", "Lent et douloureux", 72),
    ("SatieE/gymnopedie_2/gymnopedie_2.ly", "Gymnopédie No. 2", "Erik Satie", "Lent et triste", "Lent et triste", 72),
    ("SatieE/gymnopedie_3/gymnopedie_3.ly", "Gymnopédie No. 3", "Erik Satie", "Lent et grave", "Lent et grave", 72),
    ("JoplinS/entertainer/entertainer.ly", "The Entertainer (complete)", "Scott Joplin, 1902", "A ragtime two-step", "Not fast", 76),
    ("JoplinS/maple/maple.ly", "Maple Leaf Rag (complete)", "Scott Joplin, 1899", "", "Tempo di marcia", 84),
    ("JoplinS/peacherine/peacherine.ly", "Peacherine Rag", "Scott Joplin, 1901", "", "Not fast", 80),
    ("JoplinS/EliteSyncopations/EliteSyncopations.ly", "Elite Syncopations", "Scott Joplin, 1902", "", "Not fast", 80),
    ("JoplinS/PineappleRag/PineappleRag.ly", "Pine Apple Rag", "Scott Joplin, 1908", "", "Not fast", 80),
    ("JoplinS/sun-flower-slow-drag/sun-flower-slow-drag.ly", "Sunflower Slow Drag", "Scott Joplin & Scott Hayden, 1901", "", "Not fast", 80),
    ("JoplinS/TheStrenuousLife/TheStrenuousLife.ly", "The Strenuous Life", "Scott Joplin, 1902", "A ragtime two-step", "Not fast", 80),
    ("JoplinS/original/original.ly", "Original Rags", "Scott Joplin, 1899", "", "Not fast", 80),
    ("ClementiM/O36/sonatina-1/sonatina-1.ly", "Sonatina in C", "Muzio Clementi", "Op. 36 No. 1", "Allegro", 126),
    ("KuhlauF/O20/sonatine-1-allegro/sonatine-1-allegro.ly", "Sonatina in C: Allegro", "Friedrich Kuhlau", "Op. 20 No. 1", "Allegro", 120),
    ("SchubertF/D780/MomentsNo3/MomentsNo3.ly", "Moment musical No. 3", "Franz Schubert", "D. 780 No. 3", "Allegro moderato", 92),
    ("BrahmsJ/O39/waltz-op39-15/waltz-op39-15.ly", "Waltz in A-flat", "Johannes Brahms", "Op. 39 No. 15", "Tempo di valse", 108),
    ("GriegE/O12/No03_Albumblatt/No03_Albumblatt.ly", "Album Leaf", "Edvard Grieg", "Lyric Pieces, Op. 12 No. 7", "Allegretto e dolce", 88),
]


def partial_of(text: str) -> Fraction:
    m = re.search(r"\\partial\s+(\d+)(\.?)(?:\s*\*\s*(\d+))?", text)
    if not m:
        return F(0)
    d = Fraction(4, int(m.group(1)))
    if m.group(2):
        d = d * 3 / 2
    if m.group(3):
        d = d * int(m.group(3))
    return d


def header_field(text: str, name: str) -> str:
    m = re.search(r"\b%s\s*=\s*\"([^\"]*)\"" % name, text)
    return m.group(1).strip() if m else ""


def compile_midis(lyfile: Path, work: Path) -> list:
    d = work / "src"
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(lyfile.parent, d, ignore=shutil.ignore_patterns("Makefile", "*.pdf", "*.png", "*.mid*"),
                    ignore_dangling_symlinks=True)
    for f in list(d.rglob("*.ly")) + list(d.rglob("*.ily")) + list(d.rglob("*.lyi")):
        subprocess.run(["convert-ly", "-e", str(f)], capture_output=True, text=True)
    target = d / lyfile.name
    # write repeats out in the performance (they are folded again after reading the MIDI)
    text = target.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"\\score\s*\{", lambda m: "\\score { \\unfoldRepeats ", text)
    target.write_text(text, encoding="utf-8")
    subprocess.run(["lilypond", "--loglevel=ERROR", "-dno-point-and-click", target.name],
                   capture_output=True, text=True, cwd=str(d), timeout=600)
    return sorted(d.glob("*.mid*"), key=lambda p: (len(p.name), p.name))


def build(path: Path, work: Path):
    src = path.read_text(encoding="utf-8", errors="replace")
    extra = "".join(p.read_text(encoding="utf-8", errors="replace") for p in path.parent.rglob("*.ily"))
    midis = compile_midis(path, work)
    if not midis:
        return None, "no MIDI produced"
    data = midiin.read_midi(midis[0])
    st = [s for s in data["staves"] if len(s) >= 8]
    if len(st) < 2:
        return None, f"{len(st)} staves in MIDI"
    if len(st) > 2:
        # keep the two fullest (piano staves)
        st = sorted(st, key=len, reverse=True)[:2]
        st.sort(key=lambda s: -sum(n[2] for n in s) / len(s))
    hi, lo = st[0], st[1]
    if sum(n[2] for n in hi) / len(hi) < sum(n[2] for n in lo) / len(lo):
        hi, lo = lo, hi
    partial = partial_of(src + extra)
    grid = midiin.bar_grid(data["meters"], data["end"], partial)
    rh = midiin.staff_bars(hi, grid, data["keys"])
    lh = midiin.staff_bars(lo, grid, data["keys"])
    keys = midiin.bar_keys([hi, lo], grid)
    has_pick = grid[0][1] < grid[0][2].bar_len
    segs = midiin.fold_repeats(keys, min_len=8, pickup=has_pick)
    tune = Tune(title="")
    tune.key = data["keys"][0][1] if data["keys"] else tune.key
    tune.meter = grid[0][2]

    def add(i, **flags):
        start, length, meter, changed = grid[i]
        tb = TBar(length=length)
        tb.melody = rh[i][0]
        if len(rh[i]) > 1:
            tb.voices["rh2"] = rh[i][1]
        tb.voices["lh"] = lh[i][0]
        if len(lh[i]) > 1:
            tb.voices["lh2"] = lh[i][1]
        if changed:
            tb.meter = meter
        for k, v in flags.items():
            setattr(tb, k, v)
        if i == 0 and has_pick:
            tb.pickup = True
        tune.bars.append(tb)

    for seg in segs:
        if seg[0] == "plain":
            for i in seg[1]:
                add(i)
        else:
            _, body, first_end, second_end = seg
            for n_, i in enumerate(body):
                add(i, start_repeat=(n_ == 0))
            if first_end:
                for i in first_end:
                    add(i, volta=1)
                tune.bars[-1].end_repeat = True
                for i in second_end:
                    add(i, volta=2)
            else:
                tune.bars[-1].end_repeat = True
    # LilyPond sources often give minor keys as their relative major: check the last bass note
    if tune.key.mode == "major":
        last = None
        for i in range(len(grid) - 1, -1, -1):
            ns = [p for v in lh[i] for e in v for p in e.pitches]
            if ns:
                last = min(ns, key=lambda p: p.midi)
                break
        rel = (tune.key.tonic.pc + 9) % 12
        if last is not None and last.pc == rel:
            from duets.theory import Key
            tune.key = Key(tune.key.scale()[5].in_octave(4), "minor")
    # drop empty trailing bars
    while tune.bars and all(e.is_rest for e in tune.bars[-1].melody) and \
            all(all(e.is_rest for e in v) for v in tune.bars[-1].voices.values()):
        tune.bars.pop()
    names = []
    for b in tune.bars:
        for n in b.voices:
            if n not in names:
                names.append(n)
    for b in tune.bars:
        for n in names:
            b.voices.setdefault(n, [Ev(b.length)])
    lic = header_field(src, "license") or header_field(src, "copyright") or "see mutopiaproject.org"
    who = header_field(src, "maintainer")
    return (tune, lic, who), ""


def main():
    root = Path(sys.argv[1])
    dst = Path(__file__).resolve().parent.parent / "library" / "piano"
    dst.mkdir(parents=True, exist_ok=True)
    only = sys.argv[2] if len(sys.argv) > 2 else ""
    ok = 0
    with tempfile.TemporaryDirectory() as tmp:
        for rel, title, composer, subtitle, tempo_text, bpm in TABLE:
            if only and only.lower() not in title.lower():
                continue
            path = root / rel
            if not path.exists():
                print(f"  missing {rel}")
                continue
            try:
                res, why = build(path, Path(tmp))
            except Exception as exc:
                res, why = None, f"{type(exc).__name__}: {str(exc)[:160]}"
            if res is None:
                print(f"  skipped {title}: {why}")
                continue
            tune, lic, who = res
            if len(tune.bars) < 8:
                print(f"  skipped {title}: only {len(tune.bars)} bars came through")
                continue
            tune.title = title
            tune.subtitle = subtitle
            tune.composer = composer
            tune.tempo_text = tempo_text
            tune.tempo = bpm
            tune.category = "piano"
            tune.tags = ["classical", slugify(composer.split(",")[0].split("(")[0].split()[-1])]
            tune.source = "Mutopia Project"
            tune.credit = (f"{composer.split(',')[0]}. Source edition: {who or 'Mutopia Project'} for the "
                           f"Mutopia Project ({lic}).")
            tune.slug = slugify(title + "-" + composer.split(",")[0].split("(")[0].split()[-1])
            text = write_abc(tune)
            try:
                back = tune_from_abc(parse_abc(text)[0])
                same = len(back.bars) == len(tune.bars) and all(
                    a.melody == b.melody and a.voices == b.voices for a, b in zip(tune.bars, back.bars))
            except Exception as exc:
                same = False
            if not same:
                print(f"  skipped {title}: round-trip mismatch")
                continue
            (dst / f"{tune.slug}.abc").write_text(text, encoding="utf-8")
            ok += 1
            print(f"  {tune.slug}: {len(tune.bars)} bars, {tune.key.short}, {tune.meter.text}; {lic[:40]}")
    print(f"imported {ok} of {len(TABLE)}")


if __name__ == "__main__":
    main()
