"""What to play this Sunday: the church year and hymn suggestions.

Dates follow the Western calendar as used in Lutheran churches in North
America (three-year lectionary; Transfiguration on the last Sunday after
the Epiphany; Reformation and All Saints observed on the nearest Sundays).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

D = dt.date


def easter(year: int) -> D:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return D(year, month, day)


def advent1(year: int) -> D:
    xmas = D(year, 12, 25)
    # the fourth Sunday before Christmas
    last_sunday = xmas - dt.timedelta(days=(xmas.weekday() + 1) % 7 or 7)
    return last_sunday - dt.timedelta(weeks=3)


def thanksgiving(year: int) -> D:
    first = D(year, 11, 1)
    first_thu = first + dt.timedelta(days=(3 - first.weekday()) % 7)
    return first_thu + dt.timedelta(weeks=3)


def lectionary_year(date: D) -> str:
    start = advent1(date.year)
    y = date.year + 1 if date >= start else date.year
    return "ABC"[(y - 2023) % 3]          # Advent 2022 began Year A


@dataclass
class Day:
    date: D
    name: str
    season: str
    tags: list = field(default_factory=list)
    picks: list = field(default_factory=list)      # preferred slugs (hymn of the day and friends)


# hymn-of-the-day style suggestions, by day name (slugs from the library)
PICKS = {
    "First Sunday of Advent": ["savior-of-the-nations-come", "bach-savior-of-the-nations-come",
                               "wake-awake-for-night-is-flying", "o-lord-how-shall-i-meet-thee",
                               "the-advent-of-our-god", "come-thou-long-expected-jesus"],
    "Second Sunday of Advent": ["on-jordans-bank-the-baptists-cry", "comfort-comfort-ye-my-people",
                                "bach-comfort-comfort-ye-my-people", "hark-the-glad-sound", "the-king-shall-come"],
    "Third Sunday of Advent": ["hark-the-glad-sound", "comfort-comfort-ye-my-people", "o-come-o-come-emmanuel",
                               "bach-wake-awake-for-night-is-flying", "rejoice-o-pilgrim-throng"],
    "Fourth Sunday of Advent": ["o-come-o-come-emmanuel", "gabriels-message", "lo-how-a-rose-eer-blooming",
                                "bach-savior-of-the-nations-come-2", "of-the-fathers-love-begotten"],
    "Christmas Eve": ["silent-night", "from-heaven-above", "o-little-town-of-bethlehem", "away-in-a-manger",
                      "lo-how-a-rose-eer-blooming", "o-come-all-ye-faithful"],
    "Christmas Day": ["joy-to-the-world", "hark-the-herald-angels-sing", "of-the-fathers-love-begotten",
                      "bach-from-heaven-above-to-earth-i-come", "angels-we-have-heard-on-high",
                      "bach-break-forth-o-beauteous-heavenly-light"],
    "Epiphany": ["bach-o-morning-star-how-fair-and-bright", "as-with-gladness-men-of-old",
                 "we-three-kings-of-orient-are", "the-star-proclaims-the-king-is-here"],
    "Transfiguration": ["o-wondrous-type-o-vision-fair", "tis-good-lord-to-be-here", "beautiful-savior"],
    "Ash Wednesday": ["savior-when-in-dust-to-thee", "bach-from-depths-of-woe-i-cry-to-thee",
                      "out-of-the-deep-i-cry-to-thee"],
    "Palm Sunday": ["all-glory-laud-and-honor", "hosanna-loud-hosanna", "bach-all-glory-laud-and-honor"],
    "Maundy Thursday": ["twas-on-that-dark-that-doleful-night", "bach-soul-adorn-thyself-with-gladness",
                        "thou-who-at-thy-first-eucharist"],
    "Good Friday": ["o-sacred-head-now-wounded", "bach-o-sacred-head-now-wounded", "were-you-there",
                    "stricken-smitten-and-afflicted", "go-to-dark-gethsemane",
                    "bach-o-dearest-jesus-what-law-hast-thou-broken"],
    "Easter Day": ["jesus-christ-is-risen-today", "christ-the-lord-is-risen-today",
                   "christ-jesus-lay-in-deaths-strong-bands", "bach-christ-jesus-lay-in-death-s-strong-bands",
                   "i-know-that-my-redeemer-lives", "the-strife-is-oer-the-battle-done"],
    "Ascension": ["see-the-lord-ascends-in-triumph", "crown-him-with-many-crowns", "alleluia-sing-to-jesus"],
    "Pentecost": ["come-holy-spirit-lord-our-god", "bach-come-holy-ghost-god-and-lord",
                  "we-now-implore-god-the-holy-ghost", "holy-ghost-with-light-divine", "o-holy-spirit-enter-in"],
    "Holy Trinity": ["holy-holy-holy", "bach-all-glory-be-to-god-on-high", "we-all-believe-in-one-true-god",
                     "god-the-father-be-our-stay", "holy-god-we-praise-thy-name"],
    "Reformation Sunday": ["a-mighty-fortress-is-our-god", "bach-a-mighty-fortress-is-our-god",
                           "salvation-unto-us-has-come", "lord-keep-us-steadfast-in-thy-word",
                           "dear-christians-one-and-all-rejoice", "built-on-the-rock"],
    "All Saints Sunday": ["behold-a-host-arrayed-in-white", "jerusalem-the-golden", "for-all-the-saints"],
    "Christ the King": ["crown-him-with-many-crowns", "all-hail-the-power-of-jesus-name",
                        "wake-awake-for-night-is-flying", "the-day-is-surely-drawing-near",
                        "beautiful-savior"],
    "Thanksgiving Day": ["now-thank-we-all-our-god", "come-ye-thankful-people-come", "we-gather-together",
                         "for-the-beauty-of-the-earth", "praise-to-the-lord-the-almighty",
                         "bach-now-thank-we-all-our-god", "simple-gifts"],
}
SEASON_TAGS = {
    "Advent": ["advent"], "Christmas": ["christmas"], "Epiphany": ["epiphany", "praise"],
    "Lent": ["lent", "confession", "comfort"], "Holy Week": ["good-friday", "lent", "maundy-thursday"],
    "Easter": ["easter"], "Pentecost": ["pentecost"], "Time after Pentecost": ["praise", "trust", "word", "church"],
    "End of the Church Year": ["end-times", "heaven"], "Thanksgiving": ["thanksgiving"],
}
ORD = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth"]


def day_for(date: D) -> Day:
    """The observance on a given date (a Sunday, or a principal weekday feast)."""
    y = date.year
    e = easter(y)
    a1 = advent1(y)
    if date == thanksgiving(y):
        return Day(date, "Thanksgiving Day", "Thanksgiving", ["thanksgiving"])
    if date == D(y, 12, 24):
        return Day(date, "Christmas Eve", "Christmas", ["christmas"])
    if date == D(y, 12, 25):
        return Day(date, "Christmas Day", "Christmas", ["christmas"])
    if date == D(y, 1, 6):
        return Day(date, "Epiphany", "Epiphany", ["epiphany"])
    if date >= a1 and date < D(y, 12, 24):
        n = (date - a1).days // 7
        return Day(date, f"{ORD[n]} Sunday of Advent", "Advent", ["advent"])
    if date >= D(y, 12, 26) or date < D(y, 1, 6):
        return Day(date, "Sunday after Christmas", "Christmas", ["christmas"])
    ash = e - dt.timedelta(days=46)
    transfig = ash - dt.timedelta(days=3)
    if date == transfig:
        return Day(date, "Transfiguration", "Epiphany", ["transfiguration", "epiphany"])
    if date < ash:
        first = D(y, 1, 6) + dt.timedelta(days=(6 - D(y, 1, 6).weekday()) % 7 or 7)
        n = (date - first).days // 7
        if n == 0:
            return Day(date, "Baptism of Our Lord", "Epiphany", ["epiphany", "baptism"])
        return Day(date, f"{ORD[min(n, 9)]} Sunday after the Epiphany", "Epiphany", ["epiphany", "praise"])
    if date == ash:
        return Day(date, "Ash Wednesday", "Lent", ["lent", "confession"])
    if date < e - dt.timedelta(days=7):
        n = (date - ash).days // 7
        return Day(date, f"{ORD[n]} Sunday in Lent", "Lent", ["lent"])
    if date == e - dt.timedelta(days=7):
        return Day(date, "Palm Sunday", "Holy Week", ["palm-sunday", "lent"])
    if date == e - dt.timedelta(days=3):
        return Day(date, "Maundy Thursday", "Holy Week", ["maundy-thursday", "communion"])
    if date == e - dt.timedelta(days=2):
        return Day(date, "Good Friday", "Holy Week", ["good-friday", "lent"])
    if date < e:
        return Day(date, "Holy Week", "Holy Week", ["lent", "good-friday"])
    if date == e:
        return Day(date, "Easter Day", "Easter", ["easter"])
    if date == e + dt.timedelta(days=39):
        return Day(date, "Ascension", "Easter", ["ascension", "easter"])
    pent = e + dt.timedelta(days=49)
    if date < pent:
        n = (date - e).days // 7
        return Day(date, f"{ORD[n]} Sunday of Easter", "Easter", ["easter"] + (["ascension"] if n == 6 else []))
    if date == pent:
        return Day(date, "Pentecost", "Pentecost", ["pentecost"])
    if date == pent + dt.timedelta(days=7):
        return Day(date, "Holy Trinity", "Pentecost", ["trinity"])
    ck = a1 - dt.timedelta(days=7)
    if date == ck:
        return Day(date, "Christ the King", "End of the Church Year", ["end-times", "praise"])
    oct31 = D(y, 10, 31)
    ref = oct31 - dt.timedelta(days=(oct31.weekday() + 1) % 7)
    if date == ref:
        return Day(date, "Reformation Sunday", "Time after Pentecost", ["reformation"])
    nov1 = D(y, 11, 1)
    saints = nov1 + dt.timedelta(days=(6 - nov1.weekday()) % 7)
    if date == saints:
        return Day(date, "All Saints Sunday", "End of the Church Year", ["heaven", "church", "end-times"])
    n = (date - pent).days // 7
    season = "End of the Church Year" if date > saints else "Time after Pentecost"
    tags = ["end-times", "trust"] if season.startswith("End") else ["praise", "trust", "word", "church"]
    return Day(date, f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')} Sunday after Pentecost",
               season, tags)


def next_sunday(today: D) -> D:
    return today + dt.timedelta(days=(6 - today.weekday()) % 7)


def upcoming(start: D, weeks: int = 8) -> list:
    """Sundays (and principal feasts in between) from ``start`` on."""
    out = []
    first = next_sunday(start)
    end = first + dt.timedelta(weeks=weeks - 1)
    d = start
    while d <= end:
        special = d in (thanksgiving(d.year), D(d.year, 12, 24), D(d.year, 12, 25), D(d.year, 1, 6)) \
            or d in (easter(d.year) - dt.timedelta(days=46), easter(d.year) - dt.timedelta(days=3),
                     easter(d.year) - dt.timedelta(days=2), easter(d.year) + dt.timedelta(days=39))
        if d.weekday() == 6 or special:
            out.append(day_for(d))
        d += dt.timedelta(days=1)
    return out


def suggest(day: Day, tunes: list, count: int = 6) -> list:
    """Tunes for a day: the listed picks first, then others carrying the day's tags."""
    by = {t.slug: t for t in tunes}
    out = [by[s] for s in PICKS.get(day.name, []) if s in by]
    pool = [t for t in tunes if t.category == "hymn" and t not in out and set(day.tags) & set(t.tags)]
    # most specific first: tunes sharing the first (most specific) tag
    pool.sort(key=lambda t: (day.tags[0] not in t.tags, "bach" in t.tags, t.title))
    for t in pool:
        if len(out) >= count:
            break
        out.append(t)
    return out[:count]


def cmd_sunday(args):
    from pathlib import Path
    from .library import load_library
    start = D.fromisoformat(args.date) if args.date else D.today()
    tunes = load_library()
    days = upcoming(start, args.weeks)
    entries = []
    for day in days:
        picks = suggest(day, tunes)
        print(f"\n{day.date:%A, %B %-d, %Y} — {day.name} (Year {lectionary_year(day.date)})")
        for t in picks:
            extra = f"  [{t.tune_name}]" if t.tune_name and t.collection != "bach-chorales" else ""
            print(f"   {t.title}{extra}   →  python -m duets make {t.slug}")
        entries.append((day, picks))
    if args.build:
        from .books import BookDef, build_book, rotate, unique
        from .catalog import Entry

        def select(_tunes):
            e = []
            for k, (day, picks) in enumerate(entries):
                e += rotate(picks[:4], f"{day.name} · {day.date:%b %-d}", k,
                            flavors=["chorale", "setting-easy", "chorale-octaves", "easy-primo", "setting",
                                     "chorale-easy"])
            return unique(e)

        first = days[0].date
        book = BookDef(f"sundays-{first.isoformat()}", f"Duets for the Coming Sundays",
                       f"{days[0].name} to {days[-1].name}, {first:%B %Y}",
                       "Hymns of the day and seasonal favourites for the weeks ahead.", select)
        from .cli import _layouts
        build_book(book, layouts=_layouts(args.layout), paper=args.paper,
                   outdir=Path(args.output) if args.output else None)
