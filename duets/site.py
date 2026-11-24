"""The browsable catalog: ``index.html`` at the top of the repository.

A single self-contained page (no network needed) listing every book with
links to its four editions, and a searchable, sortable table of every duet
with both difficulty ratings.  Open it from the repository folder, or let
GitHub Pages serve it.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from .books import BOOKS, BOOKS_DIR, ROOT

NAMES = {"facing": "Print · facing pages", "score": "Print · full score",
         "screen": "Screen · side by side", "screen-score": "Screen · full score"}


def collect() -> list:
    out = []
    order = {b.id: b.order for b in BOOKS}
    meta = {b.id: b for b in BOOKS}
    for d in sorted(BOOKS_DIR.iterdir() if BOOKS_DIR.exists() else []):
        f = d / "contents.json"
        if not f.exists():
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        b = meta.get(d.name)
        if b:
            data["subtitle"], data["blurb"] = b.subtitle, b.blurb
        else:
            data["subtitle"] = data.get("subtitle") or "Hymns of the day for the weeks ahead"
            data["blurb"] = data.get("blurb") or "A packet built with: python -m duets sunday --build"
        data["order"] = order.get(d.name, 0 if d.name.startswith("sundays") else 99)
        data["dir"] = d.name
        out.append(data)
    out.sort(key=lambda x: (x["order"], x["title"]))
    return out


def build_site(path: Path = None) -> Path:
    books = collect()
    path = path or ROOT / "index.html"
    rows = []
    for b in books:
        for it in b["items"]:
            rows.append({
                "t": it["title"], "s": it.get("subtitle") or "", "c": it.get("composer") or "",
                "b": b["title"], "d": b["dir"], "k": it["key"], "m": it["meter"],
                "p": it["levels"]["p"], "q": it["levels"]["s"], "f": it["flavor_text"],
                "sec": it.get("section") or "", "pg": it["pages"],
                "fn": {k: Path(v["path"]).name for k, v in b["layouts"].items()},
            })
    total = len(rows)
    cards = []
    for b in books:
        links = " ".join(
            f'<a class="ed" href="books/{b["dir"]}/{Path(v["path"]).name}">{html.escape(NAMES[k])}'
            f'<span>{v["pages"]} pp</span></a>' for k, v in b["layouts"].items())
        cards.append(
            f'<article class="book"><h3>{html.escape(b["title"])}</h3>'
            f'<p class="sub">{html.escape(b["subtitle"])} · {b["pieces"]} duets</p>'
            f'<p>{html.escape(b["blurb"])}</p><div class="eds">{links}</div></article>')
    doc = _PAGE.replace("__CARDS__", "\n".join(cards)).replace("__DATA__", json.dumps(rows, ensure_ascii=False)) \
        .replace("__TOTAL__", str(total)).replace("__NBOOKS__", str(len(books)))
    path.write_text(doc, encoding="utf-8")
    # a plain index for browsing the books folder on GitHub
    lines = ["# The books", "",
             f"{total} duets in {len(books)} books. Each book comes in four editions; open a book's folder "
             "for its contents list with difficulty ratings.", "",
             "| Book | Duets | Print: facing pages | Print: score | Screen: side by side | Screen: score |",
             "|---|---|---|---|---|---|"]
    for b in books:
        cells = []
        for k in ("facing", "score", "screen", "screen-score"):
            v = b["layouts"].get(k)
            cells.append(f'[{v["pages"]} pp]({b["dir"]}/{Path(v["path"]).name})' if v else "")
        lines.append(f'| [**{b["title"]}**]({b["dir"]}/) <br><sub>{b["subtitle"]}</sub> | {b["pieces"]} | '
                     + " | ".join(cells) + " |")
    (BOOKS_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path} ({total} duets in {len(books)} books)")
    return path


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Piano Duets</title>
<style>
:root { --bg:#faf8f3; --ink:#1d1b18; --muted:#6b6459; --line:#ddd6c8; --card:#fff; --accent:#7a2e1f; --dot:#7a2e1f; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#17161a; --ink:#ece8df; --muted:#a39d91; --line:#34323a; --card:#201f25; --accent:#e0a28f; --dot:#e0a28f; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:16px/1.5 Georgia, "Iowan Old Style", "Palatino Linotype", serif; }
main { max-width:1100px; margin:0 auto; padding:24px 16px 80px; }
h1 { font-size:2.2rem; margin:.4em 0 .1em; letter-spacing:.01em; }
h2 { margin:2.2em 0 .6em; font-size:1.35rem; border-bottom:1px solid var(--line); padding-bottom:.3em; }
.lede { color:var(--muted); max-width:46em; }
.books { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:14px; }
.book { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px 16px; }
.book h3 { margin:0 0 .15em; font-size:1.12rem; }
.book p { margin:.3em 0; font-size:.92rem; }
.sub { color:var(--muted); font-style:italic; }
.eds { display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-top:.7em; }
a.ed { display:flex; justify-content:space-between; gap:8px; border:1px solid var(--line); border-radius:6px;
  padding:5px 8px; font:13px/1.3 system-ui, sans-serif; color:var(--accent); text-decoration:none; }
a.ed:hover { background:var(--bg); }
a.ed span { color:var(--muted); white-space:nowrap; }
.controls { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin:.6em 0 1em; font:14px system-ui, sans-serif; }
.controls input[type=search] { flex:1 1 240px; padding:8px 10px; border:1px solid var(--line); border-radius:6px;
  background:var(--card); color:var(--ink); font:inherit; }
.controls select { padding:7px 8px; border:1px solid var(--line); border-radius:6px; background:var(--card); color:var(--ink); font:inherit; }
.tablewrap { overflow-x:auto; border:1px solid var(--line); border-radius:8px; background:var(--card); }
table { border-collapse:collapse; width:100%; font:14px/1.35 system-ui, sans-serif; }
th, td { text-align:left; padding:7px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
th { cursor:pointer; white-space:nowrap; position:sticky; top:0; background:var(--card); }
td.t { font-family:Georgia, serif; font-size:15px; }
td small { color:var(--muted); display:block; }
.dots { color:var(--dot); letter-spacing:1px; white-space:nowrap; }
.count { color:var(--muted); }
td a { color:var(--accent); text-decoration:none; margin-right:8px; white-space:nowrap; }
footer { margin-top:3em; color:var(--muted); font-size:.9rem; }
</style>
</head>
<body>
<main>
<h1>Piano Duets</h1>
<p class="lede">__TOTAL__ duets for one piano, four hands, in __NBOOKS__ books. Every piece comes in four
editions: facing pages for printing (Secondo on the left, Primo on the right, lines and bar numbers matching),
a printed full score, and two 16:10 screen editions for a laptop or tablet on the music stand.
Dots rate each seat from 1 (beginner) to 5 (late intermediate); chord symbols are printed over both parts.</p>

<h2>The books</h2>
<section class="books">
__CARDS__
</section>

<h2>Every duet</h2>
<div class="controls">
  <input id="q" type="search" placeholder="Search titles, tune names, composers…" aria-label="Search">
  <select id="book" aria-label="Book"><option value="">All books</option></select>
  <select id="pmax" aria-label="Primo level"><option value="9">Primo: any level</option><option value="1.5">Primo ≤ 1</option><option value="2.5">Primo ≤ 2</option><option value="3.5">Primo ≤ 3</option></select>
  <select id="smax" aria-label="Secondo level"><option value="9">Secondo: any level</option><option value="1.5">Secondo ≤ 1</option><option value="2.5">Secondo ≤ 2</option><option value="3.5">Secondo ≤ 3</option></select>
  <span class="count" id="count"></span>
</div>
<div class="tablewrap">
<table>
<thead><tr><th data-k="t">Title</th><th data-k="b">Book</th><th data-k="k">Key</th><th data-k="p">Primo</th><th data-k="q">Secondo</th><th data-k="f">Setting</th><th>Open at page</th></tr></thead>
<tbody id="rows"></tbody>
</table>
</div>
<footer>
<p>Made with <strong>duets</strong>, an open-source generator in this repository — run
<code>python -m duets make "title"</code> for any tune in another setting, key or difficulty.
All melodies are in the public domain in the United States; sources are credited at the foot of each piece.</p>
</footer>
</main>
<script>
const DATA = __DATA__;
const $ = id => document.getElementById(id);
const dots = v => { const n = Math.max(1, Math.min(5, Math.round(v))); return "●".repeat(n) + "○".repeat(5 - n); };
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const books = [...new Set(DATA.map(r => r.b))];
for (const b of books) { const o = document.createElement("option"); o.value = b; o.textContent = b; $("book").appendChild(o); }
let sortKey = null, sortDir = 1;
const ED = {facing:"print", score:"score", screen:"screen", "screen-score":"screen score"};
function render() {
  const q = $("q").value.trim().toLowerCase(), book = $("book").value;
  const pmax = parseFloat($("pmax").value), smax = parseFloat($("smax").value);
  let rows = DATA.filter(r => (!book || r.b === book) && r.p <= pmax && r.q <= smax &&
    (!q || (r.t + " " + r.s + " " + r.c + " " + r.sec).toLowerCase().includes(q)));
  if (sortKey) rows = rows.slice().sort((a, b) => (a[sortKey] > b[sortKey] ? 1 : a[sortKey] < b[sortKey] ? -1 : 0) * sortDir);
  $("count").textContent = rows.length + " of " + DATA.length;
  $("rows").innerHTML = rows.slice(0, 400).map(r => {
    const links = Object.entries(r.pg).map(([k, p]) =>
      `<a href="books/${r.d}/${r.fn[k]}#page=${p}">${ED[k]} p.${p}</a>`).join("");
    return `<tr><td class="t">${esc(r.t)}<small>${esc(r.s)}${r.s && r.c ? " · " : ""}${esc(r.c)}</small></td>` +
      `<td>${esc(r.b)}<small>${esc(r.sec)}</small></td><td>${esc(r.k)}<small>${esc(r.m)}</small></td>` +
      `<td><span class="dots">${dots(r.p)}</span><small>${r.p}</small></td>` +
      `<td><span class="dots">${dots(r.q)}</span><small>${r.q}</small></td><td>${esc(r.f)}</td><td>${links}</td></tr>`;
  }).join("") + (rows.length > 400 ? `<tr><td colspan="7">… ${rows.length - 400} more — narrow the search.</td></tr>` : "");
}
for (const id of ["q", "book", "pmax", "smax"]) $(id).addEventListener("input", render);
document.querySelectorAll("th[data-k]").forEach(th => th.addEventListener("click", () => {
  const k = th.dataset.k; sortDir = sortKey === k ? -sortDir : 1; sortKey = k; render(); }));
render();
</script>
</body>
</html>
"""
