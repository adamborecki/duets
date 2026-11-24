"""Command line: ``python -m duets ...``"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .catalog import FLAVORS, default_flavor, make_piece
from .engrave import LAYOUT_HELP, LAYOUTS, build_piece
from .library import load_file, load_library, slugify
from .lily import dots


def _find(tunes, query: str):
    q = query.strip().lower()
    by_slug = {t.slug: t for t in tunes}
    if q in by_slug:
        return by_slug[q], []
    if slugify(q) in by_slug:
        return by_slug[slugify(q)], []
    hits = [t for t in tunes if q in t.title.lower() or q in t.tune_name.lower() or q in t.slug]
    hits.sort(key=lambda t: (not t.title.lower().startswith(q), len(t.title)))
    if not hits:
        return None, []
    return hits[0], hits[1:8]


def _layouts(text: str):
    if text in ("all", ""):
        return LAYOUTS
    out = tuple(x.strip() for x in text.split(",") if x.strip())
    for x in out:
        if x not in LAYOUTS:
            raise SystemExit(f"unknown layout {x!r}; choose from {', '.join(LAYOUTS)} or 'all'")
    return out


def cmd_list(args):
    tunes = load_library()
    rows = []
    for t in tunes:
        if args.category and t.category != args.category and t.collection != args.category:
            continue
        if args.tag and args.tag not in t.tags:
            continue
        if args.search and args.search.lower() not in (t.title + " " + t.tune_name + " " + t.composer).lower():
            continue
        rows.append(t)
    for t in sorted(rows, key=lambda t: t.title.lower()):
        extra = f"  [{t.tune_name}]" if t.tune_name else ""
        print(f"{t.slug:55} {t.title}{extra}  ({t.category}; {t.key.short}, {t.meter.text})")
    print(f"\n{len(rows)} tunes")


def cmd_flavors(args):
    for name, (desc, o) in FLAVORS.items():
        print(f"{name:20} {desc}")
    print("\nLayouts:")
    for name, desc in LAYOUT_HELP.items():
        print(f"{name:20} {desc}")


def _make(tune, args):
    flavor = args.flavor or default_flavor(tune)
    piece = make_piece(tune, flavor, style=args.style, key=args.key, seed=args.seed,
                       primo=args.primo, secondo=args.secondo, melody=args.melody)
    out = Path(args.output)
    stem = tune.slug + "--" + flavor
    res = build_piece(piece, out, stem, layouts=_layouts(args.layout), paper=args.paper, midi=not args.no_midi)
    print(f"{piece.title} — {piece.flavor}")
    print(f"  key {piece.key.name}, {piece.meter.text}, {len(piece.bars)} bars")
    print(f"  Primo   {dots(piece.levels['p'])} {piece.levels['p']}")
    print(f"  Secondo {dots(piece.levels['s'])} {piece.levels['s']}")
    for k, v in res.items():
        if k != "info":
            print(f"  {k:13} {v}")
    for w in piece.stats.get("problems", []):
        print("  note:", w)
    for w in res["info"]["warnings"][:5]:
        print("  lilypond:", w)


def cmd_make(args):
    tunes = load_library()
    tune, others = _find(tunes, args.tune)
    if tune is None:
        raise SystemExit(f"no tune matches {args.tune!r}; try: python -m duets list --search ...")
    if others:
        print("(also matching: " + ", ".join(t.slug for t in others) + ")")
    _make(tune, args)


def cmd_abc(args):
    tunes = load_file(Path(args.file))
    if not tunes:
        raise SystemExit("no tune found in that file")
    for tune in tunes[: args.max]:
        if not tune.has_chords and not tune.has_satb:
            from .autoharm import harmonize
            harmonize(tune)
            print(f"({tune.title}: no chord symbols in the file — chords were chosen automatically)")
        _make(tune, args)


def cmd_books(args):
    from .books import BOOKS
    tunes = load_library()
    for b in sorted(BOOKS, key=lambda b: b.order):
        n = len(b.select(tunes))
        print(f"{b.id:20} {b.title} — {n} duets")


def cmd_book(args):
    from .books import BOOKS, book_by_id, build_book
    ids = [b.id for b in sorted(BOOKS, key=lambda b: b.order)] if args.book == "all" else [args.book]
    for bid in ids:
        build_book(book_by_id(bid), layouts=_layouts(args.layout), paper=args.paper, jobs=args.jobs,
                   limit=args.limit, outdir=Path(args.output) / bid if args.output else None)


def cmd_sunday(args):
    from .sundays import cmd_sunday as run
    run(args)


def cmd_new(args):
    from .compose import cmd_new as run
    run(args)


def cmd_variations(args):
    from .variations import cmd_variations as run
    run(args)


def cmd_catalog(args):
    from .site import build_site
    build_site()


def cmd_serve(args):
    """Serve the repository folder so the catalog and practice page work locally."""
    import http.server
    import os
    import re
    from .books import ROOT

    class Handler(http.server.SimpleHTTPRequestHandler):
        """Static files with byte ranges, so the practice page can fetch just the
        pages it shows from a big book (GitHub Pages does the same)."""

        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(ROOT), **kw)

        def log_message(self, *a):
            pass

        def end_headers(self):
            self.send_header("Accept-Ranges", "bytes")
            super().end_headers()

        def send_head(self):
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "").strip())
            path = self.translate_path(self.path)
            if not m or not (m.group(1) or m.group(2)) or not os.path.isfile(path):
                self._left = None
                return super().send_head()
            size = os.path.getsize(path)
            if m.group(1):
                start, end = int(m.group(1)), min(int(m.group(2) or size - 1), size - 1)
            else:                                           # last N bytes
                start, end = max(0, size - int(m.group(2))), size - 1
            if start > end or start >= size:
                self.send_error(416, "Requested range not satisfiable")
                return None
            f = open(path, "rb")
            f.seek(start)
            self._left = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(self._left))
            self.end_headers()
            return f

        def copyfile(self, source, outputfile):
            left = getattr(self, "_left", None)
            if left is None:
                return super().copyfile(source, outputfile)
            while left > 0:
                chunk = source.read(min(65536, left))
                if not chunk:
                    break
                outputfile.write(chunk)
                left -= len(chunk)

    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as srv:
        print(f"Catalog and practice page: http://127.0.0.1:{args.port}/   (Ctrl-C to stop)")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


def _common(p):
    p.add_argument("--flavor", default="", help="arrangement recipe (see: python -m duets flavors)")
    p.add_argument("--primo", type=int, help="override Primo difficulty 1-5")
    p.add_argument("--secondo", type=int, help="override Secondo difficulty 1-5")
    p.add_argument("--melody", choices=["p", "s", "swap"], help="who plays the tune")
    p.add_argument("--style", default="auto", help="accompaniment style: waltz, march, alberti, flowing, "
                                                   "walking, ballad, stride, chorale, jig, pad ...")
    p.add_argument("--key", default="auto", help="'auto', 'original' or a key such as G or Em")
    p.add_argument("--layout", default="all", help="facing, score, screen, screen-score or all")
    p.add_argument("--paper", default="letter", choices=["letter", "a4"])
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--no-midi", action="store_true")
    p.add_argument("-o", "--output", default="out", help="output folder")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="duets", description="Piano duets (four hands, one piano) from a library "
                                                         "of public-domain tunes.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="list tunes in the library")
    p.add_argument("--category")
    p.add_argument("--tag")
    p.add_argument("--search")
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("flavors", help="list arrangement recipes and layouts")
    p.set_defaults(fn=cmd_flavors)
    p = sub.add_parser("make", help="arrange one tune and write PDFs + MIDI")
    p.add_argument("tune", help="slug or part of a title")
    _common(p)
    p.set_defaults(fn=cmd_make)
    p = sub.add_parser("abc", help="arrange tunes from your own ABC file")
    p.add_argument("file")
    p.add_argument("--max", type=int, default=20)
    _common(p)
    p.set_defaults(fn=cmd_abc)
    p = sub.add_parser("books", help="list the books")
    p.set_defaults(fn=cmd_books)
    p = sub.add_parser("book", help="build a book (or 'all')")
    p.add_argument("book")
    p.add_argument("--layout", default="all")
    p.add_argument("--paper", default="letter", choices=["letter", "a4"])
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("-o", "--output", default="")
    p.set_defaults(fn=cmd_book)
    p = sub.add_parser("sunday", help="hymn suggestions (and a packet) for a Sunday")
    p.add_argument("date", nargs="?", default="")
    p.add_argument("--weeks", type=int, default=1)
    p.add_argument("--build", action="store_true", help="also build a PDF packet")
    p.add_argument("--layout", default="all")
    p.add_argument("--paper", default="letter", choices=["letter", "a4"])
    p.add_argument("-o", "--output", default="")
    p.set_defaults(fn=cmd_sunday)
    p = sub.add_parser("new", help="compose brand-new duets")
    p.add_argument("--style", default="any")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--layout", default="all")
    p.add_argument("--paper", default="letter", choices=["letter", "a4"])
    p.add_argument("--primo", type=int, default=2)
    p.add_argument("--secondo", type=int, default=3)
    p.add_argument("-o", "--output", default="out")
    p.set_defaults(fn=cmd_new)
    p = sub.add_parser("variations", help="theme and variations on a tune")
    p.add_argument("tune")
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--layout", default="all")
    p.add_argument("--paper", default="letter", choices=["letter", "a4"])
    p.add_argument("-o", "--output", default="out")
    p.set_defaults(fn=cmd_variations)
    p = sub.add_parser("catalog", help="rebuild the browsable catalog page")
    p.set_defaults(fn=cmd_catalog)
    p = sub.add_parser("serve", help="open the catalog and practice page on this computer")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(fn=cmd_serve)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
