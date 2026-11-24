#!/usr/bin/env python3
"""Import the Open Hymnal Project (public-domain hymns with four-part
settings) into ``library/hymns``.

    python tools/import_openhymnal.py /path/to/openhymnal/Complete

Source: https://github.com/mzealey/openhymnal (mirror of openhymnal.org).
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from duets import harmony as H                                     # noqa: E402
from duets.abc import AbcBar, guess_meter, irregular_bars, parse_abc  # noqa: E402
from duets.abcwrite import write_abc                               # noqa: E402
from duets.library import slugify, title_case, tune_from_abc, validate  # noqa: E402
from duets.model import Ev, F, TBar, Tune, merge_ties, total       # noqa: E402
from duets.theory import Meter                                     # noqa: E402

SEASON_TAGS = {
    "ADVENT": "advent", "CHRISTMAS": "christmas", "EPIPHANY": "epiphany", "LENT": "lent",
    "PALM SUNDAY": "palm-sunday", "GOOD THURSDAY": "maundy-thursday", "GOOD FRIDAY": "good-friday",
    "EASTER": "easter", "ASCENSION": "ascension", "PENTECOST": "pentecost", "TRINITY": "trinity",
    "REFORMATION": "reformation", "THANKSGIVING": "thanksgiving", "END TIMES": "end-times",
    "TRANSFIGURATION": "transfiguration", "MORNING": "morning", "EVENING": "evening",
    "PRAISE": "praise", "TRUST": "trust", "REDEEMER": "redeemer", "LORD'S SUPPER": "communion",
    "BAPTISMAL LIFE": "baptism", "COMMUNION OF SAINTS": "church", "FUNERAL": "funeral",
    "OPENING SONGS": "opening", "CLOSING SONGS": "closing", "CROSS AND COMFORT": "comfort",
    "JUSTIFICATION": "justification", "WORD OF GOD": "word", "PRAYER": "prayer",
    "MISSIONS": "missions", "CONSECRATION": "consecration", "HEAVEN": "heaven",
    "CONFESSION/ABSOLUTION": "confession", "NEW OBEDIENCE": "obedience",
    "CHRISTIAN HOME": "home", "STEWARDSHIP": "stewardship", "LIFE": "life",
}


def parse_staves(directive: str, order: list) -> list:
    """``staves (A B) | (C D)`` -> [[A, B], [C, D]]"""
    d = re.sub(r"^(staves|score)\s*", "", directive.strip())
    d = d.replace("{", " ").replace("}", " ").replace("[", " ").replace("]", " ")
    staves = []
    for m in re.finditer(r"\(([^)]*)\)|([A-Za-z0-9_]+)", d):
        if m.group(1) is not None:
            names = m.group(1).split()
        else:
            names = [m.group(2)]
        names = [n for n in names if n in order]
        if names:
            staves.append(names)
    if not staves:
        staves = [[v] for v in order]
    return staves


def flatten(bars) -> list:
    out = []
    for b in bars:
        out.extend(b.events)
    return out


def rebar(events: list, lengths: list):
    """Cut a flat event list into bars of the given lengths (splitting with ties)."""
    out = []
    it = iter(events)
    cur = None
    for L in lengths:
        bar = []
        need = L
        while need > 0:
            if cur is None:
                cur = next(it, None)
                if cur is None:
                    return None
            if cur.dur <= need:
                bar.append(cur)
                need -= cur.dur
                cur = None
            else:
                bar.append(Ev(need, cur.pitches, bool(cur.pitches), cur.marks))
                cur = Ev(cur.dur - need, cur.pitches, cur.tie, ())
                need = F(0)
        out.append(bar)
    if cur is not None or next(it, None) is not None:
        return None
    return out


def top_line(events: list) -> list:
    return [Ev(e.dur, (e.top,), e.tie, e.marks) if e.pitches else Ev(e.dur) for e in events]


def rest_line(events: list) -> list:
    """Everything except the top note of each event."""
    out = []
    for e in events:
        if len(e.pitches) > 1:
            out.append(Ev(e.dur, tuple(sorted(e.pitches, key=lambda p: p.midi)[:-1]), e.tie, ()))
        else:
            out.append(Ev(e.dur))
    return out


def bottom_line(events: list) -> list:
    return [Ev(e.dur, (e.bottom,), e.tie, ()) if e.pitches else Ev(e.dur) for e in events]


def above_bottom(events: list) -> list:
    out = []
    for e in events:
        if len(e.pitches) > 1:
            out.append(Ev(e.dur, tuple(sorted(e.pitches, key=lambda p: p.midi)[1:]), e.tie, ()))
        else:
            out.append(Ev(e.dur))
    return out


def merge_overlay(bar: AbcBar) -> list:
    """Fold a voice overlay into the main events when the rhythms line up."""
    ev = list(bar.events)
    for ov in bar.overlays:
        if total(ov) != total(ev):
            continue
        # index main events by onset
        pos = {}
        t = F(0)
        for k, e in enumerate(ev):
            pos[t] = k
            t += e.dur
        t = F(0)
        for e in ov:
            if e.pitches and t in pos:
                k = pos[t]
                m = ev[k]
                if m.dur == e.dur or not m.pitches:
                    ps = tuple(sorted(set(m.pitches + e.pitches), key=lambda p: (p.midi, p.d)))
                    ev[k] = Ev(max(m.dur, e.dur) if m.pitches else e.dur, ps, m.tie, m.marks) \
                        if (m.pitches or m.dur == e.dur) else m
            t += e.dur
    return ev


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" .;,")


def import_one(path: Path):
    raw = path.read_bytes().decode("cp1252", errors="replace")
    abcs = parse_abc(raw)
    if not abcs:
        return None, "no tune"
    abc = abcs[0]
    credit_all = " ".join(abc.headers.get("C", []))
    m = re.search(r"copyright:\s*([^.]*)", credit_all, flags=re.I)
    cr = (m.group(1) if m else "").lower()
    if "public domain" not in cr:
        return None, f"not marked public domain ({cr!r})"
    order = abc.voice_order
    staves = parse_staves(abc.staves, order)
    # fold overlays
    for vid in order:
        for b in abc.voices[vid]:
            if b.overlays:
                b.events = merge_overlay(b)
    ref_id = staves[0][0]
    ref = abc.voices[ref_id]
    lengths = [b.length for b in ref]
    # majority vote on the bar structure
    structs = Counter(tuple(b.length for b in abc.voices[v]) for v in order)
    common = structs.most_common(1)[0][0]
    if tuple(lengths) != common:
        for v in order:
            if tuple(b.length for b in abc.voices[v]) == common:
                ref = abc.voices[v]
                lengths = list(common)
                break
    lines = {}
    for vid in order:
        bars = abc.voices[vid]
        if [b.length for b in bars] == lengths:
            lines[vid] = [list(b.events) for b in bars]
        else:
            rb = rebar(flatten(bars), lengths)
            if rb is None:
                return None, f"voice {vid} does not line up"
            lines[vid] = rb
    top_staff = staves[0]
    low_staff = staves[-1] if len(staves) > 1 else None
    mid_staff = staves[1] if len(staves) > 2 else None
    n = len(lengths)

    def voice(vid, fn=None):
        return [fn(lines[vid][i]) if fn else lines[vid][i] for i in range(n)]

    S = voice(top_staff[0], top_line)
    if len(top_staff) >= 2:
        A = voice(top_staff[1])
    elif mid_staff is not None:
        A = voice(mid_staff[0])
    else:
        A = voice(top_staff[0], rest_line)
    if low_staff is None:
        return None, "single staff"
    if len(low_staff) >= 2:
        T = voice(low_staff[0])
        B = voice(low_staff[-1], bottom_line)
    else:
        T = voice(low_staff[0], above_bottom)
        B = voice(low_staff[0], bottom_line)

    meter = abc.meter
    free = abc.free_meter
    common_len = Counter(lengths).most_common(1)[0][0]
    if free:
        meter = guess_meter(common_len)
    tune = Tune(title=title_case(clean(abc.title)), key=abc.key, meter=meter)
    for i in range(n):
        rb = ref[i]
        tb = TBar(length=lengths[i], melody=merge_ties(S[i]))
        tb.voices = {"A": merge_ties(A[i]), "T": merge_ties(T[i]), "B": merge_ties(B[i])}
        tb.start_repeat, tb.end_repeat, tb.volta = rb.start_repeat, rb.end_repeat, rb.volta
        tb.double_bar = rb.double_bar and i < n - 1
        if rb.meter is not None and i > 0:
            tb.meter = rb.meter
        elif rb.meter is not None:
            tune.meter = meter = rb.meter
        tune.bars.append(tb)
    # pickups
    nominal = meter.bar_len
    for i, tb in enumerate(tune.bars):
        if tb.meter is not None:
            nominal = tb.meter.bar_len
        if tb.length < nominal:
            if i == 0:
                tb.pickup = True
            else:
                prev = tune.bars[i - 1]
                if prev.length < nominal and prev.length + tb.length == nominal and not prev.pickup:
                    tb.pickup = True
    irr = irregular_bars(tune.bars, meter)
    tune.free_meter = free or len(irr) > 0
    intro = [i for i, b in enumerate(ref) if b.intro_start]
    intro_e = [i for i, b in enumerate(ref) if b.intro_end]
    if abc.tempo:
        unit = abc.tempo_unit or meter.beat_len
        tune.tempo = int(round(abc.tempo * float(unit / meter.beat_len)))
    # metadata
    music = re.search(r"Music:\s*(.*?)(?=Setting:|copyright:|Words:|$)", credit_all, flags=re.I)
    setting = re.search(r"Setting:\s*(.*?)(?=copyright:|Words:|Music:|$)", credit_all, flags=re.I)
    words = re.search(r"Words:\s*(.*?)(?=Music:|Setting:|copyright:|$)", credit_all, flags=re.I)
    music_t = clean(music.group(1)) if music else ""
    tn = re.search(r"['\"]([^'\"]+)['\"]", music_t)
    tune_name = clean(tn.group(1)) if tn else ""
    if not tune_name:
        stem = path.stem
        if "-" in stem:
            tune_name = stem.split("-", 1)[1].replace("_", " ")
    composer = clean(re.sub(r"['\"][^'\"]+['\"]", "", music_t, count=1)) if music_t else ""
    composer = re.sub(r"^(from|by)\s+", "", composer, flags=re.I)
    tune.tune_name = tune_name.upper()
    tune.subtitle = tune.tune_name
    tune.composer = composer or abc.comments.get("OHCOMPOSER", "")
    tune.lyricist = clean(words.group(1)) if words else ""
    setting_t = clean(setting.group(1)) if setting else ""
    tune.category = "hymn"
    tags = []
    cat = abc.comments.get("OHCATEGORY", "").strip().upper()
    if cat in SEASON_TAGS:
        tags.append(SEASON_TAGS[cat])
    tune.tags = tags
    tune.source = "Open Hymnal Project"
    tune.credit = "Tune and setting: public domain" + (f" ({setting_t})" if setting_t else "") \
        + ", via the Open Hymnal Project."
    tune.style = "chorale"
    tune.slug = slugify(tune.title)
    yrs = [int(y) for y in re.findall(r"\b(1[0-9]{3})\b", music_t)]
    if yrs:
        tune.year = min(yrs)
    if intro and intro_e:
        tune.notes = f"intro {intro[0] + 1}-{intro_e[-1] + 1}"
    H.infer_chords(tune)
    problems = validate(tune)
    if problems:
        return None, "; ".join(problems[:3])
    return tune, ""


def main():
    src = Path(sys.argv[1])
    dst = Path(__file__).resolve().parent.parent / "library" / "hymns"
    dst.mkdir(parents=True, exist_ok=True)
    ok = 0
    skipped = []
    seen = set()
    for path in sorted(src.glob("*/*.abc")):
        try:
            tune, why = import_one(path)
        except Exception as exc:
            tune, why = None, f"{type(exc).__name__}: {exc}"
        if tune is None:
            skipped.append((path.stem, why))
            continue
        slug = tune.slug
        k = 2
        while slug in seen:
            slug = f"{tune.slug}-{k}"
            k += 1
        seen.add(slug)
        tune.slug = slug
        text = write_abc(tune)
        # verify the round trip before trusting the file
        back = tune_from_abc(parse_abc(text)[0])
        same = len(back.bars) == len(tune.bars) and all(
            a.melody == b.melody and a.voices == b.voices and a.chords == b.chords
            for a, b in zip(tune.bars, back.bars))
        if not same:
            skipped.append((path.stem, "round-trip mismatch"))
            continue
        (dst / f"{slug}.abc").write_text(text, encoding="utf-8")
        ok += 1
    print(f"imported {ok}, skipped {len(skipped)}")
    for name, why in skipped:
        print(f"  skipped {name}: {why}")


if __name__ == "__main__":
    main()
