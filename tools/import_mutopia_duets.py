#!/usr/bin/env python3
"""Import Anton Diabelli's original four-hand duets (Op. 149 and Op. 163)
from the Mutopia Project into ``library/diabelli``.

    python tools/import_mutopia_duets.py /path/to/MutopiaProject/ftp/DiabelliA

Each LilyPond source is compiled to MIDI with LilyPond itself (one track per
staff, repeats written out), read back, and the repeats are folded again.
Source editions: Alberto Simões for Mutopia, CC BY-SA 3.0 - so the files this
writes are CC BY-SA 3.0 as well.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from duets import midiin                                             # noqa: E402
from duets.abc import parse_abc                                      # noqa: E402
from duets.abcwrite import write_abc                                 # noqa: E402
from duets.library import slugify, tune_from_abc                     # noqa: E402
from duets.model import Ev, F, TBar, Tune, total                     # noqa: E402

HANDS = ("prh", "plh", "srh", "slh")


def compile_midi(src_text: str, staves: list, workdir: Path, name: str) -> Path:
    head = src_text[:src_text.index("\\score")]
    body = "\n".join(f'    \\new Staff = "{v}" \\unfoldRepeats {{ \\{v} }}' for v in staves)
    ly = head + "\n\\score {\n  <<\n" + body + "\n  >>\n  \\midi { }\n}\n"
    path = workdir / f"{name}.ly"
    path.write_text(ly, encoding="utf-8")
    subprocess.run(["convert-ly", "-e", str(path)], capture_output=True, text=True)
    proc = subprocess.run(["lilypond", "--loglevel=ERROR", "-dno-point-and-click", "-o", str(workdir / name), str(path)],
                          capture_output=True, text=True)
    out = workdir / f"{name}.midi"
    if not out.exists():
        raise RuntimeError(proc.stderr[-400:])
    return out


def var_text(src: str, name: str) -> str:
    m = re.search(r"^\s*%s\s*=" % re.escape(name), src, flags=re.M)
    if not m:
        return ""
    i = src.index("{", m.end())
    depth = 0
    j = i
    while j < len(src):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    return src[i:j + 1]


def partial_of(text: str) -> Fraction:
    m = re.search(r"\\partial\s+(\d+)(\.?)(?:\*(\d+))?", text)
    if not m:
        return F(0)
    d = Fraction(4, int(m.group(1)))
    if m.group(2):
        d = d * 3 / 2
    if m.group(3):
        d = d * int(m.group(3))
    return d


def section_bars(src: str, sec: str, workdir: Path, name: str):
    staves = [f"primo{sec}Up", f"primo{sec}Down", f"secondo{sec}Up", f"secondo{sec}Down"]
    present = [v for v in staves if var_text(src, v)]
    if len(present) < 3:
        raise RuntimeError(f"missing staves for section {sec!r}: {present}")
    midi = compile_midi(src, present, workdir, name)
    data = midiin.read_midi(midi)
    if len(data["staves"]) != len(present):
        raise RuntimeError(f"{len(data['staves'])} MIDI tracks for {len(present)} staves")
    partial = partial_of(var_text(src, present[0]))
    grid = midiin.bar_grid(data["meters"], data["end"], partial)
    per = {}
    k = 0
    for v, hand in zip(staves, HANDS):
        if v in present:
            per[hand] = midiin.staff_bars(data["staves"][k], grid, data["keys"])
            k += 1
        else:
            per[hand] = [[[Ev(g[1])]] for g in grid]
    key = data["keys"][0][1] if data["keys"] else None
    return grid, per, key, data


def to_tune(grids_per: list, title: str) -> Tune:
    """Join sections, fold repeats, and build the multi-voice tune."""
    tune = Tune(title=title)
    first = True
    for label, (grid, per, key, data) in grids_per:
        if first:
            tune.key = key or tune.key
            tune.meter = grid[0][2]
        keys = midiin.bar_keys(data["staves"], grid)
        has_pick = grid[0][1] < grid[0][2].bar_len
        segs = midiin.fold_repeats(keys, min_len=8, pickup=has_pick)
        start_index = len(tune.bars)

        def add(i, **flags):
            start, length, meter, changed = grid[i]
            tb = TBar(length=length)
            v0 = per["prh"][i]
            tb.melody = v0[0]
            if len(v0) > 1:
                tb.voices["prh2"] = v0[1]
            for h in HANDS[1:]:
                vs = per[h][i]
                tb.voices[h] = vs[0]
                if len(vs) > 1:
                    tb.voices[h + "2"] = vs[1]
            for k2, v in flags.items():
                setattr(tb, k2, v)
            if i == 0 and has_pick:
                tb.pickup = True
            tune.bars.append(tb)
            return tb

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
        sec_first = tune.bars[start_index]
        if not first:
            sec_first.label = label or "Trio"
            if key is not None and key != tune.key:
                sec_first.key = key
            if grid[0][2] != tune.meter:
                sec_first.meter = grid[0][2]
            tune.bars[start_index - 1].double_bar = True
        first = False
    # make sure every bar has the same voice names (rests where a second voice is silent)
    names = []
    for b in tune.bars:
        for n in b.voices:
            if n not in names:
                names.append(n)
    for b in tune.bars:
        for n in names:
            b.voices.setdefault(n, [Ev(b.length)])
    return tune


def main():
    src_root = Path(sys.argv[1])
    dst = Path(__file__).resolve().parent.parent / "library" / "diabelli"
    dst.mkdir(parents=True, exist_ok=True)
    files = sorted(src_root.glob("O149/*/*.ly"), key=lambda p: int(re.findall(r"(\d+)\.ly$", p.name)[0])) \
        + sorted(src_root.glob("O163/*/*.ly"))
    ok = 0
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for path in files:
            src = path.read_text(encoding="utf-8", errors="replace")
            op = "149" if "O149" in str(path) else "163"
            if op == "149":
                num = int(re.findall(r"(\d+)\.ly$", path.name)[0])
                title = f"Melodious Piece No. {num}"
                subtitle = "Melodische Übungsstücke, Op. 149 No. %d" % num
                slug = f"diabelli-op149-{num:02d}"
            else:
                s, mv = re.findall(r"s(\d)-(\d)\.ly$", path.name)[0]
                roman = ["I", "II", "III", "IV"][int(mv) - 1]
                title = f"Sonatina No. {s}: {roman}"
                subtitle = f"Jugendfreuden (Pleasures of Youth), Op. 163 No. {s}"
                slug = f"diabelli-op163-{s}-{mv}"
            secs = []
            for m in re.finditer(r"^\s*primo(\w*?)Up\s*=", src, flags=re.M):
                if m.group(1) not in secs:
                    secs.append(m.group(1))
            try:
                parts = []
                for k, sec in enumerate(secs):
                    parts.append((sec if k else "", section_bars(src, sec, work, f"{slug}-{k}")))
                tune = to_tune(parts, title)
            except Exception as exc:
                print(f"  skipped {path.name}: {type(exc).__name__}: {str(exc)[:200]}")
                continue
            tempo_txt = re.findall(r'piece\s*=\s*"([^"]+)"', src)
            tune.tempo_text = tempo_txt[0].strip().rstrip(".") if tempo_txt else ""
            bpm = re.findall(r"\\tempo\s+(\d+)\s*=\s*(\d+)", src)
            if bpm:
                unit = Fraction(4, int(bpm[0][0]))
                tune.tempo = int(round(int(bpm[0][1]) * float(unit / tune.meter.beat_len)))
            tune.subtitle = subtitle
            tune.composer = "Anton Diabelli (1781–1858)"
            tune.category = "duet"
            tune.tags = ["classical", "original-duet", "diabelli"] + (["dacapo"] if len(secs) > 1 else [])
            tune.source = "Mutopia Project"
            tune.credit = ("Original duet by Anton Diabelli. Source edition: Alberto Simões for the Mutopia Project; "
                           "this engraving is licensed CC BY-SA 3.0.")
            tune.slug = slug
            text = write_abc(tune)
            back = tune_from_abc(parse_abc(text)[0])
            same = len(back.bars) == len(tune.bars) and all(
                a.melody == b.melody and a.voices == b.voices for a, b in zip(tune.bars, back.bars))
            if not same:
                print(f"  skipped {path.name}: round-trip mismatch")
                continue
            (dst / f"{slug}.abc").write_text(text, encoding="utf-8")
            ok += 1
            print(f"  {slug}: {len(tune.bars)} bars, {tune.key.short}, {tune.meter.text}, sections {secs}")
    print(f"imported {ok} of {len(files)}")


if __name__ == "__main__":
    main()
