#!/usr/bin/env python3
"""Import a selection of J. S. Bach's four-part chorales into
``library/bach-chorales`` from the music21 corpus (``pip install music21``).

    python tools/import_bach_chorales.py

The scores are public-domain encodings distributed with music21; the chorale
melodies and Bach's harmonisations are of course long out of copyright.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from duets import harmony as H                                      # noqa: E402
from duets.abc import irregular_bars, parse_abc                     # noqa: E402
from duets.abcwrite import write_abc                                # noqa: E402
from duets.library import slugify, tune_from_abc, validate          # noqa: E402
from duets.model import Ev, F, TBar, Tune, merge_ties, total        # noqa: E402
from duets.mxl import infer_minor, read_musicxml_parts              # noqa: E402

# German title (start of) | English title ('' = keep German) | tags
TABLE = """
Nun komm, der Heiden Heiland | Savior of the Nations, Come | advent
Wachet auf, ruft uns die Stimme | Wake, Awake, for Night Is Flying | advent end-times
Wie soll ich dich empfangen | O Lord, How Shall I Meet You | advent
Gottes Sohn ist kommen | Once He Came in Blessing | advent
Freu dich sehr, o meine Seele | Comfort, Comfort Ye My People | advent
Vom Himmel hoch, da komm ich her | From Heaven Above to Earth I Come | christmas
Gelobet seist du, Jesu Christ | We Praise You, Jesus, at Your Birth | christmas
Lobt Gott, ihr Christen, allzugleich | Praise God the Lord, Ye Sons of Men | christmas
In dulci jubilo | In dulci jubilo | christmas
Puer natus in Bethlehem | A Child Is Born in Bethlehem | christmas
Ermuntre dich, mein schwacher Geist | Break Forth, O Beauteous Heavenly Light | christmas
Christum wir sollen loben schon | From East to West | christmas
Der Tag, der ist so freudenreich | | christmas
Uns ist ein Kindlein heut geborn | Unto Us a Child Is Born | christmas
Wir Christenleut | | christmas
Wie schön leuchtet der Morgenstern | O Morning Star, How Fair and Bright | epiphany
Herr Christ, der einig Gotts Sohn | The Only Son from Heaven | epiphany
Das alte Jahr vergangen ist | The Old Year Now Hath Passed Away | newyear
Jesu, nun sei gepreiset | Jesus, Now Be Praised | newyear
O Haupt voll Blut und Wunden | O Sacred Head, Now Wounded | lent good-friday
Herzlich tut mich verlangen | O Sacred Head, Now Wounded | lent good-friday
Befiehl du deine Wege | Commit Thou All Thy Griefs (Passion Chorale) | lent trust
Herzliebster Jesu, was hast du verbrochen | O Dearest Jesus, What Law Hast Thou Broken | lent good-friday
O Lamm Gottes, unschuldig | Lamb of God, Pure and Holy | lent
Christe, du Lamm Gottes | O Christ, Thou Lamb of God | lent
O Welt, ich muss dich lassen | Upon the Cross Extended (Innsbruck) | lent evening
Nun ruhen alle Wälder | Now Rest Beneath Night's Shadow | evening
O Welt, sieh hier dein Leben | Upon the Cross Extended | lent good-friday
Jesu Leiden, Pein und Tod | Jesus, I Will Ponder Now | lent
Christus, der uns selig macht | Christ, Who Makes Us Blessed | lent good-friday
O Mensch, bewein dein Sünde groß | O Man, Bewail Thy Grievous Sin | lent
Aus tiefer Not schrei ich zu dir | From Depths of Woe I Cry to Thee | lent confession
Erbarm dich mein, o Herre Gott | Have Mercy, Lord | lent confession
Ach Gott und Herr | Alas, My God | confession
Christ lag in Todesbanden | Christ Jesus Lay in Death's Strong Bands | easter
Christ ist erstanden | Christ Is Arisen | easter
Erschienen ist der herrlich Tag | The Glorious Day Has Dawned | easter
Jesus Christus, unser Heiland | Jesus Christ, Our Blessed Savior | easter communion
Heut triumphieret Gottes Sohn | Today in Triumph Christ Arose | easter
Erstanden ist der heilig Christ | The Holy Christ Is Risen | easter
Jesus, meine Zuversicht | Jesus Christ, My Sure Defense | easter
Komm, heiliger Geist, Herre Gott | Come, Holy Ghost, God and Lord | pentecost
Komm, Gott Schöpfer, heiliger Geist | Come, God Creator, Holy Ghost | pentecost
Nun bitten wir den heiligen Geist | We Now Implore God the Holy Ghost | pentecost
Zeuch ein zu deinen Toren | O Enter, Lord, Thy Temple | pentecost
Allein Gott in der Höh sei Ehr | All Glory Be to God on High | trinity praise
Wir glauben all an einen Gott | We All Believe in One True God | trinity
Gott der Vater wohn uns bei | God the Father, Be Our Stay | trinity
Ein feste Burg ist unser Gott | A Mighty Fortress Is Our God | reformation
Erhalt uns, Herr, bei deinem Wort | Lord, Keep Us Steadfast in Thy Word | reformation
Es ist das Heil uns kommen her | Salvation unto Us Has Come | reformation
Nun freut euch, lieben Christen | Dear Christians, One and All, Rejoice | reformation
Vater unser im Himmelreich | Our Father, Thou in Heaven Above | prayer
Dies sind die heilgen zehn Gebot | These Are the Holy Ten Commands | reformation
Ach Gott, vom Himmel sieh darein | O Lord, Look Down from Heaven | reformation
Wo Gott der Herr nicht bei uns hält | If God Had Not Been on Our Side | reformation
Verleih uns Frieden gnädiglich | Grant Peace, We Pray, in Mercy, Lord | reformation
Mit Fried und Freud ich fahr dahin | In Peace and Joy I Now Depart | funeral
Nun danket alle Gott | Now Thank We All Our God | thanksgiving praise
Lobe den Herren, den mächtigen König der Ehren | Praise to the Lord, the Almighty | praise thanksgiving
Nun lob, mein Seel, den Herren | My Soul, Now Praise Your Maker | praise
Herr Gott, dich loben alle wir | Old Hundredth | praise thanksgiving
Lobet den Herren, denn er ist sehr freundlich | Praise the Lord, for He Is Kind | praise thanksgiving
Nun lasst uns Gott dem Herren | Now Let Us Come before Him | thanksgiving
Singen wir aus Herzensgrund | Let Us Sing with All Our Heart | thanksgiving
Danket dem Herren, denn er ist sehr freundlich | Give Thanks unto the Lord | thanksgiving
Sollt ich meinem Gott nicht singen | I Will Sing My Maker's Praises | praise
Dir, dir, Jehova, will ich singen | To Thee, Jehovah, Will I Sing | praise
Was Gott tut, das ist wohlgetan | What God Ordains Is Always Good | trust
Wer nur den lieben Gott lässt walten | If Thou But Trust in God to Guide Thee | trust
Jesu, meine Freude | Jesus, Priceless Treasure | trust
Werde munter, mein Gemüte | Jesu, Joy of Man's Desiring (Werde munter) | praise
Liebster Jesu, wir sind hier | Blessed Jesus, at Thy Word | opening
Schmücke dich, o liebe Seele | Soul, Adorn Thyself with Gladness | communion
Meinen Jesum lass ich nicht | Jesus I Will Never Leave | trust
Was mein Gott will, das g'scheh allzeit | The Will of God Is Always Best | trust
Christus, der ist mein Leben | Abide, O Dearest Jesus | trust
Valet will ich dir geben | All Glory, Laud and Honor | palm-sunday
O Ewigkeit, du Donnerwort | O Eternity, Thou Thunderous Word | end-times
Es ist genug | It Is Enough | funeral
Es ist gewisslich an der Zeit | The Day Is Surely Drawing Near | end-times
Herr Jesu Christ, dich zu uns wend | Lord Jesus Christ, Be Present Now | opening
Herr Jesu Christ, du höchstes Gut | Lord Jesus Christ, Thou Highest Good | confession
O Gott, du frommer Gott | O God, Thou Faithful God | trust
Wenn wir in höchsten Nöten sein | When in the Hour of Deepest Need | trust
Auf meinen lieben Gott | In God, My Faithful God | trust
Ach wie flüchtig, ach wie nichtig | O How Cheating, O How Fleeting | funeral
Ach bleib bei uns, Herr Jesu Christ | Lord Jesus Christ, with Us Abide | evening
Christ, der du bist der helle Tag | O Christ, Who Art the Light and Day | evening
Warum sollt ich mich denn grämen | Why Should Cross and Trial Grieve Me | trust
Jesu, der du meine Seele | Jesus, Who My Soul Hast Rescued | redeemer
Ich ruf zu dir, Herr Jesu Christ | I Call to Thee, Lord Jesus Christ | prayer
In dich hab ich gehoffet, Herr | In Thee, Lord, Have I Put My Trust | trust
Aus meines Herzens Grunde | My Inmost Heart Now Raises | morning
Ich dank dir, lieber Herre | I Thank Thee, Dear Lord | morning
Gott des Himmels und der Erden | God of Heaven and of Earth | morning
Machs mit mir, Gott, nach deiner Güt | Come, Follow Me, the Savior Spake | trust
Seelenbräutigam | Jesus, Lead Thou On | trust
Eins ist not | One Thing's Needful | trust
Alle Menschen müssen sterben | All Men Living Are but Mortal | funeral
Helft mir Gotts Güte preisen | Help Me to Praise God's Goodness | newyear
Jesu, meiner Seelen Wonne | Jesus, My Soul's Delight | trust
"""


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.replace("ß", "ss")).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^a-z0-9 ]", "", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def build_tune(path: Path):
    title, composer, parts, names = read_musicxml_parts(path)
    want = ["soprano", "alto", "tenor", "bass"]
    by = {}
    for t, n in zip(parts, names):
        key = n.strip().lower()
        if key in want and key not in by:
            by[key] = t
    if len(by) < 4:
        if len(parts) >= 4:
            by = dict(zip(want, parts[:4]))
        else:
            return None, "not four parts"
    S = by["soprano"]
    n = len(S.bars)
    for k in want[1:]:
        if len(by[k].bars) != n or any(a.length != b.length for a, b in zip(by[k].bars, S.bars)):
            return None, f"{k} does not line up"
    tune = Tune(title=title, key=S.key, meter=S.meter)
    for i in range(n):
        sb = S.bars[i]
        tb = TBar(length=sb.length, melody=sb.melody)
        tb.voices = {"A": by["alto"].bars[i].melody, "T": by["tenor"].bars[i].melody, "B": by["bass"].bars[i].melody}
        tb.pickup, tb.start_repeat, tb.end_repeat, tb.volta = sb.pickup, sb.start_repeat, sb.end_repeat, sb.volta
        tb.meter, tb.key = sb.meter, sb.key
        tune.bars.append(tb)
    return tune, ""


def main():
    import music21
    from music21.corpus import chorales
    root = Path(music21.__file__).resolve().parent / "corpus" / "bach"
    listing = chorales.ChoraleListRKBWV().byRiemenschneider
    rows = []
    for line in TABLE.strip().splitlines():
        de, en, tags = [x.strip() for x in line.split("|")]
        rows.append((norm(de), de, en, tags.split()))
    dst = Path(__file__).resolve().parent.parent / "library" / "bach-chorales"
    dst.mkdir(parents=True, exist_ok=True)
    count = {}
    done = 0
    skipped = []
    for num in sorted(listing):
        info = listing[num]
        nt = norm(info["title"])
        match = None
        for key, de, en, tags in rows:
            if nt.startswith(key) or key.startswith(nt):
                match = (key, de, en, tags)
                break
        if match is None:
            continue
        key, de, en, tags = match
        if count.get(key, 0) >= 2:
            continue
        path = root / f"bwv{info['bwv']}.mxl"
        if not path.exists():
            skipped.append((de, info["bwv"], "file missing"))
            continue
        try:
            tune, why = build_tune(path)
        except Exception as exc:
            tune, why = None, f"{type(exc).__name__}: {exc}"
        if tune is None:
            skipped.append((de, info["bwv"], why))
            continue
        infer_minor(tune)
        H.infer_chords(tune)
        irr = irregular_bars(tune.bars, tune.meter)
        tune.free_meter = bool(irr)
        probs = validate(tune)
        if probs:
            skipped.append((de, info["bwv"], "; ".join(probs[:2])))
            continue
        k = count.get(key, 0)
        count[key] = k + 1
        tune.title = (en or de) + ("" if k == 0 else " (II)")
        tune.subtitle = f"{de} · BWV {info['bwv']}"
        tune.tune_name = de
        tune.composer = "Harmonized by Johann Sebastian Bach"
        tune.category = "hymn"
        tune.tags = ["bach"] + tags
        tune.style = "chorale"
        tune.source = "music21 corpus"
        tune.credit = f"Chorale harmonization by J. S. Bach (BWV {info['bwv']}), public domain; score from the music21 corpus."
        tune.tempo = 0
        tune.slug = slugify(f"bach-{en or de}" + ("" if k == 0 else "-2"))
        text = write_abc(tune)
        back = tune_from_abc(parse_abc(text)[0])
        same = len(back.bars) == len(tune.bars) and all(
            a.melody == b.melody and a.voices == b.voices for a, b in zip(tune.bars, back.bars))
        if not same:
            skipped.append((de, info["bwv"], "round-trip mismatch"))
            count[key] = k
            continue
        (dst / f"{tune.slug}.abc").write_text(text, encoding="utf-8")
        done += 1
    print(f"imported {done}")
    missing = [de for key, de, en, tags in rows if key not in count]
    print("not found:", "; ".join(missing))
    for s in skipped:
        print("  skipped:", s)


if __name__ == "__main__":
    main()
