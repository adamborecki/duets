"""LilyPond source generation.

``render_ly(piece, spec)`` returns the text of a complete ``.ly`` file for one
view of a piece: the stacked four-stave score, or a single part (Primo or
Secondo) whose line and page breaks are forced so the two parts line up when
they sit on facing pages.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional

from .model import HANDS, Ev, F, PBar, Piece
from .notate import lily_dur, notate, representable
from .theory import Chord, Key, Meter

PART_HANDS = {"p": ("prh", "plh"), "s": ("srh", "slh")}
PART_NAME = {"p": "Primo", "s": "Secondo"}

_MARK_LY = {
    "stacc": "-.", "accent": "->", "ten": "--", "ferm": "\\fermata",
    "arp": "\\arpeggio", "slur(": "(", "slur)": ")", "marcato": "-^",
}


@dataclass
class Spec:
    """How to lay a piece out on paper."""

    parts: tuple = ("p", "s")            # which parts are shown
    paper: tuple = (215.9, 279.4)        # width, height in mm
    staff_size: float = 18.0
    margins: tuple = (10.0, 10.0, 12.0, 12.0)   # top, bottom, left, right (mm)
    breaks: Optional[set] = None         # bar indices after which a new system starts
    page_breaks: set = field(default_factory=set)
    chords: bool = True
    title: bool = True
    midi: bool = False
    footer: str = ""
    label: str = ""                      # e.g. "Secondo ●●○○○"
    ragged_last: bool = False
    auto_pages: bool = False             # let LilyPond choose page breaks even with manual line breaks
    compact: bool = False                # tighter vertical spacing

    @property
    def is_score(self) -> bool:
        return len(self.parts) == 2


def q(text: str) -> str:
    """Quote a string for LilyPond."""
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def frac_dur(d: Fraction, base: str = "1") -> str:
    """Duration with a multiplier, relative to a whole note: 3 quarters -> 1*3/4."""
    w = Fraction(d) / 4
    if w == 1:
        return base
    if w.denominator == 1:
        return f"{base}*{w.numerator}"
    return f"{base}*{w.numerator}/{w.denominator}"


def moment(d: Fraction) -> str:
    w = Fraction(d) / 4
    return f"#(ly:make-moment {w.numerator} {w.denominator})"


# ---------------------------------------------------------------------------
# timing: partial bars, irregular bars, bars split by a repeat sign
# ---------------------------------------------------------------------------
def timing_plan(bars, meter: Meter) -> list:
    """For every bar decide which timing command the engraver needs.

    Returns a list of dicts with keys:
      partial   – length for ``\\partial`` (first-bar anacrusis)
      set_len   – measure length to set before this bar (None = no change)
      open      – True if the measure is still incomplete after this bar
                  (the next bar is an upbeat that completes it)
      joined    – True if this bar continues the previous, incomplete measure
    """
    plan = []
    nominal = meter.bar_len
    ly_len = nominal        # measure length LilyPond currently believes in
    pos = F(0)
    n = len(bars)
    for i, b in enumerate(bars):
        if b.meter is not None:
            nominal = b.meter.bar_len
            ly_len = nominal
            pos = F(0)
        act = {"partial": None, "set_len": None, "open": False, "joined": False}
        L = b.length
        if pos != 0:
            act["joined"] = True
            pos = (pos + L) % ly_len
            if pos != 0 and not (i + 1 < n and bars[i + 1].pickup):
                pos = F(0)
            act["open"] = pos != 0
            plan.append(act)
            continue
        if L == nominal:
            if ly_len != nominal:
                act["set_len"] = nominal
                ly_len = nominal
        elif i == 0 and L < nominal and b.pickup:
            if ly_len != nominal:
                act["set_len"] = nominal
                ly_len = nominal
            act["partial"] = L
        else:
            nxt = bars[i + 1] if i + 1 < n else None
            if (L < nominal and nxt is not None and nxt.pickup and nxt.meter is None
                    and L + nxt.length == nominal):
                if ly_len != nominal:
                    act["set_len"] = nominal
                    ly_len = nominal
                act["open"] = True
                pos = L
            else:
                if ly_len != L:
                    act["set_len"] = L
                    ly_len = L
        plan.append(act)
    return plan


# ---------------------------------------------------------------------------
# events -> text
# ---------------------------------------------------------------------------
def ev_ly(e: Ev) -> str:
    dur = lily_dur(e.dur) if representable(e.dur) else frac_dur(e.dur, "1")
    if e.is_rest:
        return "r" + dur
    if len(e.pitches) == 1:
        s = e.pitches[0].lily() + dur
    else:
        ps = sorted(set(e.pitches), key=lambda p: (p.midi, p.d))
        s = "<" + " ".join(p.lily() for p in ps) + ">" + dur
    for m in e.marks:
        s += _MARK_LY.get(m, "")
    if e.tie:
        s += "~"
    return s


def voice_ly(events, meter: Meter, mpos: Fraction) -> str:
    out = []
    for tok in notate(events, meter, mpos):
        if isinstance(tok, tuple):
            _, (num, den), evs = tok
            out.append("\\tuplet %d/%d { %s }" % (num, den, " ".join(ev_ly(e) for e in evs)))
        else:
            out.append(ev_ly(tok))
    return " ".join(out)


def _all_rests(events) -> bool:
    return all(e.is_rest for e in events)


def hand_bar_ly(voices, meter: Meter, mpos: Fraction, length: Fraction, whole_ok: bool) -> str:
    voices = [v for v in voices if v]
    if not voices or all(_all_rests(v) for v in voices):
        if whole_ok:
            return "R" + frac_dur(length)
        return voice_ly([Ev(length)], meter, mpos)
    live = [v for v in voices if not _all_rests(v)]
    if len(live) == 1:
        return voice_ly(live[0], meter, mpos)
    a, b = live[0], live[1]
    return "<< { %s } \\\\ { %s } >>" % (voice_ly(a, meter, mpos), voice_ly(b, meter, mpos))


def chords_bar_ly(chords, length: Fraction, carried: Optional[Chord]) -> tuple:
    """Chord-name tokens for one bar; returns (text, chord sounding at the bar end)."""
    pts = sorted(chords, key=lambda c: c[0])
    out = []
    cur = carried
    t = F(0)
    if not pts or pts[0][0] > 0:
        end = pts[0][0] if pts else length
        if cur is None:
            out.append("s" + frac_dur(end - t))
        else:
            out.append(cur.lily(frac_dur(end - t)))
        t = end
    for i, (off, ch) in enumerate(pts):
        end = pts[i + 1][0] if i + 1 < len(pts) else length
        if end <= off:
            continue
        cur = ch
        if ch is None:
            out.append("s" + frac_dur(end - off))
        else:
            out.append(ch.lily(frac_dur(end - off)))
    return " ".join(out), cur


# ---------------------------------------------------------------------------
# whole file
# ---------------------------------------------------------------------------
def _per_bar(value, n, default):
    if isinstance(value, (list, tuple)):
        return list(value) + [default] * (n - len(value))
    return [value if value is not None else default] * n


def build_music(piece: Piece, spec: Spec, unfolded: bool = False) -> dict:
    """Return LilyPond music strings: global, chords, dyn_p, dyn_s and one per hand."""
    bars = piece.bars
    order = piece.play_order() if unfolded else list(range(len(bars)))
    seq = [bars[i] for i in order]
    n = len(seq)
    if unfolded:
        # a linear copy: no repeat signs or endings
        import copy
        seq2 = []
        for b in seq:
            c = copy.copy(b)
            c.start_repeat = c.end_repeat = False
            c.volta = 0
            seq2.append(c)
        seq = seq2
    plan = timing_plan(seq, piece.meter)
    meter = piece.meter
    key = piece.key
    clefs = {h: _per_bar(piece.clefs.get(h), len(bars), "treble" if h[0] == "p" else "bass") for h in HANDS}
    ottava = {h: _per_bar(piece.ottava.get(h), len(bars), 0) for h in HANDS}

    g: list = []
    ch: list = []
    dyn = {"p": [], "s": []}
    hv = {h: [] for h in HANDS}
    cur_clef = {h: None for h in HANDS}
    cur_ott = {h: 0 for h in HANDS}
    carried: Optional[Chord] = None
    mpos = F(0)
    breaks = spec.breaks if (spec.breaks is not None and not unfolded) else set()
    page_breaks = spec.page_breaks if not unfolded else set()

    for k, b in enumerate(seq):
        src = order[k]
        act = plan[k]
        pre = []
        if b.meter is not None:
            meter = b.meter
        if k == 0:
            if not piece.free_meter:
                pre.append(meter.lily())
            pre.append(key.lily())
            beat = meter.beat_len
            unit = lily_dur(beat) if representable(beat) else "4"
            if piece.tempo_text:
                pre.append(f"\\tempo {q(piece.tempo_text)} {unit} = {piece.tempo}")
            else:
                pre.append(f"\\tempo {unit} = {piece.tempo}")
        else:
            if b.meter is not None and not piece.free_meter:
                pre.append(b.meter.lily())
            if b.key is not None:
                key = b.key
                pre.append(key.lily())
            if b.tempo is not None:
                text, bpm = b.tempo
                beat = meter.beat_len
                unit = lily_dur(beat) if representable(beat) else "4"
                pre.append(f"\\tempo {q(text)} {unit} = {bpm}" if text else f"\\tempo {unit} = {bpm}")
        if act["set_len"] is not None:
            pre.append(f"\\set Timing.measureLength = {moment(act['set_len'])}")
        if act["partial"] is not None:
            pre.append(f"\\partial {frac_dur(act['partial'])}")
            mpos = meter.bar_len - b.length
        elif not act["joined"]:
            mpos = F(0)
        # volta brackets
        prev = seq[k - 1] if k else None
        if b.volta and (prev is None or prev.volta != b.volta):
            if prev is not None and prev.volta:
                pre.append('\\set Score.repeatCommands = #\'((volta #f) (volta "%d."))' % b.volta)
            else:
                pre.append('\\set Score.repeatCommands = #\'((volta "%d."))' % b.volta)
        elif not b.volta and prev is not None and prev.volta:
            pre.append("\\set Score.repeatCommands = #'((volta #f))")
        if b.start_repeat and k > 0 and not (prev.end_repeat):
            if not (k == 1 and seq[0].pickup):
                pre.append('\\bar ".|:"')
            else:
                pre.append('\\bar ".|:"')
        if b.mark:
            pre.append("\\mark \\markup { \\box \\bold %s }" % q(b.mark))
        spacer = "s" + frac_dur(b.length)
        if b.text:
            spacer += "^\\markup { \\italic %s }" % q(b.text)
        post = []
        nxt = seq[k + 1] if k + 1 < n else None
        if b.final or nxt is None:
            if b.end_repeat:
                post.append('\\bar ":|."')
            else:
                post.append('\\bar "|."')
            if b.volta:
                post.append("\\set Score.repeatCommands = #'((volta #f))")
        elif b.end_repeat and nxt.start_repeat:
            post.append('\\bar ":|.|:"')
        elif b.end_repeat:
            post.append('\\bar ":|."')
        elif b.double_bar and not nxt.start_repeat:
            post.append('\\bar "||"')
        elif act["open"]:
            post.append('\\bar "|"')
        if src in page_breaks and nxt is not None:
            post.append("\\pageBreak")
        elif src in breaks and nxt is not None:
            post.append("\\break")
        g.append(" ".join(pre + [spacer] + post))

        # chord names
        ctext, carried = chords_bar_ly(b.chords, b.length, carried)
        ch.append(ctext)

        # dynamics
        for part in ("p", "s"):
            d = b.dyn.get(part)
            s = "s" + frac_dur(b.length)
            if d in ("pp", "p", "mp", "mf", "f", "ff"):
                s += "\\" + d
            elif d == "<":
                s += "\\<"
            elif d == ">":
                s += "\\>"
            elif d == "!":
                s += "\\!"
            dyn[part].append(s)

        # notes
        whole_ok = (not act["joined"]) and (not act["open"]) and act["partial"] is None
        for h in HANDS:
            pre_h = []
            if k == 0:
                pre_h.append(key.lily())
            elif b.key is not None:
                pre_h.append(b.key.lily())
            c = clefs[h][src]
            if c != cur_clef[h]:
                pre_h.append(f"\\clef {c}")
                cur_clef[h] = c
            o = ottava[h][src]
            if o != cur_ott[h]:
                pre_h.append(f"\\ottava #{o}")
                cur_ott[h] = o
            body = hand_bar_ly(b.hands.get(h, []), meter, mpos, b.length, whole_ok)
            sep = "" if act["open"] else " |"
            hv[h].append(" ".join(pre_h + [body]) + sep)
        mpos = (mpos + b.length) % meter.bar_len if act["open"] or act["joined"] else F(0)
        if act["joined"] and not act["open"]:
            mpos = F(0)

    def block(lines):
        return "{\n  " + "\n  ".join(lines) + "\n}"

    music = {"global": block(g), "chords": "\\chordmode " + block(ch),
             "dyn_p": block(dyn["p"]), "dyn_s": block(dyn["s"])}
    for h in HANDS:
        music[h] = block(hv[h])
    return music


def dots(level: float) -> str:
    n = max(1, min(5, int(round(level))))
    return "●" * n + "○" * (5 - n)


def _paper(spec: Spec, piece: Piece) -> str:
    w, h = spec.paper
    top, bottom, left, right = spec.margins
    manual = spec.breaks is not None
    lines = [
        "\\paper {",
        "  #(set! paper-alist (cons '(\"duet\" . (cons (* %.2f mm) (* %.2f mm))) paper-alist))" % (w, h),
        '  #(set-paper-size "duet")',
        f"  top-margin = {top}\\mm",
        f"  bottom-margin = {bottom}\\mm",
        f"  left-margin = {left}\\mm",
        f"  right-margin = {right}\\mm",
        "  indent = %s\\mm" % ("14" if spec.is_score else "0"),
        "  short-indent = %s\\mm" % ("5" if spec.is_score else "0"),
        "  ragged-right = ##f",
        "  ragged-last = %s" % ("##t" if spec.ragged_last else "##f"),
        "  ragged-bottom = ##f",
        "  ragged-last-bottom = ##t",
        "  print-page-number = ##f",
        "  oddHeaderMarkup = ##f",
        "  evenHeaderMarkup = ##f",
        "  bookTitleMarkup = \\markup \\column {",
        "    \\fill-line { \\fontsize #5 \\bold \\fromproperty #'header:title }",
        "    \\vspace #0.25",
        "    \\fill-line { \\fontsize #0.5 \\italic \\fromproperty #'header:subtitle }",
        "    \\vspace #0.35",
        "    \\fill-line {",
        "      \\fontsize #0.5 \\fromproperty #'header:poet",
        "      \\right-column { \\fontsize #0.5 \\fromproperty #'header:composer",
        "                      \\fontsize #-0.5 \\fromproperty #'header:arranger }",
        "    }",
        "  }",
        "  oddFooterMarkup = \\markup \\fill-line { \\fontsize #-3.5 \\if \\on-first-page \\fromproperty #'header:copyright }",
        "  evenFooterMarkup = \\oddFooterMarkup",
        "  markup-system-spacing.padding = #%s" % ("2.5" if spec.compact else "3.5"),
        "  system-system-spacing.padding = #%s" % ("2.2" if spec.compact else "3.2"),
        "  system-system-spacing.basic-distance = #%s" % ("14" if spec.compact else "16"),
        "  last-bottom-spacing.padding = #2",
    ]
    if manual:
        lines.append("  page-breaking = #ly:optimal-breaking")
    lines.append("}")
    return "\n".join(lines)


def _layout(spec: Spec, piece: Piece) -> str:
    manual = spec.breaks is not None
    lines = [
        "  \\layout {",
        "    \\context { \\Score",
        "      \\override BarNumber.font-size = #0.5",
        "      \\override BarNumber.font-series = #'bold",
        "      \\override BarNumber.padding = #1.2",
        "      \\override RehearsalMark.self-alignment-X = #LEFT",
        "      \\override RehearsalMark.font-size = #1",
        "      \\override MetronomeMark.font-size = #0.5",
        "      \\override VoltaBracket.font-size = #-1",
        "      \\override OttavaBracket.font-size = #-1",
    ]
    if manual:
        lines.append("      \\override NonMusicalPaperColumn.line-break-permission = ##f")
        if not spec.auto_pages:
            lines.append("      \\override NonMusicalPaperColumn.page-break-permission = ##f")
    lines += [
        "    }",
        "    \\context { \\Staff",
        "      \\numericTimeSignature",
    ]
    if piece.free_meter:
        lines.append("      \\omit TimeSignature")
    lines += [
        "    }",
        "    \\context { \\ChordNames",
        "      chordChanges = ##t",
        "      majorSevenSymbol = \\markup { maj7 }",
        "      \\override ChordName.font-size = #1.2",
        "      \\override ChordName.font-series = #'bold",
        "    }",
        "    \\context { \\PianoStaff",
        "      \\override StaffGrouper.staff-staff-spacing.padding = #1.4",
        "      \\override StaffGrouper.staff-staff-spacing.basic-distance = #%s" % ("8.5" if spec.compact else "9.5"),
        "      \\override StaffGrouper.staffgroup-staff-spacing.basic-distance = #13",
        "      \\override StaffGrouper.staffgroup-staff-spacing.padding = #2.5",
        "    }",
        "  }",
    ]
    return "\n".join(lines)


def _part_block(part: str, spec: Spec, with_global: bool, named: bool) -> str:
    rh, lh = PART_HANDS[part]
    with_ = ""
    if named:
        short = {"p": "I", "s": "II"}[part]
        with_ = ' \\with { instrumentName = %s shortInstrumentName = %s }' % (q(PART_NAME[part]), q(short))
    top = "<< \\global \\%s >>" % rh if with_global else "\\%s" % rh
    lines = []
    if spec.chords:
        lines.append("    \\new ChordNames \\harmonies")
    lines += [
        "    \\new PianoStaff%s <<" % with_,
        "      \\new Staff = \"%s\" %s" % (rh, top),
        "      \\new Dynamics \\dyn%s" % {"p": "P", "s": "S"}[part],
        "      \\new Staff = \"%s\" \\%s" % (lh, lh),
        "    >>",
    ]
    return "\n".join(lines)


def render_ly(piece: Piece, spec: Spec) -> str:
    music = build_music(piece, spec)
    out = ['\\version "2.24.0"', "#(set-global-staff-size %.2f)" % spec.staff_size, ""]
    out.append(_paper(spec, piece))
    # header
    hdr = ["\\header {"]
    if spec.title:
        hdr.append(f"  title = {q(piece.title)}")
        if piece.subtitle:
            hdr.append(f"  subtitle = {q(piece.subtitle)}")
        if piece.composer:
            hdr.append(f"  composer = {q(piece.composer)}")
        if piece.arranger:
            hdr.append(f"  arranger = {q(piece.arranger)}")
        if spec.label:
            hdr.append(f"  poet = {q(spec.label)}")
    if spec.footer:
        hdr.append(f"  copyright = {q(spec.footer)}")
    hdr.append("  tagline = ##f")
    hdr.append("}")
    out.append("\n".join(hdr))
    out.append("")
    out.append("global = " + music["global"])
    out.append("harmonies = " + music["chords"])
    out.append("dynP = " + music["dyn_p"])
    out.append("dynS = " + music["dyn_s"])
    for h in HANDS:
        out.append(f"{h} = " + music[h])
    out.append("")
    out.append("\\score {")
    out.append("  <<")
    for i, part in enumerate(spec.parts):
        out.append(_part_block(part, spec, with_global=(i == 0), named=spec.is_score))
    out.append("  >>")
    out.append(_layout(spec, piece))
    out.append("}")
    if spec.midi:
        out.append(midi_score(piece, spec))
    return "\n".join(out) + "\n"


def midi_score(piece: Piece, spec: Spec, parts=("p", "s")) -> str:
    um = build_music(piece, Spec(parts=spec.parts, breaks=None), unfolded=True)
    beat = piece.meter.beat_len
    out = ["", "% ---- playback (repeats written out) ----"]
    out.append("globalMidi = " + um["global"])
    for h in HANDS:
        out.append(f"{h}Midi = " + um[h])
    out.append("\\score {")
    out.append("  <<")
    first = True
    for part in parts:
        for h in PART_HANDS[part]:
            g = "\\globalMidi " if first else ""
            first = False
            out.append('    \\new Staff \\with { midiInstrument = "acoustic grand" } << %s\\%sMidi >>' % (g, h))
    out.append("  >>")
    out.append("  \\midi { }")
    out.append("}")
    return "\n".join(out)
