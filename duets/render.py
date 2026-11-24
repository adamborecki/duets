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


def gs_available() -> bool:
    return shutil.which("gs") is not None


def _font_path() -> str:
    """Directories holding LilyPond's music fonts, for Ghostscript."""
    dirs = []
    exe = shutil.which("lilypond")
    if exe:
        prefix = Path(exe).resolve().parent.parent
        dirs += [str(p) for p in prefix.glob("share/lilypond/*/fonts/otf")]
    dirs += [str(p) for p in Path("/usr/share/lilypond").glob("*/fonts/otf")]
    return os.pathsep.join(dict.fromkeys(dirs))


def finalize(src: Path, dst: Path) -> Path:
    """Embed fonts (once per file) and compress.  Pieces are compiled without
    embedded fonts so that a 200-page book carries each font only once."""
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not gs_available():
        if src != dst:
            shutil.copyfile(src, dst)
        return dst
    tmp = dst.with_suffix(".tmp.pdf")
    cmd = ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.5",
           "-dAutoRotatePages=/None", "-dEmbedAllFonts=true", "-dSubsetFonts=true",
           "-dPrinted=false", f"-sFONTPATH={_font_path()}", f"-sOutputFile={tmp}", str(src)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not tmp.exists():
        raise RenderError(f"Ghostscript failed on {src.name}: {proc.stderr[-800:]}")
    tmp.replace(dst)
    return dst


def compile_ly(text: str, out_pdf: Path, midi_out: Path | None = None, use_cache: bool = True) -> dict:
    """Compile LilyPond source to ``out_pdf`` (fonts not embedded when
    Ghostscript is around to add them later with ``finalize``).
    Returns {'pages': n, 'warnings': [...]}."""
    out_pdf = Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    lazy_fonts = gs_available()
    digest = _digest(text)
    cdir = CACHE / digest[:2] / digest
    cpdf = cdir / "out.pdf"
    cmid = cdir / "out.midi"
    clog = cdir / "out.log"
    if not (use_cache and cpdf.exists()):
        cdir.mkdir(parents=True, exist_ok=True)
        src = cdir / "out.ly"
        src.write_text(text, encoding="utf-8")
        proc = subprocess.run(
            ["lilypond", "-dno-point-and-click"] + (["-dgs-never-embed-fonts"] if lazy_fonts else [])
            + ["--loglevel=WARNING", "-o", str(cdir / "out"), str(src)],
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


def _digest(text: str) -> str:
    return hashlib.sha1((("noembed|" if gs_available() else "embed|") + text).encode("utf-8")).hexdigest()


def compile_batch(texts: list) -> int:
    """Compile many LilyPond sources in one LilyPond run and file the results
    in the cache, so that later ``compile_ly`` calls return at once.  Starting
    LilyPond costs more than engraving a short piece, so this is several times
    faster than compiling one by one.  Returns the number compiled."""
    todo = {}
    for text in texts:
        d = _digest(text)
        if not (CACHE / d[:2] / d / "out.pdf").exists():
            todo[d] = text
    if not todo:
        return 0
    bdir = CACHE / f"_batch_{os.getpid()}"
    if bdir.exists():
        shutil.rmtree(bdir)
    bdir.mkdir(parents=True)
    for d, text in todo.items():
        (bdir / f"{d}.ly").write_text(text, encoding="utf-8")
    names = [f"{d}.ly" for d in todo]
    proc = subprocess.run(
        ["lilypond", "-dno-point-and-click"] + (["-dgs-never-embed-fonts"] if gs_available() else [])
        + ["--loglevel=WARNING"] + names, capture_output=True, text=True, cwd=str(bdir))
    log = proc.stdout + proc.stderr
    done = 0
    for d in todo:
        pdf = bdir / f"{d}.pdf"
        if not pdf.exists():
            continue
        cdir = CACHE / d[:2] / d
        cdir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bdir / f"{d}.ly", cdir / "out.ly")
        mine = [ln.replace(f"{d}.ly", "out.ly") for ln in log.splitlines() if d in ln]
        (cdir / "out.log").write_text("\n".join(mine), encoding="utf-8")
        mid = bdir / f"{d}.midi"
        if mid.exists():
            shutil.move(str(mid), cdir / "out.midi")
        shutil.move(str(pdf), cdir / "out.pdf")
        done += 1
    shutil.rmtree(bdir, ignore_errors=True)
    return done


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


def balance_page_tree(w: PdfWriter, fanout: int = 8) -> None:
    """Nest the writer's flat page list into a tree.  A viewer that fetches a
    big book piecemeal over the web (PDF.js on the practice page) can then find
    page 300 by reading a few small nodes instead of every page before it.
    Call this last, just before ``w.write``."""
    from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject
    root_ref = w._root_object.raw_get("/Pages")
    root = root_ref.get_object()
    level = list(root["/Kids"])
    if len(level) <= fanout:
        return

    def count(ref) -> int:
        o = ref.get_object()
        return int(o["/Count"]) if o.get("/Type") == "/Pages" else 1

    while len(level) > fanout:
        nxt = []
        for i in range(0, len(level), fanout):
            group = level[i:i + fanout]
            node = DictionaryObject({NameObject("/Type"): NameObject("/Pages")})
            ref = w._add_object(node)
            for k in group:
                k.get_object()[NameObject("/Parent")] = ref
            node[NameObject("/Kids")] = ArrayObject(group)
            node[NameObject("/Count")] = NumberObject(sum(count(k) for k in group))
            nxt.append(ref)
        level = nxt
    for k in level:
        k.get_object()[NameObject("/Parent")] = root_ref
    root[NameObject("/Kids")] = ArrayObject(level)


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


def stamp_page_numbers(src: Path, dst: Path, start_index: int = 0, first_number: int = 1,
                       outer: bool = True, size: float = 9.0, margin: float = 22.0,
                       two_up: bool = False) -> None:
    """Write page numbers in the top outer corners (or top right when
    ``outer`` is false).  With ``two_up`` each sheet shows two page numbers."""
    from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject, FloatObject,
                               NameObject)
    r = PdfReader(str(src))
    w = PdfWriter()
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Times-Roman")})
    num = first_number
    for i, page in enumerate(r.pages):
        w.add_page(page)
        if i < start_index:
            continue
        pg = w.pages[-1]
        pw, ph = float(pg.mediabox.width), float(pg.mediabox.height)
        ops = []

        def put(text, x, right):
            tw = 0.5 * size * len(text)
            xx = x - tw if right else x
            ops.append(f"BT /DuetF {size} Tf 0.25 g {xx:.1f} {ph - margin:.1f} Td ({text}) Tj ET")

        if two_up:
            put(str(num), margin, False)
            put(str(num + 1), pw - margin, True)
            num += 2
        else:
            left = outer and (num % 2 == 0)
            put(str(num), margin if left else pw - margin, not left)
            num += 1
        stream = DecodedStreamObject()
        stream.set_data(("q " + " ".join(ops) + " Q").encode("latin-1"))
        res = pg.get("/Resources")
        if res is None:
            res = DictionaryObject()
            pg[NameObject("/Resources")] = res
        res = res.get_object()
        fonts = res.get("/Font")
        if fonts is None:
            fonts = DictionaryObject()
            res[NameObject("/Font")] = fonts
        fonts = fonts.get_object()
        fonts[NameObject("/DuetF")] = w._add_object(font)
        ref = w._add_object(stream)
        contents = pg.get("/Contents")
        if contents is None:
            pg[NameObject("/Contents")] = ref
        else:
            c = contents.get_object()
            if isinstance(c, ArrayObject):
                c.append(ref)
            else:
                pg[NameObject("/Contents")] = ArrayObject([contents, ref])
    with open(dst, "wb") as fh:
        w.write(fh)
