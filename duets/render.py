"""Running LilyPond and assembling PDFs."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf._page import PageObject

CACHE = Path(os.environ.get("DUETS_CACHE", Path(__file__).resolve().parent.parent / ".cache"))


class RenderError(RuntimeError):
    pass


def lilypond_available() -> bool:
    return shutil.which("lilypond") is not None


def compile_ly(text: str, out_pdf: Path, midi_out: Path | None = None, use_cache: bool = True) -> dict:
    """Compile LilyPond source to ``out_pdf``.  Returns {'pages': n, 'warnings': [...]}."""
    out_pdf = Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    cdir = CACHE / digest[:2] / digest
    cpdf = cdir / "out.pdf"
    cmid = cdir / "out.midi"
    clog = cdir / "out.log"
    if not (use_cache and cpdf.exists()):
        cdir.mkdir(parents=True, exist_ok=True)
        src = cdir / "out.ly"
        src.write_text(text, encoding="utf-8")
        proc = subprocess.run(
            ["lilypond", "-dno-point-and-click", "--loglevel=WARNING", "-o", str(cdir / "out"), str(src)],
            capture_output=True, text=True)
        log = proc.stdout + proc.stderr
        clog.write_text(log, encoding="utf-8")
        if proc.returncode != 0 or not cpdf.exists():
            if cpdf.exists():
                cpdf.unlink()
            raise RenderError(f"LilyPond failed for {out_pdf.name}:\n{log[-3000:]}")
    log = clog.read_text(encoding="utf-8") if clog.exists() else ""
    shutil.copyfile(cpdf, out_pdf)
    if midi_out is not None and cmid.exists():
        Path(midi_out).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cmid, midi_out)
    warnings = [ln for ln in log.splitlines() if "warning" in ln.lower() or "error" in ln.lower()]
    return {"pages": len(PdfReader(str(out_pdf)).pages), "warnings": warnings, "log": log}


def page_count(pdf: Path) -> int:
    return len(PdfReader(str(pdf)).pages)


def interleave(left: Path, right: Path, out: Path) -> int:
    """Alternate the pages of two PDFs: left 1, right 1, left 2, right 2 ..."""
    a, b = PdfReader(str(left)), PdfReader(str(right))
    w = PdfWriter()
    for i in range(max(len(a.pages), len(b.pages))):
        if i < len(a.pages):
            w.add_page(a.pages[i])
        if i < len(b.pages):
            w.add_page(b.pages[i])
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        w.write(fh)
    return len(w.pages)


def two_up(left: Path, right: Path, out: Path, gap_pt: float = 0.0) -> int:
    """Put page i of ``left`` and page i of ``right`` side by side on one sheet."""
    a, b = PdfReader(str(left)), PdfReader(str(right))
    w = PdfWriter()
    for i in range(max(len(a.pages), len(b.pages))):
        pa = a.pages[i] if i < len(a.pages) else None
        pb = b.pages[i] if i < len(b.pages) else None
        ref = pa or pb
        pw, ph = float(ref.mediabox.width), float(ref.mediabox.height)
        sheet = PageObject.create_blank_page(width=2 * pw + gap_pt, height=ph)
        if pa is not None:
            sheet.merge_transformed_page(pa, Transformation().translate(0, 0))
        if pb is not None:
            sheet.merge_transformed_page(pb, Transformation().translate(pw + gap_pt, 0))
        w.add_page(sheet)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        w.write(fh)
    return len(w.pages)


def concat(pdfs, out: Path, outline=None) -> int:
    """Concatenate PDFs; ``outline`` is a list of (title, first_page_index)."""
    w = PdfWriter()
    for p in pdfs:
        r = PdfReader(str(p))
        for pg in r.pages:
            w.add_page(pg)
    for title, idx in (outline or []):
        w.add_outline_item(title, idx)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        w.write(fh)
    return len(w.pages)


def png_preview(pdf: Path, out_prefix: Path, dpi: int = 80, first: int = 1, last: int | None = None) -> list:
    """Rasterise pages with pdftoppm (for eyeballing output)."""
    out_prefix = Path(out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["pdftoppm", "-png", "-r", str(dpi), "-f", str(first)]
    if last:
        cmd += ["-l", str(last)]
    cmd += [str(pdf), str(out_prefix)]
    subprocess.run(cmd, check=True, capture_output=True)
    return sorted(out_prefix.parent.glob(out_prefix.name + "*.png"))
