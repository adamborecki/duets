"""Engraving decisions and the PDF build for one piece.

* clefs and 8va brackets chosen to keep notes near the staff,
* line breaks planned once and shared by both players' parts so that the
  facing pages match system for system and bar number for bar number,
* the four page layouts (see ``LAYOUTS``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Optional

from . import render
from .lily import PART_HANDS, PART_NAME, Spec, dots, render_ly
from .model import HANDS, F, Piece, onsets

# ---------------------------------------------------------------------------
# clefs and ottava
# ---------------------------------------------------------------------------


def ledger_lines(d: int, clef: str) -> int:
    """Ledger lines needed for diatonic number ``d`` in a clef."""
    if clef == "treble":
        bottom, top = 30, 38        # E4 .. F5
    else:
        bottom, top = 18, 26        # G2 .. A3
    if d < bottom - 1:
        return (bottom - d) // 2
    if d > top + 1:
        return (d - top) // 2
    return 0


def _hand_notes(piece: Piece, hand: str, lo: int, hi: int) -> list:
    out = []
    for b in piece.bars[lo:hi]:
        for v in b.hands.get(hand, []):
            for e in v:
                for p in e.pitches:
                    out.append(p)
    return out


def _sections(piece: Piece) -> list:
    """Bar ranges between rehearsal marks / double bars."""
    cuts = [0]
    for i, b in enumerate(piece.bars):
        if i > 0 and (b.mark or piece.bars[i - 1].double_bar or b.key is not None or b.meter is not None):
            if i - cuts[-1] >= 4:
                cuts.append(i)
    cuts.append(len(piece.bars))
    return [(cuts[k], cuts[k + 1]) for k in range(len(cuts) - 1)]


def plan_clefs(piece: Piece) -> None:
    """Choose a clef per hand and section, and 8va where the Primo climbs."""
    n = len(piece.bars)
    from .lily import hands_of
    for hand in hands_of(piece):
        default = "treble" if hand in ("prh", "plh") else "bass"
        clefs = [default] * n
        prev = None
        for (a, b) in _sections(piece):
            notes = _hand_notes(piece, hand, a, b)
            if not notes:
                choice = prev or default
            else:
                cost = {}
                for c in ("treble", "bass"):
                    cost[c] = sum(ledger_lines(p.d, c) ** 1.3 for p in notes) / len(notes)
                if hand == "prh":
                    choice = "treble"
                elif hand in ("slh", "ped") and not (hand == "slh" and "ped" in piece.clefs):
                    choice = "bass"
                else:
                    bias = 0.25
                    stay = prev or default
                    other = "bass" if stay == "treble" else "treble"
                    choice = other if cost[other] + bias < cost[stay] else stay
            for i in range(a, b):
                clefs[i] = choice
            prev = choice
        piece.clefs[hand] = clefs
    # ottava for treble-clef hands that sit high
    for hand in ("prh", "plh"):
        ott = [0] * n
        for (a, b) in _sections(piece):
            if piece.clefs[hand][a] != "treble":
                continue
            notes = _hand_notes(piece, hand, a, b)
            if not notes:
                continue
            ms = sorted(p.midi for p in notes)
            hi = ms[-1]
            p80 = ms[int(len(ms) * 0.8)]
            lo = ms[0]
            # high enough to be awkward, and low notes would still be fine an octave down
            if (hi >= 91 or p80 >= 86) and lo >= 71:
                for i in range(a, b):
                    ott[i] = 1
        piece.ottava[hand] = ott


# ---------------------------------------------------------------------------
# line breaks
# ---------------------------------------------------------------------------
def bar_width(piece: Piece, i: int, parts=("p", "s")) -> float:
    """Rough horizontal space a bar needs, in staff spaces."""
    b = piece.bars[i]
    widest = 0.0
    for part in parts:
        cols = set()
        acc = 0
        shortest = F(4)
        for h in PART_HANDS[part]:
            for v in b.hands.get(h, []):
                for off, e in onsets(v):
                    cols.add(off)
                    if not e.is_rest:
                        shortest = min(shortest, e.dur)
                    acc += sum(1 for p in e.pitches if p.alter != 0)
        n = max(len(cols), 1)
        w = 2.4 + n * 2.9 + min(acc, 6) * 0.35
        if shortest <= F(1, 4):
            w += n * 0.35
        widest = max(widest, w)
    chords = len(b.chords)
    widest = max(widest, 2.0 + chords * 5.5)
    if b.start_repeat or b.end_repeat:
        widest += 1.2
    if b.pickup:
        widest = max(3.5, widest * 0.9)
    widest = max(widest, 6.5 * float(b.length) / float(piece.meter.bar_len) if not b.pickup else widest)
    return widest


def plan_breaks(piece: Piece, capacity: float, parts=("p", "s"), max_systems: Optional[int] = None) -> list:
    """Split the bars into systems.  Returns a list of bar indices *after which*
    a line break occurs.  Uses a least-raggedness dynamic programme and prefers
    breaking at section boundaries and after even-numbered bars."""
    n = len(piece.bars)
    w = [bar_width(piece, i, parts) for i in range(n)]
    overhead = 9.0
    cap = capacity - overhead
    INF = float("inf")
    # count "real" bars from each section start for phrase-aware penalties
    since = []
    k = 0
    for i, b in enumerate(piece.bars):
        if b.mark or (i > 0 and (piece.bars[i - 1].double_bar or piece.bars[i - 1].end_repeat)):
            k = 0
        if not b.pickup:
            k += 1
        since.append(k)

    def break_penalty(j: int) -> float:
        """Penalty for ending a system after bar j."""
        if j == n - 1:
            return 0.0
        b, nxt = piece.bars[j], piece.bars[j + 1]
        if b.pickup:
            return 50.0                       # never strand an upbeat at a line end
        if nxt.mark or b.double_bar or b.end_repeat:
            return -3.0
        if nxt.volta and b.volta and nxt.volta != b.volta:
            return 4.0
        p = 0.0
        if since[j] % 4 == 0:
            p -= 1.5
        elif since[j] % 2 == 1:
            p += 2.5
        return p

    best = [INF] * (n + 1)
    prev = [-1] * (n + 1)
    best[0] = 0.0
    for i in range(n):
        if best[i] == INF:
            continue
        width = 0.0
        for j in range(i, n):
            width += w[j]
            if width > cap and j > i:
                break
            # a rehearsal mark must start a system (it would sit on the chord names otherwise)
            if j > i and piece.bars[j].mark and not all(b.pickup for b in piece.bars[i:j]):
                break
            slack = max(cap - width, 0.0) / cap
            last = j == n - 1
            cost = (slack ** 2) * (2.0 if last else 10.0) + 1.0 + break_penalty(j) * 0.25
            if width > cap:
                cost += 5.0
            if best[i] + cost < best[j + 1]:
                best[j + 1] = best[i] + cost
                prev[j + 1] = i
    cuts = []
    j = n
    while j > 0:
        i = prev[j]
        if i < 0:
            i = j - 1
        if j < n:
            cuts.append(j - 1)
        j = i
    return sorted(cuts)


def systems_from_breaks(n_bars: int, breaks: list) -> list:
    out = []
    start = 0
    for b in sorted(breaks):
        out.append((start, b + 1))
        start = b + 1
    out.append((start, n_bars))
    return out


# ---------------------------------------------------------------------------
# layouts
# ---------------------------------------------------------------------------
PAPERS = {"letter": (215.9, 279.4), "a4": (210.0, 297.0)}


@dataclass
class LayoutPlan:
    staff_size: float
    breaks: list
    page_breaks: list
    pages: int


def _capacity(width_mm: float, margins_lr: float, staff_size: float) -> float:
    ss = staff_size * 0.3515 / 4.0          # one staff space in mm
    return (width_mm - margins_lr) / ss


def plan_part_layout(piece: Piece, paper: tuple, sizes=(22.0, 20.5, 19.0, 17.5, 16.5), margins=(10, 10, 12, 12),
                     first_page_systems=None) -> LayoutPlan:
    """Find a staff size and break plan that puts a part on as few pages as possible."""
    w, h = paper
    top, bottom, left, right = margins
    n = len(piece.bars)
    best = None
    for size in sizes:
        ss = size * 0.3515 / 4.0
        cap = _capacity(w, left + right, size)
        breaks = plan_breaks(piece, cap)
        systems = len(breaks) + 1
        sys_h = 31.0 * ss          # grand staff + chord names + breathing room
        if any("ped" in b.hands for b in piece.bars):
            sys_h = 44.0 * ss      # an organ part has a third staff
        title_h = 30.0
        usable = h - top - bottom
        per_first = max(1, int((usable - title_h) // sys_h))
        per_other = max(1, int(usable // sys_h))
        if systems <= per_first:
            pages = 1
        else:
            pages = 1 + math.ceil((systems - per_first) / per_other)
        plan = LayoutPlan(size, breaks, [], pages)
        # page breaks after the last system of each page
        sysl = systems_from_breaks(n, breaks)
        pbs = []
        if pages > 1:
            # spread systems evenly over the pages
            counts = _spread(systems, pages, per_first, per_other)
            k = 0
            for c in counts[:-1]:
                k += c
                pbs.append(sysl[k - 1][1] - 1)
        plan.page_breaks = pbs
        if best is None or pages < best.pages:
            best = plan
        if pages == 1:
            return plan
    return best


def _spread(systems: int, pages: int, per_first: int, per_other: int) -> list:
    counts = [0] * pages
    caps = [per_first] + [per_other] * (pages - 1)
    # fill evenly but respect capacities
    base = systems // pages
    counts = [min(base, c) for c in caps]
    rem = systems - sum(counts)
    i = pages - 1
    guard = 0
    while rem > 0 and guard < 1000:
        guard += 1
        if counts[i] < caps[i]:
            counts[i] += 1
            rem -= 1
        i = (i - 1) % pages
    return counts


def plan_score_layout(piece: Piece, paper: tuple, size: float, margins=(10, 10, 12, 12)) -> LayoutPlan:
    w, h = paper
    cap = _capacity(w, margins[2] + margins[3] + 14, size)
    breaks = plan_breaks(piece, cap)
    return LayoutPlan(size, breaks, [], 0)


def level_label(piece: Piece, part: str) -> str:
    lv = piece.levels.get(part)
    from .lily import part_name
    name = part_name(piece, part).upper()
    return f"{name}   {dots(lv)}" if lv else name


GENERATED_NOTE = "Duet arrangement generated by “duets” — free to copy, share and perform."
ENGRAVED_NOTE = "Engraved with “duets”."


def note_for(piece: Piece) -> str:
    return ENGRAVED_NOTE if piece.category in ("duet", "piano") else GENERATED_NOTE


def footer_text(piece: Piece) -> str:
    return piece.credit or ""


SCREEN_HALF = (203.2, 254.0)      # two of these side by side make a 16:10 screen
SCREEN_FULL = (406.4, 254.0)


def _labels(piece: Piece) -> str:
    return f"{level_label(piece, 'p')}      {level_label(piece, 's')}"


def _part_params(layout: str, pw: tuple) -> tuple:
    if layout == "facing":
        return pw, (22.0, 20.5, 19.0, 17.5, 16.5), (10, 10, 12, 12)
    return SCREEN_HALF, (25.0, 23.0, 21.0), (8, 8, 9, 9)


def _part_spec(piece: Piece, part: str, paper_size: tuple, plan: LayoutPlan, margins: tuple) -> Spec:
    return Spec(parts=(part,), paper=paper_size, staff_size=plan.staff_size, margins=margins,
                breaks=set(plan.breaks), page_breaks=set(plan.page_breaks),
                label=level_label(piece, part), footer=footer_text(piece), footer2=note_for(piece))


def _score_spec(piece: Piece, layout: str, pw: tuple, midi: bool = False) -> Spec:
    if layout == "score":
        paper_size, size, margins = pw, 17.5, (10, 10, 12, 12)
    elif layout == "screen-score":
        paper_size, size, margins = SCREEN_FULL, 23.0, (8, 8, 10, 10)
    else:
        raise ValueError(f"unknown layout {layout!r}")
    plan = plan_score_layout(piece, paper_size, size, margins=margins)
    return Spec(parts=("p", "s"), paper=paper_size, staff_size=size, margins=margins, breaks=set(plan.breaks),
                auto_pages=True, label=_labels(piece), footer=footer_text(piece), footer2=note_for(piece),
                midi=midi)


def first_texts(piece: Piece, layout: str, paper: str = "letter") -> list:
    """The LilyPond sources ``render_layout`` will ask for first - so that a
    whole batch of pieces can be compiled in one LilyPond run beforehand."""
    if not piece.clefs:
        plan_clefs(piece)
    pw = PAPERS[paper]
    if layout in ("facing", "screen"):
        paper_size, sizes, margins = _part_params(layout, pw)
        plan = plan_part_layout(piece, paper_size, sizes=sizes, margins=margins)
        return [render_ly(piece, _part_spec(piece, part, paper_size, plan, margins)) for part in ("s", "p")]
    return [render_ly(piece, _score_spec(piece, layout, pw))]


def render_layout(piece: Piece, layout: str, workdir: Path, stem: str, paper: str = "letter",
                  midi_out: Optional[Path] = None) -> dict:
    """Render one layout of a piece into ``workdir`` (fonts not yet embedded).

    Returns {'path', 'pages', 'warnings', 'staff_size'}.  For the two-part
    layouts the two parts are compiled with identical line and page breaks
    and then interleaved ('facing') or placed side by side ('screen').
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    if not piece.clefs:
        plan_clefs(piece)
    footer = footer_text(piece)
    pw = PAPERS[paper]
    warnings: list = []
    out = workdir / f"{stem}.{layout}.pdf"

    if layout in ("facing", "screen"):
        paper_size, sizes, margins = _part_params(layout, pw)
        plan = plan_part_layout(piece, paper_size, sizes=sizes, margins=margins)
        paths = {}
        attempt = 0
        while True:
            pages = {}
            warn = []
            for part in ("s", "p"):
                spec = _part_spec(piece, part, paper_size, plan, margins)
                path = workdir / f"{stem}.{layout}.{part}.pdf"
                info = render.compile_ly(render_ly(piece, spec), path)
                pages[part] = info["pages"]
                paths[part] = path
                warn += [f"{layout}/{part}: {w}" for w in info["warnings"]]
            squeezed = any("compress" in w for w in warn)
            if (pages["s"] == pages["p"] == plan.pages and not squeezed) or attempt >= 4:
                warnings += warn
                break
            attempt += 1
            smaller = [x for x in sizes if x < plan.staff_size]
            if smaller and (max(pages.values()) > plan.pages or squeezed):
                plan2 = plan_part_layout(piece, paper_size, sizes=tuple(smaller), margins=margins)
                if plan2.pages <= plan.pages:
                    plan = plan2
                    continue
            plan.pages = max(max(pages.values()), plan.pages + (1 if squeezed else 0))
            n_sys = len(plan.breaks) + 1
            sysl = systems_from_breaks(len(piece.bars), plan.breaks)
            per = math.ceil(n_sys / plan.pages)
            plan.page_breaks = [sysl[k - 1][1] - 1 for k in range(per, n_sys, per)]
        if layout == "facing":
            n = render.interleave(paths["s"], paths["p"], out)
        else:
            n = render.two_up(paths["s"], paths["p"], out)
        for pth in paths.values():
            pth.unlink(missing_ok=True)
        return {"path": out, "pages": n, "warnings": warnings, "staff_size": plan.staff_size,
                "page_breaks": sorted(plan.page_breaks)}

    spec = _score_spec(piece, layout, pw, midi=midi_out is not None)
    size = spec.staff_size
    info = render.compile_ly(render_ly(piece, spec), out, midi_out=midi_out)
    warnings += [f"{layout}: {w}" for w in info["warnings"]]
    return {"path": out, "pages": info["pages"], "warnings": warnings, "staff_size": size}


LAYOUTS = ("facing", "score", "screen", "screen-score")
LAYOUT_HELP = {
    "facing": "print: Secondo on left-hand pages, Primo on right-hand pages, systems aligned",
    "score": "print: both parts stacked in one four-stave score",
    "screen": "laptop/tablet: Secondo and Primo side by side on one 16:10 page",
    "screen-score": "laptop/tablet: stacked four-stave score on a 16:10 page",
}


def build_piece(piece: Piece, outdir: Path, stem: str, layouts=LAYOUTS, paper: str = "letter",
                midi: bool = True) -> dict:
    """Render a piece in the requested layouts as finished PDFs (+ MIDI)."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    tmp = outdir / ".work"
    result: dict = {"info": {"warnings": []}}
    midi_path = outdir / f"{stem}.mid" if midi else None
    want_midi = midi
    for layout in layouts:
        mo = midi_path if (want_midi and layout in ("score", "screen-score")) else None
        r = render_layout(piece, layout, tmp, stem, paper=paper, midi_out=mo)
        if mo is not None:
            want_midi = False
            result["midi"] = midi_path
        final = outdir / f"{stem}.{layout}.pdf"
        render.finalize(r["path"], final)
        result[layout] = final
        result["info"]["warnings"] += r["warnings"]
        result["info"][f"{layout}_pages"] = r["pages"]
    if want_midi:
        # no score layout requested: compile one just for the MIDI
        r = render_layout(piece, "score", tmp, stem, paper=paper, midi_out=midi_path)
        result["midi"] = midi_path
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    return result
