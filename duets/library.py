"""The tune library: ABC files with a little extra metadata."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional

from .abc import AbcTune, apply_play_order, irregular_bars, parse_abc
from .model import Ev, F, Tune, merge_ties, total
from .theory import Meter

LIBRARY_ROOT = Path(__file__).resolve().parent.parent / "library"


def slugify(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"['’`]", "", t.lower())
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t or "untitled"


def tune_from_abc(abc: AbcTune) -> Tune:
    """Build a Tune from a parsed ABC tune, including extra voices and the
    ``%%duets`` metadata."""
    tune = abc.to_tune()
    main = abc.voice_order[0]
    ref = abc.voices[main]
    for vid in abc.voice_order[1:]:
        bars = abc.voices[vid]
        if len(bars) != len(ref) or any(a.length != b.length for a, b in zip(bars, ref)):
            continue
        for tb, vb in zip(tune.bars, bars):
            tb.voices[vid] = list(vb.events)
    meta = abc.meta
    tune.category = meta.get("category", tune.category)
    if meta.get("tags"):
        tune.tags = [t.strip() for t in meta["tags"].split(",") if t.strip()]
    tune.tune_name = meta.get("tune", "")
    tune.credit = meta.get("credit", "")
    tune.lyricist = meta.get("lyricist", "")
    tune.tempo_text = meta.get("tempo-text", "")
    tune.notes = meta.get("notes", "")
    if meta.get("round"):
        tune.notes = (tune.notes + " round " + meta["round"]).strip()
    if meta.get("year", "").strip().isdigit():
        tune.year = int(meta["year"])
    if meta.get("free-meter", "").lower() in ("yes", "true", "1"):
        tune.free_meter = True
    if meta.get("style"):
        tune.style = meta["style"]
    titles = abc.headers.get("T", [])
    if len(titles) > 1:
        tune.subtitle = titles[1].strip()
    order = abc.header("Y")
    if order:
        apply_play_order(tune, order)
    for b in tune.bars:
        b.melody = merge_ties(b.melody)
        b.voices = {k: merge_ties(v) for k, v in b.voices.items()}
    tune.slug = meta.get("slug") or slugify(tune.title)
    _normalise_meter(tune)
    return tune


_COMMON_METERS = {(4, 4), (3, 4), (2, 4), (6, 8), (2, 2), (3, 2), (6, 4), (9, 8), (12, 8), (3, 8), (4, 2), (8, 4)}


def _normalise_meter(tune: Tune) -> None:
    """Free-rhythm hymns arrive with whatever 'meter' their commonest bar
    length suggests (23/8 ...).  Give them a plain beat to count in, and keep
    hymn tempos within what people actually play."""
    m = tune.meter
    if tune.free_meter and (m.num, m.den) not in _COMMON_METERS:
        new = Meter(4, 2) if m.den <= 2 else Meter(4, 4)
        if tune.tempo:
            tune.tempo = int(round(tune.tempo * float(m.beat_len / new.beat_len)))
        tune.meter = new
    if tune.category == "hymn" and tune.tempo:
        while tune.tempo > 200:
            tune.tempo //= 2
        tune.tempo = min(tune.tempo, 144)


def load_file(path: Path) -> list:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    out = []
    for abc in parse_abc(text):
        try:
            t = tune_from_abc(abc)
        except Exception as exc:  # a broken tune should not take the library down
            print(f"warning: {path}: {abc.title}: {exc}")
            continue
        out.append(t)
    return out


def load_library(root: Optional[Path] = None) -> list:
    """Load every ``*.abc`` under the library folder."""
    root = Path(root or LIBRARY_ROOT)
    tunes = []
    seen = set()
    for path in sorted(root.rglob("*.abc")):
        for t in load_file(path):
            coll = path.parent.name if path.parent != root else ""
            t.collection = coll
            base = t.slug
            k = 2
            while t.slug in seen:
                t.slug = f"{base}-{k}"
                k += 1
            seen.add(t.slug)
            t.path = str(path)
            tunes.append(t)
    return tunes


def validate(tune: Tune) -> list:
    """Problems that make a tune unsuitable for arranging."""
    problems = []
    if not tune.bars:
        return ["empty"]
    for i, b in enumerate(tune.bars):
        if total(b.melody) != b.length:
            problems.append(f"bar {i + 1}: melody length mismatch")
        for name, v in b.voices.items():
            if total(v) != b.length:
                problems.append(f"bar {i + 1}: voice {name} length mismatch")
    if not tune.free_meter:
        irr = irregular_bars(tune.bars, tune.meter)
        if irr:
            problems.append("irregular bars: " + ", ".join(str(i + 1) for i in irr[:6]))
    notes = [p for p in tune.melody_pitches()]
    notes += [p for b in tune.bars for v in b.voices.values() for e in v for p in e.pitches]
    if len(notes) < 8:
        problems.append("too few notes")
    return problems


_SMALL = {"a", "an", "the", "and", "but", "or", "nor", "for", "of", "on", "in", "to", "at", "by", "with",
          "from", "as", "o'er", "unto", "into", "upon"}


def title_case(text: str) -> str:
    """Hymnal-style capitalisation: small words stay lower case inside a title."""
    words = text.split()
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        if 0 < i < len(words) - 1 and lw in _SMALL:
            out.append(lw)
        elif w.isupper() and len(w) > 1:
            out.append(w.capitalize())
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)
