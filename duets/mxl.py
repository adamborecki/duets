"""A small MusicXML lead-sheet reader (melody, chord symbols, repeats).

Reads compressed ``.mxl`` or plain ``.xml``/``.musicxml`` files into the
lead-sheet model.  Only the first part and its first voice are used, which is
what a lead sheet is.
"""
from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from typing import Optional

from .model import Ev, F, TBar, Tune, merge_ties, total
from .theory import STEP_NAMES, Chord, Key, Meter, Pitch, pitch_from_lof

_KIND = {
    "major": "", "minor": "m", "dominant": "7", "major-seventh": "maj7", "minor-seventh": "m7",
    "diminished": "dim", "augmented": "aug", "half-diminished": "m7b5", "diminished-seventh": "dim7",
    "major-sixth": "6", "minor-sixth": "m6", "dominant-ninth": "9", "major-ninth": "maj9",
    "minor-ninth": "m9", "suspended-fourth": "sus4", "suspended-second": "sus2",
    "major-minor": "mmaj7", "minor-major": "mmaj7", "dominant-11th": "11", "dominant-13th": "13",
    "minor-11th": "m11", "minor-13th": "m9", "augmented-seventh": "aug7", "augmented-ninth": "aug7",
    "power": "5", "maj69": "69", "major-11th": "maj9", "major-13th": "maj9", "other": "",
}


def _read_xml(path: Path) -> ET.Element:
    path = Path(path)
    if path.suffix.lower() == ".mxl":
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith((".xml", ".musicxml")) and "META-INF" not in n]
            data = z.read(names[0])
    else:
        data = path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    text = re.sub(r"<!DOCTYPE[^>]*>", "", text, count=1, flags=re.S)
    return ET.fromstring(text)


def _harmony(el) -> Optional[Chord]:
    root = el.find("root")
    if root is None:
        return None
    step = root.findtext("root-step")
    if not step:
        return None
    alter = int(float(root.findtext("root-alter") or 0))
    rp = Pitch.of(STEP_NAMES.index(step.strip().upper()), alter, 4)
    kind_txt = (el.findtext("kind") or "major").strip()
    if kind_txt == "none":
        return None
    kind = _KIND.get(kind_txt, "")
    degs = []
    for d in el.findall("degree"):
        try:
            degs.append((int(d.findtext("degree-value")), int(float(d.findtext("degree-alter") or 0)),
                         (d.findtext("degree-type") or "add").strip()))
        except (TypeError, ValueError):
            pass
    for val, alt, typ in degs:
        if val == 9 and alt == -1 and kind in ("7", "9"):
            kind = "7b9"
        elif val == 9 and alt == 1 and kind in ("7", "9"):
            kind = "7#9"
        elif val == 5 and alt == 1 and kind in ("7", "9"):
            kind = "aug7"
        elif val == 5 and alt == -1 and kind == "7":
            kind = "7b5"
        elif val == 5 and alt == -1 and kind == "m7":
            kind = "m7b5"
        elif val == 5 and alt == 1 and kind == "":
            kind = "aug"
        elif val == 9 and alt == 0 and kind == "" and typ == "add":
            kind = "add9"
        elif val == 9 and alt == 0 and kind == "7":
            kind = "9"
        elif val == 7 and alt == 0 and kind == "sus4":
            kind = "7sus4"
        elif val == 6 and alt == 0 and kind == "":
            kind = "6"
        elif val == 6 and alt == 0 and kind == "m":
            kind = "m6"
    bass = None
    b = el.find("bass")
    if b is not None and b.findtext("bass-step"):
        bass = Pitch.of(STEP_NAMES.index(b.findtext("bass-step").strip().upper()),
                        int(float(b.findtext("bass-alter") or 0)), 4)
        if bass.same_class(rp):
            bass = None
    return Chord(rp, kind, bass)


def read_musicxml(path: Path) -> Tune:
    root = _read_xml(path)
    title = (root.findtext("movement-title") or root.findtext("work/work-title") or Path(path).stem).strip()
    tune = _tune_from_root(root, title)
    composers = [c.text.strip() for c in root.findall("identification/creator") if c.text]
    tune.composer = ", ".join(composers)
    return tune


def _tune_from_root(root: ET.Element, title: str) -> Tune:
    part = root.find("part")
    if part is None:
        raise ValueError("no part")
    tune = Tune(title=title)
    divisions = 1
    key_set = False
    meter = Meter(4, 4)
    first = True
    main_voice = None
    for mi, measure in enumerate(part.findall("measure")):
        events: list = []
        chords: list = []
        t = F(0)
        bar = TBar(length=F(0))
        pending_tie_from_prev = False
        for el in measure:
            tag = el.tag
            if tag == "attributes":
                d = el.findtext("divisions")
                if d:
                    divisions = int(d)
                k = el.find("key")
                if k is not None and k.findtext("fifths") is not None:
                    fifths = int(k.findtext("fifths"))
                    mode = (k.findtext("mode") or "major").strip().lower()
                    mode = mode if mode in ("major", "minor", "dorian", "mixolydian") else "major"
                    from .theory import MODE_LOF
                    tonic = pitch_from_lof(fifths - MODE_LOF[mode])
                    key = Key(tonic, mode)
                    if not key_set:
                        tune.key = key
                        key_set = True
                    elif key != tune.key and not events:
                        bar.key = key
                tm = el.find("time")
                if tm is not None and tm.findtext("beats"):
                    try:
                        m2 = Meter(int(tm.findtext("beats")), int(tm.findtext("beat-type")))
                    except ValueError:
                        m2 = meter
                    if first:
                        tune.meter = m2
                    elif m2 != meter:
                        bar.meter = m2
                    meter = m2
            elif tag == "barline":
                rep = el.find("repeat")
                if rep is not None:
                    if rep.get("direction") == "forward":
                        bar.start_repeat = True
                    elif rep.get("direction") == "backward":
                        bar.end_repeat = True
                end = el.find("ending")
                if end is not None and end.get("type") == "start":
                    num = re.match(r"\d", (end.get("number") or "1").strip())
                    bar.volta = int(num.group(0)) if num else 1
                style = el.findtext("bar-style")
                if style in ("light-light", "light-heavy") and el.get("location", "right") == "right":
                    bar.double_bar = True
            elif tag == "harmony":
                ch = _harmony(el)
                off = t
                o = el.findtext("offset")
                if o:
                    try:
                        off = t + Fraction(int(float(o)), divisions)
                    except ValueError:
                        pass
                if ch is not None:
                    chords.append((off, ch))
            elif tag == "direction":
                snd = el.find("sound")
                if snd is not None and snd.get("tempo") and not tune.tempo_set:
                    try:
                        tune.tempo = int(float(snd.get("tempo")))
                        tune.tempo_set = True
                    except ValueError:
                        pass
            elif tag == "note":
                if el.find("grace") is not None:
                    continue
                voice = el.findtext("voice") or "1"
                if main_voice is None:
                    main_voice = voice
                if voice != main_voice:
                    continue
                dur_txt = el.findtext("duration")
                if dur_txt is None:
                    continue
                dur = Fraction(int(float(dur_txt)), divisions)
                is_chord = el.find("chord") is not None
                tie = any(tn.get("type") == "start" for tn in el.findall("tie"))
                if el.find("rest") is not None:
                    events.append(Ev(dur))
                    t += dur
                    continue
                p = el.find("pitch")
                if p is None:
                    events.append(Ev(dur))
                    t += dur
                    continue
                pitch = Pitch.of(STEP_NAMES.index(p.findtext("step").strip().upper()),
                                 int(float(p.findtext("alter") or 0)), int(p.findtext("octave")))
                marks = ()
                if el.find("notations/fermata") is not None:
                    marks = ("ferm",)
                if is_chord and events and not events[-1].is_rest:
                    prev = events[-1]
                    ps = tuple(sorted(set(prev.pitches + (pitch,)), key=lambda q: (q.midi, q.d)))
                    events[-1] = Ev(prev.dur, ps, prev.tie or tie, prev.marks)
                else:
                    events.append(Ev(dur, (pitch,), tie, marks))
                    t += dur
            elif tag == "forward":
                d = el.findtext("duration")
                if d:
                    dur = Fraction(int(float(d)), divisions)
                    events.append(Ev(dur))
                    t += dur
            elif tag == "backup":
                # anything after a backup belongs to another voice/staff
                break
        first = False
        if not events:
            continue
        # carry voltas: an ending lasts until the bar that closes it
        bar.melody = merge_ties(_top_only(events))
        bar.length = total(events)
        bar.chords = spread_stacked([(off, c) for off, c in chords if off < bar.length], bar.length, meter)
        tune.bars.append(bar)
    _finish(tune)
    return tune


def _top_only(events):
    return [Ev(e.dur, (e.top,), e.tie, e.marks) if e.pitches else e for e in events]


def _finish(tune: Tune) -> None:
    bars = tune.bars
    if not bars:
        raise ValueError("no music")
    nominal = tune.meter.bar_len
    # drop leading/trailing empty bars
    while bars and all(e.is_rest for e in bars[0].melody) and not bars[0].chords:
        nxt_flags = bars[0].start_repeat
        bars.pop(0)
        if bars and nxt_flags:
            bars[0].start_repeat = True
    while bars and all(e.is_rest for e in bars[-1].melody):
        last = bars.pop()
        if bars and last.end_repeat:
            bars[-1].end_repeat = True
    # endings: propagate the volta number over the bars it covers
    cur = 0
    for b in bars:
        if b.volta:
            cur = b.volta
        b.volta = cur
        if cur == 1 and b.end_repeat:
            cur = 0
        elif cur >= 2 and (b.double_bar or b.end_repeat):
            cur = 0
    # a second ending with no explicit end: same length as the first
    n1 = n2 = 0
    for b in bars:
        if b.volta == 1:
            n1 += 1
            n2 = 0
        elif b.volta == 2:
            n2 += 1
            if n1 and n2 > n1:
                b.volta = 0
        else:
            if b.volta == 0:
                pass
    for i, b in enumerate(bars):
        if b.meter is not None:
            nominal = b.meter.bar_len
        if b.length < nominal:
            if i == 0:
                b.pickup = True
            else:
                prev = bars[i - 1]
                if prev.length < nominal and prev.length + b.length == nominal and not prev.pickup:
                    b.pickup = True


def spread_stacked(chords: list, length: Fraction, meter: Meter) -> list:
    """Several chord symbols written at one spot really mean 'in this order
    until the next symbol': share the time between them, on the beat grid."""
    if len({off for off, _ in chords}) == len(chords):
        return chords
    out = []
    offs = sorted({off for off, _ in chords})
    beat = meter.beat_len
    for k, off in enumerate(offs):
        group = [c for o, c in chords if o == off]
        end = offs[k + 1] if k + 1 < len(offs) else length
        if len(group) == 1:
            out.append((off, group[0]))
            continue
        span = end - off
        n = len(group)
        step = span / n
        # snap to beats when possible
        if step % beat != 0:
            beats = int(span / beat)
            if beats >= n:
                step = beat * (beats // n)
            else:
                group = group[-1:] if beats < 1 else group[:max(beats, 1)]
                n = len(group)
                step = span / n
        for i, c in enumerate(group):
            out.append((off + step * i, c))
    return out


def infer_minor(tune: Tune) -> None:
    """Lead sheets often label minor keys as their relative major; fix that
    when the tune clearly ends on the relative minor."""
    if tune.key.mode != "major" or not tune.bars:
        return
    rel = (tune.key.tonic.pc + 9) % 12
    last_chord = None
    for b in reversed(tune.bars):
        if b.chords:
            last_chord = b.chords[-1][1]
            break
    last_note = None
    for b in reversed(tune.bars):
        for e in reversed(b.melody):
            if e.pitches:
                last_note = e.pitches[0]
                break
        if last_note:
            break
    first_chord = next((b.chords[0][1] for b in tune.bars if b.chords), None)
    votes = 0
    if last_chord is not None and last_chord.is_minor and last_chord.root.pc == rel:
        votes += 2
    if last_note is not None and last_note.pc == rel:
        votes += 1
    if first_chord is not None and first_chord.is_minor and first_chord.root.pc == rel:
        votes += 1
    if votes >= 3:
        tonic = tune.key.scale()[5]
        tune.key = Key(tonic.in_octave(4), "minor")


def read_musicxml_parts(path: Path) -> tuple:
    """Read every part of a score.  Returns (title, composer, [Tune per part],
    [part names]); each Tune holds that part's top line as its melody."""
    root = _read_xml(path)
    names = {}
    for sp in root.findall("part-list/score-part"):
        names[sp.get("id")] = (sp.findtext("part-name") or "").strip()
    title = (root.findtext("movement-title") or root.findtext("work/work-title") or Path(path).stem).strip()
    composers = [c.text.strip() for c in root.findall("identification/creator") if c.text]
    tunes = []
    part_names = []
    for part in root.findall("part"):
        solo = ET.Element("score-partwise")
        solo.append(part)
        try:
            t = _tune_from_root(solo, title)
        except ValueError:
            continue
        tunes.append(t)
        part_names.append(names.get(part.get("id"), ""))
    return title, ", ".join(composers), tunes, part_names
