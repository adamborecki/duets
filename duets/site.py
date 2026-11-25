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
        for n, it in enumerate(b["items"]):
            rows.append({
                "i": n,
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
            f'<p>{html.escape(b["blurb"])}</p><div class="eds">{links}</div>'
            f'<p class="go"><a href="#find" data-book="{html.escape(b["title"], quote=True)}">List these duets ↓</a></p>'
            f'</article>')
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
    (path.parent / "play.html").write_text(_PLAYER, encoding="utf-8")
    print(f"wrote {path} ({total} duets in {len(books)} books)")
    return path


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Happy Birthday, Mom! · Piano Duets</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Great+Vibes&family=Playfair+Display:ital,wght@0,500;0,700;1,500&display=swap" rel="stylesheet">
<style>
:root { --bg:#fff6f4; --ink:#2a1216; --muted:#7d5a60; --line:#f0d3d6; --card:#fff; --accent:#b0122f; --dot:#d2143a;
  --crimson:#a50f2d; --cherry:#d2143a; --wine:#5e0a1c; --blush:#ffe3e6; --gold:#d9b36a; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#1c0c10; --ink:#fbe9ea; --muted:#c99aa1; --line:#4a1f28; --card:#2a1218; --accent:#ff8fa3; --dot:#ff6b85; --blush:#3a1820; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:16px/1.5 Georgia, "Iowan Old Style", "Palatino Linotype", serif; }
main { max-width:1100px; margin:0 auto; padding:24px 16px 80px; }
h1 { margin:0; }
h2 { margin:2.2em 0 .6em; font-size:1.35rem; border-bottom:1px solid var(--line); padding-bottom:.3em; }
.lede { color:var(--muted); max-width:46em; margin:1.2em auto 0; text-align:center; }
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
td a.pr { font-weight:600; }
td.t a { color:inherit; margin:0; white-space:normal; }
td.t a:hover { color:var(--accent); }
td.t .m { display:none; }
nav.jump { font:15px system-ui, sans-serif; margin:1em 0 0; display:flex; flex-wrap:wrap; gap:8px 10px; }
nav.jump a, button.lucky { border:1px solid var(--line); border-radius:999px; padding:6px 14px; background:var(--card);
  color:var(--accent); text-decoration:none; font:inherit; cursor:pointer; }
button.lucky { font:14px system-ui, sans-serif; border-radius:6px; padding:7px 12px; }
.book p.go { margin:.7em 0 0; font:13px system-ui, sans-serif; }
.book p.go a { color:var(--accent); text-decoration:none; }
button.more { display:block; width:100%; padding:12px; border:0; background:var(--card); color:var(--accent);
  font:14px system-ui, sans-serif; cursor:pointer; border-radius:0 0 8px 8px; }
@media (max-width: 760px) {
  thead { display:none; }
  table, tbody, tr, td { display:block; }
  tr { padding:10px 12px; border-bottom:1px solid var(--line); }
  td { border:0; padding:0; }
  td.x { display:none; }
  td.t { font-size:17px; }
  td.t .m { display:block; font:13px/1.5 system-ui, sans-serif; color:var(--muted); margin:3px 0 5px; }
  td.l a { display:inline-block; padding:4px 0; }
  td.l br { display:none; }
}
footer { margin-top:3em; color:var(--muted); font-size:.9rem; }
h2, .book h3 { font-family:"Playfair Display", Georgia, serif; }
h2 { color:var(--accent); border-bottom:2px solid var(--line); }
.book { border-radius:14px; box-shadow:0 2px 10px rgba(165,15,45,.07); transition:transform .2s, box-shadow .2s; border-top:4px solid var(--cherry); }
.book:hover { transform:translateY(-3px); box-shadow:0 8px 22px rgba(165,15,45,.16); }
.hero { background:radial-gradient(circle at 20% 0%, #e8244c 0, transparent 55%), linear-gradient(135deg, var(--cherry), var(--crimson) 45%, var(--wine));
  color:#fff; text-align:center; padding:54px 18px 60px; position:relative; overflow:hidden; }
.hero::after { content:""; position:absolute; left:0; right:0; bottom:-1px; height:26px; background:var(--bg);
  clip-path:ellipse(60% 100% at 50% 100%); }
.hero h1 { font:400 clamp(3rem, 10vw, 5.6rem)/1.05 "Great Vibes", "Snell Roundhand", cursive; margin:0; text-shadow:0 3px 14px rgba(60,0,15,.45); }
.hero p { margin:.7em auto 0; max-width:34em; font:italic 500 1.15rem/1.5 "Playfair Display", Georgia, serif; color:#ffe9ec; }
.hero .bow { font-size:2rem; display:block; margin-bottom:.2em; animation:bob 3s ease-in-out infinite; }
.hero .float { position:absolute; bottom:-30px; color:rgba(255,255,255,.28); animation:rise linear infinite; pointer-events:none; }
@keyframes bob { 50% { transform:translateY(-6px) rotate(-4deg); } }
@keyframes rise { to { transform:translateY(-420px) rotate(25deg); opacity:0; } }
nav.jump { justify-content:center; margin-top:1.6em; }
.hero nav.jump a { background:rgba(255,255,255,.14); border-color:rgba(255,255,255,.45); color:#fff; backdrop-filter:blur(3px); }
.hero nav.jump a:hover { background:#fff; color:var(--crimson); }
/* ---- the present ---- */
body.wrapped { overflow:hidden; }
#gift { position:fixed; inset:0; z-index:50; display:flex; flex-direction:column; align-items:center; justify-content:center;
  background:radial-gradient(circle at 50% 35%, #e3254b 0, var(--crimson) 45%, var(--wine) 100%); color:#fff; text-align:center;
  transition:opacity .9s ease, visibility .9s; padding:20px; }
#gift.gone { opacity:0; visibility:hidden; }
#gift canvas { position:absolute; inset:0; width:100%; height:100%; pointer-events:none; }
#gift .to { font:400 clamp(2.2rem, 8vw, 3.6rem)/1 "Great Vibes", cursive; margin:0 0 34px; text-shadow:0 2px 10px rgba(0,0,0,.3); }
#gift .hint { font:italic 1.05rem "Playfair Display", Georgia, serif; margin-top:30px; opacity:.9; animation:pulse 1.8s ease-in-out infinite; }
@keyframes pulse { 50% { opacity:.45; } }
#box { all:unset; cursor:pointer; position:relative; width:190px; height:170px; display:block; animation:wiggle 2.6s ease-in-out infinite; -webkit-tap-highlight-color:transparent; }
#box:focus-visible { outline:3px solid #fff; outline-offset:12px; border-radius:8px; }
@keyframes wiggle { 0%, 70%, 100% { transform:rotate(0); } 76% { transform:rotate(-4deg); } 82% { transform:rotate(4deg); } 88% { transform:rotate(-3deg); } 94% { transform:rotate(2deg); } }
#box .body { position:absolute; left:10px; right:10px; bottom:0; height:120px; border-radius:4px 4px 10px 10px;
  background:linear-gradient(90deg, #fff5f0, #ffe1dc); box-shadow:0 18px 40px rgba(40,0,10,.45); }
#box .lid { position:absolute; left:0; right:0; top:22px; height:36px; border-radius:6px; background:linear-gradient(90deg, #fff, #ffe9e4);
  box-shadow:0 4px 10px rgba(40,0,10,.3); transition:transform 1s cubic-bezier(.3,1.6,.5,1), opacity .9s .25s; transform-origin:20% 100%; }
#box .rv, #box .rh { position:absolute; background:linear-gradient(90deg, #c40f33, #ff3b5f, #c40f33); }
#box .rv { left:50%; width:28px; margin-left:-14px; top:22px; bottom:0; }
#box .bowk { position:absolute; left:50%; top:-6px; width:0; height:0; transition:transform 1s cubic-bezier(.3,1.6,.5,1), opacity .9s .25s; }
#box .bowk::before, #box .bowk::after { content:""; position:absolute; top:0; width:46px; height:34px; border:9px solid #ff3b5f; border-radius:50% 50% 50% 50% / 60% 60% 40% 40%; box-sizing:border-box; }
#box .bowk::before { right:0; transform:rotate(-18deg); } #box .bowk::after { left:0; transform:rotate(18deg); }
#gift.open #box { animation:none; }
#gift.open #box .lid, #gift.open #box .bowk { transform:translate(-40px, -230px) rotate(-38deg); opacity:0; }
#gift.open #box .body, #gift.open #box .rv { transition:transform .9s .35s ease-in, opacity .8s .35s; transform:translateY(60px) scale(.8); opacity:0; }
#gift.open .to, #gift.open .hint { transition:opacity .5s; opacity:0; animation:none; }
#gift .wrap { transition:opacity .4s 1s; }
#gift.open .wrap { opacity:0; pointer-events:none; position:absolute; }
#gift .wish { position:absolute; opacity:0; transform:scale(.6) translateY(30px); pointer-events:none; max-width:92vw; }
#gift.open .wish { opacity:1; transform:none; pointer-events:auto; transition:opacity 1s .7s, transform 1.2s .7s cubic-bezier(.2,1.5,.4,1); }
#gift .wish h2 { font:400 clamp(3.2rem, 13vw, 7rem)/1.05 "Great Vibes", "Snell Roundhand", cursive; margin:0; border:0; color:#fff; text-shadow:0 4px 18px rgba(50,0,12,.5); }
#gift .wish p { font:italic 500 clamp(1.05rem, 3.4vw, 1.4rem)/1.5 "Playfair Display", Georgia, serif; margin:.8em auto 0; max-width:26em; color:#ffe9ec; }
#gift .wish .hearts { font-size:1.5rem; letter-spacing:.5em; margin-top:.6em; color:#ffd0d8; }
#enter { margin-top:1.6em; font:600 1.1rem "Playfair Display", Georgia, serif; color:var(--crimson); background:#fff; border:0; border-radius:999px;
  padding:13px 34px; cursor:pointer; box-shadow:0 8px 24px rgba(40,0,10,.4); transition:transform .2s; }
#enter:hover { transform:scale(1.06); }
#again { border:1px solid rgba(255,255,255,.45); border-radius:999px; padding:6px 14px; background:rgba(255,255,255,.14); color:#fff; font:inherit; cursor:pointer; }
@media (prefers-reduced-motion: reduce) { #box, .hero .bow, .hero .float, #gift .hint { animation:none; } #gift *, #gift { transition-duration:.01s !important; transition-delay:0s !important; } }
</style>
</head>
<body class="wrapped">
<div id="gift" role="dialog" aria-label="A birthday present">
  <canvas id="confetti"></canvas>
  <div class="wrap">
    <p class="to">For Mom</p>
    <button id="box" aria-label="Open your present"><span class="body"></span><span class="rv"></span><span class="lid"></span><span class="bowk"></span></button>
    <p class="hint">Tap the present to open it</p>
  </div>
  <div class="wish">
    <h2>Happy Birthday, Mom!</h2>
    <p>__TOTAL__ piano duets for the two of us — hymns, carols, Bach, ragtime and the old songs. A lifetime of four hands at one piano.</p>
    <div class="hearts">♥ ♪ ♥</div>
    <button id="enter">Let’s play ♪</button>
  </div>
</div>
<header class="hero">
  <span class="bow">🎁</span>
  <h1>Happy Birthday, Mom!</h1>
  <p>__TOTAL__ piano duets for the two of us to play, with all my love.</p>
  <nav class="jump"><a href="#books">The books</a><a href="#find">Find a duet</a><a href="#" id="lucky1">🎲 Surprise us</a><button id="again" title="Open the present again">🎁 Open it again</button></nav>
</header>
<main>
<p class="lede">__TOTAL__ duets for one piano, four hands, in __NBOOKS__ books. Every piece comes in four
editions: facing pages for printing (Secondo on the left, Primo on the right, lines and bar numbers matching),
a printed full score, and two 16:10 screen editions for a laptop or tablet on the music stand.
Dots rate each seat from 1 (beginner) to 5 (late intermediate); chord symbols are printed over both parts.
<strong>▶ practice</strong> opens a piece on the music stand with a player that can sound either part while you
play the other.</p>

<h2 id="books">The books</h2>
<section class="books">
__CARDS__
</section>

<h2 id="find">Every duet</h2>
<div class="controls">
  <input id="q" type="search" placeholder="Search titles, tune names, composers…" aria-label="Search">
  <select id="book" aria-label="Book"><option value="">All books</option></select>
  <select id="pmax" aria-label="Primo level"><option value="9">Primo: any level</option><option value="1.5">Primo ≤ 1</option><option value="2.5">Primo ≤ 2</option><option value="3.5">Primo ≤ 3</option></select>
  <select id="smax" aria-label="Secondo level"><option value="9">Secondo: any level</option><option value="1.5">Secondo ≤ 1</option><option value="2.5">Secondo ≤ 2</option><option value="3.5">Secondo ≤ 3</option></select>
  <button class="lucky" id="lucky2" title="Open a random duet from the list below">🎲 Surprise us</button>
  <span class="count" id="count"></span>
</div>
<div class="tablewrap">
<table>
<thead><tr><th data-k="t">Title</th><th data-k="b">Book</th><th data-k="k">Key</th><th data-k="p">Primo</th><th data-k="q">Secondo</th><th data-k="f">Setting</th><th>Practice · open at page</th></tr></thead>
<tbody id="rows"></tbody>
</table>
<button class="more" id="more" hidden></button>
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
let sortKey = null, sortDir = 1, shown = 150, current = [];
const ED = {facing:"print", score:"score", screen:"screen", "screen-score":"screen score"};
function render() {
  const q = $("q").value.trim().toLowerCase(), book = $("book").value;
  const pmax = parseFloat($("pmax").value), smax = parseFloat($("smax").value);
  let rows = DATA.filter(r => (!book || r.b === book) && r.p <= pmax && r.q <= smax &&
    (!q || (r.t + " " + r.s + " " + r.c + " " + r.sec).toLowerCase().includes(q)));
  if (sortKey) rows = rows.slice().sort((a, b) => (a[sortKey] > b[sortKey] ? 1 : a[sortKey] < b[sortKey] ? -1 : 0) * sortDir);
  current = rows;
  $("count").textContent = rows.length + " of " + DATA.length;
  $("rows").innerHTML = rows.slice(0, shown).map(r => {
    const links = Object.entries(r.pg).map(([k, p]) =>
      `<a href="books/${r.d}/${r.fn[k]}#page=${p}">${ED[k]} p.${p}</a>`).join("");
    const play = `play.html?b=${r.d}&i=${r.i}`;
    return `<tr><td class="t"><a href="${play}">${esc(r.t)}</a><small>${esc(r.s)}${r.s && r.c ? " · " : ""}${esc(r.c)}</small>` +
      `<div class="m">${esc(r.b)} · ${esc(r.k)} · Primo <span class="dots">${dots(r.p)}</span> Secondo <span class="dots">${dots(r.q)}</span></div></td>` +
      `<td class="x">${esc(r.b)}<small>${esc(r.sec)}</small></td><td class="x">${esc(r.k)}<small>${esc(r.m)}</small></td>` +
      `<td class="x"><span class="dots">${dots(r.p)}</span><small>${r.p}</small></td>` +
      `<td class="x"><span class="dots">${dots(r.q)}</span><small>${r.q}</small></td><td class="x">${esc(r.f)}</td>` +
      `<td class="l"><a class="pr" href="${play}">▶ practice</a><br>${links}</td></tr>`;
  }).join("");
  $("more").hidden = rows.length <= shown;
  $("more").textContent = `Show ${Math.min(150, rows.length - shown)} more (${rows.length - shown} not shown)`;
}
function fresh() { shown = 150; render(); }
for (const id of ["q", "book", "pmax", "smax"]) $(id).addEventListener("input", fresh);
$("more").addEventListener("click", () => { shown += 150; render(); });
document.querySelectorAll("th[data-k]").forEach(th => th.addEventListener("click", () => {
  const k = th.dataset.k; sortDir = sortKey === k ? -sortDir : 1; sortKey = k; fresh(); }));
document.querySelectorAll("a[data-book]").forEach(a => a.addEventListener("click", () => {
  $("q").value = ""; $("book").value = a.dataset.book; fresh(); }));
function lucky(ev) {
  ev.preventDefault();
  const pool = current.length ? current : DATA, r = pool[Math.floor(Math.random() * pool.length)];
  location.href = `play.html?b=${r.d}&i=${r.i}`;
}
$("lucky1").addEventListener("click", lucky); $("lucky2").addEventListener("click", lucky);
render();

// ---- the present ----
(function () {
  const gift = $("gift"), cv = $("confetti"), cx = cv.getContext("2d"), hero = document.querySelector(".hero");
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const COL = ["#ffffff", "#ffd0d8", "#ff6b85", "#ff3b5f", "#f7d58b", "#ffe9ec"], SH = ["♥", "♪", "♫", "●", "✦", "♥"];
  for (let k = 0; k < 14; k++) {                      // notes and hearts drifting up the banner
    const f = document.createElement("span"); f.className = "float"; f.textContent = SH[k % 3];
    f.style.left = (4 + Math.random() * 92) + "%"; f.style.fontSize = (1 + Math.random() * 1.6) + "rem";
    f.style.animationDuration = (9 + Math.random() * 10) + "s"; f.style.animationDelay = (-Math.random() * 16) + "s";
    hero.appendChild(f);
  }
  let parts = [], raf = 0, until = 0;
  function size() { cv.width = innerWidth; cv.height = innerHeight; }
  function burst(n, x, y, up) {
    for (let k = 0; k < n; k++) { const a = up ? -Math.PI / 2 + (Math.random() - .5) * 2.1 : Math.random() * Math.PI * 2, v = 5 + Math.random() * 12;
      parts.push({x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - (up ? 5 : 0), r: Math.random() * 6, vr: (Math.random() - .5) * .3,
        s: 14 + Math.random() * 22, c: COL[k % COL.length], t: SH[k % SH.length], life: 1}); }
  }
  function frame(now) {
    cx.clearRect(0, 0, cv.width, cv.height);
    if (now < until && Math.random() < .35) parts.push({x: Math.random() * cv.width, y: -20, vx: (Math.random() - .5) * 2, vy: 2 + Math.random() * 3,
      r: 0, vr: (Math.random() - .5) * .2, s: 14 + Math.random() * 18, c: COL[parts.length % COL.length], t: SH[parts.length % SH.length], life: 1});
    parts = parts.filter(p => p.y < cv.height + 40 && p.life > 0);
    for (const p of parts) { p.vy += .22; p.vx *= .99; p.x += p.vx; p.y += p.vy; p.r += p.vr; if (now > until) p.life -= .012;
      cx.save(); cx.globalAlpha = Math.max(0, p.life); cx.translate(p.x, p.y); cx.rotate(p.r); cx.fillStyle = p.c;
      cx.font = p.s + "px Georgia, serif"; cx.textAlign = "center"; cx.fillText(p.t, 0, 0); cx.restore(); }
    if (parts.length || now < until) raf = requestAnimationFrame(frame);
  }
  function open() {
    if (gift.classList.contains("open")) return;
    gift.classList.add("open");
    if (!calm) { size(); const r = $("box").getBoundingClientRect(); burst(110, r.left + r.width / 2, r.top + 40, true);
      setTimeout(() => { burst(60, cv.width * .2, cv.height * .35); burst(60, cv.width * .8, cv.height * .35); }, 900);
      until = performance.now() + 6000; cancelAnimationFrame(raf); raf = requestAnimationFrame(frame); }
    setTimeout(() => $("enter").focus(), 1600);
  }
  function close() { gift.classList.add("gone"); document.body.classList.remove("wrapped"); until = 0;
    try { sessionStorage.setItem("duets-opened", "1"); } catch (e) {} }
  function wrap() { parts = []; gift.classList.remove("open", "gone"); document.body.classList.add("wrapped"); scrollTo(0, 0); }
  $("box").addEventListener("click", open); $("enter").addEventListener("click", close); $("again").addEventListener("click", wrap);
  addEventListener("resize", size);
  addEventListener("keydown", ev => { if (ev.key === "Escape" && !gift.classList.contains("gone")) close(); });
  let seen = false; try { seen = sessionStorage.getItem("duets-opened") === "1"; } catch (e) {}
  if (seen || location.hash) { gift.classList.add("gone"); document.body.classList.remove("wrapped"); }
})();
</script>
</body>
</html>
"""


_PLAYER = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Practice · Piano Duets</title>
<style>
:root { --bg:#fff6f4; --ink:#2a1216; --muted:#7d5a60; --line:#f0d3d6; --card:#fff; --accent:#b0122f; --on:#fff; --desk:#f3dcdf; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#1c0c10; --ink:#fbe9ea; --muted:#c99aa1; --line:#4a1f28; --card:#2a1218; --accent:#ff8fa3; --on:#1c0c10; --desk:#12070a; }
}
header { border-top:4px solid #d2143a; }
* { box-sizing:border-box; }
html, body { height:100%; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif;
  display:flex; flex-direction:column; }
header { padding:8px 14px 9px; border-bottom:1px solid var(--line); background:var(--card); }
.top { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 14px; }
.top a { color:var(--accent); text-decoration:none; white-space:nowrap; }
h1 { font:600 1.15rem/1.25 Georgia, serif; margin:0; }
.sub { color:var(--muted); font-size:.85rem; }
.row { display:flex; flex-wrap:wrap; align-items:center; gap:7px 14px; margin-top:7px; }
button { font:inherit; border:1px solid var(--line); background:var(--bg); color:var(--ink); border-radius:6px;
  padding:6px 12px; cursor:pointer; min-width:44px; }
button:disabled { opacity:.4; cursor:default; }
button.go { background:var(--accent); color:var(--on); border-color:var(--accent); font-weight:600; min-width:92px; }
label { display:inline-flex; align-items:center; gap:5px; white-space:nowrap; }
select, input { font:inherit; accent-color:var(--accent); }
select { border:1px solid var(--line); border-radius:6px; background:var(--bg); color:var(--ink); padding:5px 6px; max-width:100%; }
.seat { border:1px solid var(--line); border-radius:6px; padding:4px 9px; }
#bar { flex:1 1 200px; height:10px; background:var(--line); border-radius:5px; cursor:pointer; position:relative; min-width:120px; }
#fill { position:absolute; left:0; top:0; bottom:0; width:0; background:var(--accent); border-radius:5px; }
#pos, #pg { color:var(--muted); font-variant-numeric:tabular-nums; white-space:nowrap; }
main { flex:1 1 auto; min-height:300px; display:flex; background:var(--desk); position:relative; overflow:hidden; }
#stage { flex:1; overflow:auto; display:flex; justify-content:center; align-items:flex-start; gap:6px; padding:8px; }
#stage.fit { align-items:center; }
.sheet { background:#fff; box-shadow:0 1px 6px rgba(0,0,0,.35); display:none; overflow:hidden; flex:none; }
.sheet canvas { display:block; }
#more { display:none; }
@media (max-width: 720px) {
  header { padding:6px 10px 8px; }
  h1 { font-size:1rem; flex-basis:100%; }
  #lv { display:none; }
  #more { display:inline-block; }
  header:not(.open) .opt { display:none; }
  #stage { padding:4px; }
}
.turn { position:absolute; top:0; bottom:0; width:12%; min-width:44px; border:0; border-radius:0; background:transparent;
  color:transparent; font-size:2rem; }
.turn:hover:not(:disabled) { background:rgba(0,0,0,.06); color:var(--accent); }
#pgprev { left:0; } #pgnext { right:0; }
iframe { flex:1; border:0; width:100%; }
.note { padding:24px 16px; max-width:40em; }
.note a { color:var(--accent); }
</style>
</head>
<body>
<header>
  <div class="top">
    <a href="index.html">← All duets</a>
    <h1 id="title">Loading…</h1>
    <span class="sub" id="sub"></span>
    <span class="sub" id="lv"></span>
  </div>
  <div class="row">
    <button class="go" id="play" disabled>▶ Play</button>
    <button id="stop" title="Back to the start">⏮</button>
    <span class="seat"><label><input type="checkbox" id="p" checked> <span id="pn">Primo</span> sounds</label></span>
    <span class="seat"><label><input type="checkbox" id="s" checked> <span id="sn">Secondo</span> sounds</label></span>
    <label>Tempo <input type="range" id="rate" min="40" max="125" value="100" step="5"> <span id="bpm"></span></label>
    <button id="more" aria-label="More options" title="More options">⋯</button>
    <label class="opt"><input type="checkbox" id="click"> Metronome</label>
    <label class="opt"><input type="checkbox" id="count" checked> Count-in</label>
    <label class="opt"><input type="checkbox" id="loop"> Loop</label>
    <label class="opt" id="followbox" title="Turn the page automatically while the music plays"><input type="checkbox" id="follow" checked> Turn pages</label>
  </div>
  <div class="row">
    <div id="bar" title="Click to jump"><div id="fill"></div></div>
    <span id="pos"></span>
    <select id="ed" aria-label="Edition shown"></select>
    <select id="part" aria-label="Which part to show">
      <option value="both">Both parts</option><option value="p">Primo only</option><option value="s">Secondo only</option>
    </select>
    <span id="pg"></span>
    <a id="open" class="opt" target="_blank" rel="noopener" style="color:var(--accent)">Open PDF ↗</a>
    <button id="prev" title="Previous duet in this book">‹ duet</button>
    <button id="next" title="Next duet in this book">duet ›</button>
    <button id="full" class="opt" title="Full screen (F)" aria-label="Full screen">⛶</button>
  </div>
</header>
<main id="main">
  <div id="stage"><div class="sheet" id="s1"><canvas id="c1"></canvas></div><div class="sheet" id="s2"><canvas id="c2"></canvas></div></div>
  <button class="turn" id="pgprev" aria-label="Previous page">‹</button>
  <button class="turn" id="pgnext" aria-label="Next page">›</button>
</main>
<script src="vendor/pdfjs/pdf.min.js"></script>
<script>
const Q = new URLSearchParams(location.search), book = Q.get("b") || "", idx = parseInt(Q.get("i") || "0", 10);
const $ = id => document.getElementById(id);
const ED = {screen: "Screen · side by side", "screen-score": "Screen · full score", facing: "Print · facing pages", score: "Print · full score"};
const dots = v => { const n = Math.max(1, Math.min(5, Math.round(v))); return "●".repeat(n) + "○".repeat(5 - n); };
let item, nextItem, song, files = {}, events = [], beats = [], ctx, master, gains = {}, live = [], playing = false,
    timer = null, startAt = 0, startTick = 0, nextEv = 0, nextBeat = 0, raf = 0;
let doc = null, docUrl = "", sheets = [[]], view = 0, canFollow = false, seq = 0;

function fail(msg) {
  $("title").textContent = "Practice";
  $("main").innerHTML = '<div class="note"><p>' + msg + '</p><p><a href="index.html">Back to the catalog</a></p></div>';
}
if (location.protocol === "file:") {
  fail("The practice page has to load its data over the web. Open this site from GitHub Pages, or run " +
       "<code>python -m duets serve</code> in the repository and visit the address it prints. " +
       "(The PDFs in the books folder open fine straight from disk.)");
} else {
  Promise.all([fetch(`books/${book}/contents.json`).then(r => r.json()), fetch(`books/${book}/notes.json`).then(r => r.json())])
    .then(([c, n]) => setup(c, n)).catch(() => fail("Could not load that duet."));
}

function setup(c, n) {
  item = c.items[idx]; nextItem = c.items[idx + 1]; song = n.items[idx];
  if (!item || !song) return fail("That duet is not in this book.");
  document.title = item.title + " · Practice";
  $("title").textContent = item.title;
  $("sub").textContent = [item.subtitle, c.title].filter(Boolean).join(" · ");
  $("lv").textContent = `Primo ${dots(item.levels.p)}  Secondo ${dots(item.levels.s)}  ·  ${item.key}, ${item.meter}`;
  for (const [k, v] of Object.entries(c.layouts)) files[k] = v.path.split("/").pop();
  let pref = null; try { pref = localStorage.getItem("duets-edition"); } catch (e) {}
  for (const k of ["screen", "screen-score", "facing", "score"]) if (files[k]) {
    const o = document.createElement("option"); o.value = k; o.textContent = ED[k]; $("ed").appendChild(o);
  }
  if (pref && files[pref]) $("ed").value = pref;
  const names = song.names || {p: "Primo", s: "Secondo"};
  $("pn").textContent = names.p; $("sn").textContent = names.s;
  $("part").options[1].textContent = names.p + " only"; $("part").options[2].textContent = names.s + " only";
  let pp = null; try { pp = localStorage.getItem("duets-part"); } catch (e) {}
  if (pp === "p" || pp === "s") $("part").value = pp;
  $("prev").disabled = idx <= 0; $("next").disabled = idx >= c.items.length - 1;
  $("prev").onclick = () => location.search = `?b=${book}&i=${idx - 1}`;
  $("next").onclick = () => location.search = `?b=${book}&i=${idx + 1}`;
  build();
  $("play").disabled = false;
  draw();
  showPdf();
}

// ---- the page on the stand ---------------------------------------------------
// Secondo sits on the left: the left half of a screen page, the even pages of the print edition.
async function showPdf() {
  const k = $("ed").value, url = `books/${book}/${files[k]}`;
  $("open").href = `${url}#page=${item.pages[k]}`;
  if (!window.pdfjsLib) {                       // no renderer: let the browser show the PDF
    $("main").innerHTML = `<iframe title="Sheet music" src="${url}#page=${item.pages[k]}"></iframe>`;
    return;
  }
  pdfjsLib.GlobalWorkerOptions.workerSrc = "vendor/pdfjs/pdf.worker.min.js";
  try {
    if (url !== docUrl) {
      $("pg").textContent = "loading…";
      doc = await pdfjsLib.getDocument({url, rangeChunkSize: 131072, disableAutoFetch: true, disableStream: true}).promise;
      docUrl = url;
    }
  } catch (e) { return fail("Could not open the sheet music."); }
  const first = item.pages[k], last = nextItem ? Math.max(first, nextItem.pages[k] - 1) : doc.numPages;
  const split = k === "screen" || k === "facing";
  $("part").disabled = !split;
  const part = split ? $("part").value : "both", wide = $("stage").clientWidth > 900;
  sheets = []; canFollow = !!(song.pb && song.pb[k]);
  if (k === "screen" && part !== "both") for (let n = first; n <= last; n++) sheets.push([{n, half: part === "s" ? 0 : 1}]);
  else if (k === "facing" && part !== "both") for (let n = first + (part === "p" ? 1 : 0); n <= last; n += 2) sheets.push([{n}]);
  else if (k === "facing" && wide) for (let n = first; n <= last; n += 2) sheets.push(n < last ? [{n}, {n: n + 1}] : [{n}]);
  else { for (let n = first; n <= last; n++) sheets.push([{n}]); if (k === "facing") canFollow = false; }
  if (!sheets.length) sheets = [[{n: first}]];
  $("followbox").style.display = canFollow ? "" : "none";
  view = 0;
  if (canFollow && (playing || startTick > 0)) view = pageAt(now());
  render();
}
async function render() {
  const my = ++seq, stage = $("stage"), pad = stage.clientWidth > 720 ? 16 : 8,
        W = stage.clientWidth - pad, H = stage.clientHeight - pad, dpr = Math.min(window.devicePixelRatio || 1, 2),
        cur = sheets[view] || [], n = cur.length;
  let fit = true;
  for (let j = 0; j < 2; j++) {
    const box = $("s" + (j + 1)), cv = $("c" + (j + 1)), sh = cur[j];
    if (!sh) { box.style.display = "none"; continue; }
    const page = await doc.getPage(sh.n);
    if (my !== seq) return;
    const base = page.getViewport({scale: 1}), halves = sh.half === undefined ? 1 : 2,
          visW = base.width / halves, availW = (W - (n - 1) * 6) / n;
    let scale = Math.min(availW / visW, H / base.height);
    if (n === 1 && base.height > visW && H < W) { scale = Math.min(availW, 1050) / visW; fit = false; }   // tall page, wide screen: scroll
    const vp = page.getViewport({scale: scale * dpr});
    const off = document.createElement("canvas");
    off.width = Math.floor(vp.width); off.height = Math.floor(vp.height);
    await page.render({canvasContext: off.getContext("2d"), viewport: vp}).promise;
    if (my !== seq) return;
    const w = Math.floor(off.width / halves);
    cv.width = w; cv.height = off.height;
    cv.getContext("2d").drawImage(off, sh.half ? off.width - w : 0, 0, w, off.height, 0, 0, w, off.height);
    cv.style.width = box.style.width = Math.floor(w / dpr) + "px";
    cv.style.height = box.style.height = Math.floor(off.height / dpr) + "px";
    box.style.display = "block";
  }
  stage.classList.toggle("fit", fit);
  stage.scrollTop = 0;
  $("pg").textContent = `page ${view + 1} / ${sheets.length}`;
  $("pgprev").disabled = view <= 0; $("pgnext").disabled = view >= sheets.length - 1;
}
function turn(d) { const v = Math.max(0, Math.min(sheets.length - 1, view + d)); if (v !== view) { view = v; render(); } }
$("pgprev").onclick = () => turn(-1); $("pgnext").onclick = () => turn(1);
$("ed").onchange = () => { try { localStorage.setItem("duets-edition", $("ed").value); } catch (e) {} showPdf(); };
$("part").onchange = () => { try { localStorage.setItem("duets-part", $("part").value); } catch (e) {} showPdf(); };
$("more").onclick = () => { document.querySelector("header").classList.toggle("open"); if (doc) setTimeout(render, 50); };
let rz = 0, lastW = 0;
window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => { if (doc) { const v = view; showPdf().then(() => { if (!canFollow || !playing) { view = Math.min(v, sheets.length - 1); render(); } }); } }, 200); });
function pageAt(tick) {                          // which view holds the bar sounding at this tick
  const pb = song.pb[$("ed").value];
  let bar = 0; for (let j = 0; j < song.bars.length; j++) if (song.bars[j] <= tick + song.beat * 0.5) bar = j;
  const written = song.ord ? song.ord[bar] : bar;
  return Math.min(sheets.length - 1, pb.filter(x => x < written).length);   // pb: last bar of each page
}
function followPage(tick) {
  if (!canFollow || !$("follow").checked) return;
  const v = pageAt(tick);
  if (v !== view) { view = v; render(); }
}

// ---- timing -------------------------------------------------------------------
const TPQ = 24;
let segs = [];
function build() {
  events = [];
  for (const [hand, arr] of Object.entries(song.h)) {
    const part = hand[0] === "p" && hand !== "ped" ? "p" : "s";
    for (let k = 0; k < arr.length; k += 3) {
      let t = arr[k], d = arr[k + 1];
      if (song.swing) {                      // long-short eighths
        const pos = t % TPQ;
        if (pos === 12) { t += 4; d = Math.max(4, d - 4); } else if (pos === 0 && d === 12) d = 16;
      }
      events.push({t, d, m: arr[k + 2], part});
    }
  }
  events.sort((a, b) => a.t - b.t);
  const compound = song.ts[1] === 8 && song.ts[0] % 3 === 0 && song.ts[0] > 3;
  song.beat = TPQ * 4 / song.ts[1] * (compound ? 3 : 1);
  beats = [];
  song.bars.forEach((b, k) => {
    const end = k + 1 < song.bars.length ? song.bars[k + 1] : song.len;
    const from = (k === 0 && song.pick) ? b + (song.pick % song.beat) : b;
    for (let t = from; t < end - 1; t += song.beat) beats.push({t, strong: t === b});
  });
  segs = [{tick: 0, sec: 0, qpm: song.q}];
  for (const [tick, qpm] of song.tm) {
    const lastSeg = segs[segs.length - 1];
    segs.push({tick, sec: lastSeg.sec + (tick - lastSeg.tick) / TPQ * 60 / lastSeg.qpm, qpm});
  }
  showBpm();
}
const rate = () => parseInt($("rate").value, 10) / 100;
function secOf(tick) {
  let s = segs[0];
  for (const g of segs) if (g.tick <= tick) s = g;
  return (s.sec + (tick - s.tick) / TPQ * 60 / s.qpm) / rate();
}
function tickOf(sec) {
  sec *= rate();
  let s = segs[0];
  for (const g of segs) if (g.sec <= sec) s = g;
  return s.tick + (sec - s.sec) * s.qpm / 60 * TPQ;
}
function showBpm() { $("bpm").textContent = Math.round(song.q / (song.beat / TPQ) * rate()) + " bpm"; }

// ---- sound --------------------------------------------------------------------
function audio() {
  if (ctx) return;
  ctx = new (window.AudioContext || window.webkitAudioContext)();
  master = ctx.createDynamicsCompressor(); master.connect(ctx.destination);
  for (const k of ["p", "s", "c"]) { gains[k] = ctx.createGain(); gains[k].connect(master); }
  setGains();
}
function setGains() {
  if (!ctx) return;
  gains.p.gain.value = $("p").checked ? 0.9 : 0;
  gains.s.gain.value = $("s").checked ? 0.8 : 0;
  gains.c.gain.value = 0.5;
}
function tone(midi, when, dur, part) {
  const f = 440 * Math.pow(2, (midi - 69) / 12), g = ctx.createGain(), o = ctx.createOscillator(), o2 = ctx.createOscillator(),
        g2 = ctx.createGain(), peak = 0.16 * Math.min(1, 1.25 - (midi - 36) / 120), hold = Math.max(dur, 0.08);
  o.type = "triangle"; o.frequency.value = f; o2.type = "sine"; o2.frequency.value = f * 2; g2.gain.value = 0.22;
  const decay = Math.max(0.5, 3.2 - (midi - 30) / 28);          // low strings ring longer
  g.gain.setValueAtTime(0.0001, when);
  g.gain.exponentialRampToValueAtTime(peak, when + 0.008);
  g.gain.exponentialRampToValueAtTime(Math.max(peak * Math.exp(-hold / decay * 2.2), 0.0002), when + hold);
  g.gain.exponentialRampToValueAtTime(0.0001, when + hold + 0.14);
  o.connect(g); o2.connect(g2); g2.connect(g); g.connect(gains[part]);
  o.start(when); o2.start(when); o.stop(when + hold + 0.16); o2.stop(when + hold + 0.16);
  live.push({o, o2, g, end: when + hold + 0.2});
}
function tick(when, strong) {
  const o = ctx.createOscillator(), g = ctx.createGain();
  o.frequency.value = strong ? 1568 : 1047; g.gain.setValueAtTime(strong ? 0.5 : 0.3, when);
  g.gain.exponentialRampToValueAtTime(0.0001, when + 0.05);
  o.connect(g); g.connect(gains.c); o.start(when); o.stop(when + 0.06);
  live.push({o, o2: null, g, end: when + 0.1});
}
function hush() {
  const t = ctx ? ctx.currentTime : 0;
  for (const v of live) { try { v.g.gain.cancelScheduledValues(t); v.g.gain.setValueAtTime(0.0001, t); v.o.stop(t + 0.02); if (v.o2) v.o2.stop(t + 0.02); } catch (e) {} }
  live = [];
}

// ---- transport ------------------------------------------------------------------
function start(countIn) {
  audio(); ctx.resume();
  if (startTick >= song.len - 1) startTick = 0;
  let lead = 0.12;
  if (countIn && $("count").checked) {
    const beatSec = song.beat / TPQ * 60 / segs[0].qpm / rate();
    const barTicks = TPQ * 4 * song.ts[0] / song.ts[1], perBar = Math.max(1, Math.round(barTicks / song.beat));
    const pickBeats = startTick === 0 && song.pick ? song.pick / song.beat : 0;
    const n = Math.max(1, perBar - Math.floor(pickBeats + 1e-6) % perBar);
    for (let k = 0; k < n; k++) tick(ctx.currentTime + lead + k * beatSec, k === 0);
    lead += n * beatSec - (pickBeats % 1) * beatSec;
  }
  startAt = ctx.currentTime + lead - secOf(startTick);
  nextEv = events.findIndex(e => e.t >= startTick); if (nextEv < 0) nextEv = events.length;
  nextBeat = beats.findIndex(b => b.t >= startTick); if (nextBeat < 0) nextBeat = beats.length;
  playing = true; $("play").textContent = "⏸ Pause";
  timer = setInterval(pump, 40); pump(); cancelAnimationFrame(raf); raf = requestAnimationFrame(draw);
}
function pump() {
  const horizon = ctx.currentTime + 0.3;
  while (nextEv < events.length && startAt + secOf(events[nextEv].t) < horizon) {
    const e = events[nextEv++], when = Math.max(startAt + secOf(e.t), ctx.currentTime);
    tone(e.m, when, secOf(e.t + e.d) - secOf(e.t), e.part);
  }
  while (nextBeat < beats.length && startAt + secOf(beats[nextBeat].t) < horizon) {
    const b = beats[nextBeat++];
    if ($("click").checked) tick(Math.max(startAt + secOf(b.t), ctx.currentTime), b.strong);
  }
  live = live.filter(v => v.end > ctx.currentTime);
  if (ctx.currentTime > startAt + secOf(song.len) + 0.4) {
    pause(); startTick = 0;
    if ($("loop").checked) start(true); else draw();
  }
}
function now() { return playing ? Math.max(0, Math.min(song.len, tickOf(ctx.currentTime - startAt))) : startTick; }
function pause() {
  if (!playing) return;
  startTick = now(); playing = false; clearInterval(timer); hush(); $("play").textContent = "▶ Play";
}
function draw() {
  if (!song) return;
  const t = now();
  $("fill").style.width = (song.len ? t / song.len * 100 : 0).toFixed(1) + "%";
  let bar = 0; for (let k = 0; k < song.bars.length; k++) if (song.bars[k] <= t + 0.01) bar = k;
  $("pos").textContent = `bar ${bar + 1} / ${song.bars.length}`;
  if (playing) { if (doc) followPage(t); raf = requestAnimationFrame(draw); }
}
function resume() { const was = playing; if (was) pause(); return was; }
$("play").onclick = () => playing ? pause() : start(true);
$("stop").onclick = () => { pause(); startTick = 0; draw(); if (doc && view) { view = 0; render(); } };
$("p").onchange = $("s").onchange = setGains;
$("rate").oninput = () => { const was = resume(); showBpm(); if (was) start(false); };
$("bar").onclick = ev => {
  const r = $("bar").getBoundingClientRect(), f = Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width));
  let snap = 0; for (const b of song.bars) if (b <= f * song.len) snap = b;
  const was = resume(); startTick = snap; draw(); if (doc) followPage(snap);
  if (was) start(false);
};
// keep the screen awake on the music stand, and offer the whole screen to the page
let lock = null;
async function awake() {
  try { if (navigator.wakeLock && !lock && document.visibilityState === "visible") {
    lock = await navigator.wakeLock.request("screen"); lock.addEventListener("release", () => { lock = null; }); } } catch (e) {}
}
document.addEventListener("visibilitychange", awake);
document.addEventListener("pointerdown", awake, {once: true});
awake();
function fullscreen() {
  const el = document.documentElement;
  if (document.fullscreenElement) document.exitFullscreen();
  else if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
}
if (!document.documentElement.requestFullscreen) $("full").style.display = "none";
// after a click or tap, hand the keyboard back to the page so Space and the arrows keep working
document.addEventListener("pointerup", ev => {
  const t = ev.target.closest && ev.target.closest("button, input[type=checkbox]");
  if (t) setTimeout(() => t.blur(), 0);
});
$("full").onclick = fullscreen;
document.addEventListener("keydown", ev => {
  const tag = document.activeElement.tagName;
  if (/^(INPUT|SELECT|BUTTON|A)$/.test(tag) || ev.ctrlKey || ev.metaKey || ev.altKey) return;   // Tab users keep the native keys
  if (ev.key === "f" || ev.key === "F") { fullscreen(); return; }
  if (ev.code === "Space") { ev.preventDefault(); $("play").click(); }
  else if (ev.key === "ArrowRight" || ev.key === "PageDown") { ev.preventDefault(); turn(1); }
  else if (ev.key === "ArrowLeft" || ev.key === "PageUp") { ev.preventDefault(); turn(-1); }
});
</script>
</body>
</html>
"""
