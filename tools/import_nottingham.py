#!/usr/bin/env python3
"""Import a hand-picked set of traditional tunes (melody + chords) from the
Nottingham Music Database into ``library/folk`` and ``library/carols``.

    python tools/import_nottingham.py /path/to/nottingham-dataset/ABC_cleaned

Source: https://github.com/jukedeck/nottingham-dataset (cleaned copy of Eric
Foxley's Nottingham Music Database).  Only tunes that are traditional or were
published before 1931 are taken.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from duets.abc import apply_play_order, parse_abc           # noqa: E402
from duets.abcwrite import write_abc                        # noqa: E402
from duets.library import slugify, tune_from_abc, validate  # noqa: E402
from duets.model import merge_ties                          # noqa: E402

# file, source title, new title ('' = keep), composer/origin, tags, style
T = "Traditional"
SEL = [
    # ---- carols -----------------------------------------------------------
    ("xmas", "The Boar's Head", "The Boar's Head Carol", "English traditional carol", "christmas", "march"),
    ("xmas", "Ding Dong", "Ding Dong! Merrily on High", "French dance tune (Arbeau, 1589)", "christmas", "march"),
    ("xmas", "GKW", "Good King Wenceslas", "Tempus adest floridum (Piae Cantiones, 1582)", "christmas", "march"),
    ("xmas", "God rest you, merry gentlemen", "God Rest You Merry, Gentlemen", "English traditional carol", "christmas", "march"),
    ("xmas", "Good Christian Men Rejoice", "Good Christian Friends, Rejoice", "In dulci jubilo (14th-century German carol)", "christmas", "jig"),
    ("xmas", "The Holly and the Ivy", "", "English traditional carol", "christmas", "waltz"),
    ("xmas", "Nos Galan", "Deck the Halls", "Nos Galan (Welsh traditional)", "christmas", "march"),
    ("xmas", "On Christmas Night", "On Christmas Night (Sussex Carol)", "English traditional carol", "christmas", "jig"),
    ("xmas", "Wassail 1", "Here We Come A-Wassailing", "English traditional carol", "christmas", "jig"),
    ("xmas", "Wassail 2", "Gloucestershire Wassail", "English traditional carol", "christmas", "waltz"),
    ("xmas", "W3KOOA", "We Three Kings of Orient Are", "John Henry Hopkins Jr., 1857", "christmas epiphany", "waltz"),
    ("jigs", "Christmas Day in da Morning", "Christmas Day in the Morning", "Shetland traditional", "christmas", "jig"),
    # ---- hornpipes and polkas ---------------------------------------------
    ("hpps", "The Blackbird", "", "Irish traditional hornpipe", "irish", "march"),
    ("hpps", "Fisher's Hornpipe", "", "English traditional (18th century)", "english", "march"),
    ("hpps", "Harvest Home", "", "Irish traditional hornpipe", "irish thanksgiving", "march"),
    ("hpps", "John Peel", "D'ye Ken John Peel", "English traditional (Cumberland)", "english", "march"),
    ("hpps", "Keel Row", "The Keel Row", "Northumbrian traditional", "english", "march"),
    ("hpps", "King of the Fairies", "", "Irish traditional set dance", "irish", "march"),
    ("hpps", "Liverpool Hornpipe", "", "English traditional", "english", "march"),
    ("hpps", "Londonderry Hornpipe", "", "Irish traditional", "irish", "march"),
    ("hpps", "Rights of Man", "The Rights of Man", "Irish traditional hornpipe", "irish", "march"),
    ("hpps", "Trumpet", "The Trumpet Hornpipe", "English traditional", "english", "march"),
    ("hpps", "Castles in the Air", "", "Scottish traditional", "scottish", "march"),
    ("hpps", "Green Grow the Rushes", "Green Grow the Rushes, O", "Scottish traditional", "scottish", "march"),
    # ---- morris and Playford ------------------------------------------------
    ("morris", "Blue Bells of Scotland", "The Bluebells of Scotland", "Scottish traditional", "scottish", "march"),
    ("morris", "Constant Billy", "", "English morris dance", "english", "jig"),
    ("morris", "Jockey to the Fair", "", "English morris dance", "english", "jig"),
    ("morris", "Sweet Jenny Jones", "", "Welsh traditional (Cader Idris)", "welsh", "waltz"),
    ("morris", "Bonny Green Garters", "", "English morris dance", "english", "jig"),
    ("morris", "Highland Mary", "", "English morris dance", "english", "march"),
    ("morris", "Abbotts Bromley Horn Dance", "Abbots Bromley Horn Dance", "English traditional", "english", "jig"),
    ("playford", "Hole in the Wall", "", "Henry Purcell, 1695 (Playford's Dancing Master)", "english baroque", "waltz"),
    ("playford", "The Indian Queen", "", "Playford's Dancing Master, 1701", "english baroque", "march"),
    ("playford", "Mr Beveridge's Maggot", "", "Playford's Dancing Master, 1695", "english baroque", "waltz"),
    ("playford", "Nonesuch", "", "Playford's Dancing Master, 1651", "english baroque", "march"),
    ("playford", "Rufty Tufty", "", "Playford's Dancing Master, 1651", "english baroque", "march"),
    ("playford", "Staines Morris", "", "Playford's Dancing Master, 1651", "english baroque", "march"),
    ("playford", "Dick's Maggot", "", "Playford's Dancing Master, 1703", "english baroque", "waltz"),
    # ---- slip jigs -------------------------------------------------------------
    ("slip", "Drops of Brandy", "", "Irish/Scottish traditional slip jig", "irish", "jig"),
    ("slip", "The Rocky Road To Dublin", "The Rocky Road to Dublin", "Irish traditional slip jig", "irish", "jig"),
    ("slip", "Sir Roger de Coverley", "", "English traditional (17th century)", "english", "jig"),
    ("slip", "Kid on the Mountain", "The Kid on the Mountain", "Irish traditional slip jig", "irish", "jig"),
    # ---- waltzes and airs ------------------------------------------------------
    ("waltzes", "Ye Banks and Braes", "Ye Banks and Braes o' Bonnie Doon", "Scottish traditional air", "scottish", "waltz"),
    ("waltzes", "Blow the Wind Southerly", "", "Northumbrian traditional", "english", "waltz"),
    ("waltzes", "Bonnie Dundee", "", "Scottish traditional", "scottish", "jig"),
    ("waltzes", "Daisy Daisy", "Daisy Bell (A Bicycle Built for Two)", "Harry Dacre, 1892", "oldies", "waltz"),
    ("waltzes", "All Those Endearing Young Charms", "Believe Me, If All Those Endearing Young Charms", "Irish traditional air", "irish", "waltz"),
    ("waltzes", "I Belong to Glasgow", "", "Will Fyffe, 1920", "scottish oldies", "waltz"),
    ("waltzes", "Great is Thy Faithfulness", "Great Is Thy Faithfulness", "William M. Runyan, 1923", "hymn praise", "waltz"),
    ("waltzes", "Kelvingrove", "", "Scottish traditional air", "scottish hymn", "waltz"),
    ("waltzes", "Scots Wha Hae", "", "Scottish traditional (Hey Tuttie Tatie)", "scottish", "march"),
    ("waltzes", "Planxty Irwin", "", "Turlough O'Carolan (1670-1738)", "irish", "waltz"),
    ("waltzes", "Shebag Shebong", "Sheebeg and Sheemore", "Turlough O'Carolan (1670-1738)", "irish", "waltz"),
    ("waltzes", "Waters of Tyne", "The Waters of Tyne", "Northumbrian traditional", "english", "waltz"),
    ("waltzes", "Road to Dundee", "The Road to Dundee", "Scottish traditional", "scottish", "waltz"),
    ("waltzes", "Lord of all Hopefulness", "Slane (Be Thou My Vision)", "Irish traditional melody", "irish hymn", "waltz"),
    ("waltzes", "Hector the Hero", "", "James Scott Skinner, 1903", "scottish", "waltz"),
    ("waltzes", "Merch Megan", "Megan's Daughter (Merch Megan)", "Welsh traditional", "welsh", "waltz"),
    # ---- jigs ------------------------------------------------------------------
    ("jigs", "Atholl Highlanders", "The Atholl Highlanders", "Scottish traditional pipe march", "scottish", "jig"),
    ("jigs", "Blackthorne Stick", "The Blackthorn Stick", "Irish traditional jig", "irish", "jig"),
    ("jigs", "Blarney Pilgrim", "The Blarney Pilgrim", "Irish traditional jig", "irish", "jig"),
    ("jigs", "Blaydon Races", "The Blaydon Races", "Tyneside song (George Ridley, 1862)", "english", "jig"),
    ("jigs", "Cock of the North", "", "Scottish traditional", "scottish", "jig"),
    ("jigs", "The Connaught Man's Rambles", "The Connaughtman's Rambles", "Irish traditional jig", "irish", "jig"),
    ("jigs", "Garry Owen", "Garryowen", "Irish traditional quickstep", "irish", "jig"),
    ("jigs", "Haste To The Wedding", "Haste to the Wedding", "English/Irish traditional jig", "irish", "jig"),
    ("jigs", "The Hundred Pipers", "The Hundred Pipers", "Scottish traditional", "scottish", "jig"),
    ("jigs", "Irish Washerwoman", "The Irish Washerwoman", "Irish traditional jig", "irish", "jig"),
    ("jigs", "John Brown's Body", "John Brown's Body (in Jig Time)", "William Steffe, c. 1856", "american patriotic", "jig"),
    ("jigs", "Rakes of Kildare", "The Rakes of Kildare", "Irish traditional jig", "irish", "jig"),
    ("jigs", "Lannigan's Ball", "Lanigan's Ball", "Irish traditional jig", "irish", "jig"),
    ("jigs", "The Lark In The Morning", "The Lark in the Morning", "Irish traditional jig", "irish", "jig"),
    ("jigs", "Larry O'Gaff", "", "Irish traditional jig", "irish", "jig"),
    ("jigs", "Road To Lisdoonvarna", "The Road to Lisdoonvarna", "Irish traditional", "irish", "jig"),
    ("jigs", "Nancy Dawson", "Nancy Dawson (Here We Go Round the Mulberry Bush)", "English traditional", "english children", "jig"),
    ("jigs", "Off She Goes", "", "English traditional jig", "english", "jig"),
    ("jigs", "Oh Dear, What Can The Matter Be", "Oh Dear! What Can the Matter Be?", "English traditional", "english children", "jig"),
    ("jigs", "Paddy Whack", "", "Irish traditional jig", "irish", "jig"),
    ("jigs", "Pop Goes the Wheezle", "Pop! Goes the Weasel", "English traditional", "english children", "jig"),
    ("jigs", "Rory O'More", "", "Samuel Lover, 1826", "irish", "jig"),
    ("jigs", "Rosin The Beau", "Rosin the Bow", "Irish/American traditional", "irish american", "jig"),
    ("jigs", "Saddle The Pony", "Saddle the Pony", "Irish traditional jig", "irish", "jig"),
    ("jigs", "Smash the Windows", "", "Irish traditional jig", "irish", "jig"),
    ("jigs", "Swallowtail", "The Swallowtail Jig", "Irish traditional jig", "irish", "jig"),
    ("jigs", "Tenpenny Bit", "The Tenpenny Bit", "Irish traditional jig", "irish", "jig"),
    ("jigs", "Tobin's Favourite", "", "Irish traditional jig", "irish", "jig"),
    ("jigs", "Tripping Upstairs", "Tripping Up the Stairs", "Irish traditional jig", "irish", "jig"),
    ("jigs", "Jig from the Water Music", "Jig from the Water Music", "George Frideric Handel, 1717", "classical baroque", "jig"),
    ("jigs", "I Do Like To Be Beside The Seaside", "I Do Like to Be Beside the Seaside", "John A. Glover-Kind, 1907", "oldies english", "jig"),
    ("jigs", "My Darling Asleep", "", "Irish traditional jig", "irish", "jig"),
    ("jigs", "The Monaghan Jig", "", "Irish traditional jig", "irish", "jig"),
    ("jigs", "Cherish The Ladies", "Cherish the Ladies", "Irish traditional jig", "irish", "jig"),
    ("jigs", "Liberty Bell", "The Liberty Bell", "John Philip Sousa, 1893", "march american", "jig"),
    ("jigs", "Sweets of May", "The Sweets of May", "Irish traditional", "irish", "jig"),
    ("jigs", "Oyster Girl", "The Oyster Girl", "English traditional jig", "english", "jig"),
    ("jigs", "Cumberland Reel", "", "English traditional", "english", "jig"),
    ("jigs", "Hunt The Squirrel", "Hunt the Squirrel", "English traditional (Playford, 1709)", "english", "jig"),
    ("jigs", "Dingle Regatta", "", "Irish traditional", "irish", "jig"),
    ("jigs", "On the Trail of the Lonesome Pine", "The Trail of the Lonesome Pine", "Harry Carroll, 1913", "oldies american", "jig"),
    ("jigs", "Humours of Donnybrook", "The Humours of Donnybrook", "Irish traditional jig", "irish", "jig"),
    # ---- reels, marches, songs ------------------------------------------------
    ("reelsa-c", "Barren Rocks of Aden", "The Barren Rocks of Aden", "Scottish pipe march", "scottish", "march"),
    ("reelsa-c", "Aiken Drum", "", "Scottish traditional", "scottish children", "march"),
    ("reelsa-c", "Alabama Jubilee", "", "George L. Cobb, 1915", "oldies american rag", "march"),
    ("reelsa-c", "Angeline The Baker", "Angeline the Baker", "Stephen Foster, 1850", "american", "march"),
    ("reelsa-c", "Arkensas Traveller", "Arkansas Traveler", "American traditional fiddle tune", "american", "march"),
    ("reelsa-c", "La Bastringue", "", "French-Canadian traditional", "canadian", "march"),
    ("reelsa-c", "Billy In The Lowground", "Billy in the Lowground", "American traditional fiddle tune", "american", "march"),
    ("reelsa-c", "Boil 'Em Cabbage Down", "Bile 'Em Cabbage Down", "American traditional", "american", "march"),
    ("reelsa-c", "Brighton Camp", "The Girl I Left Behind Me", "English/Irish traditional (Brighton Camp)", "english", "march"),
    ("reelsa-c", "Buffalo Gals", "", "American traditional (1844)", "american", "march"),
    ("reelsa-c", "California Here I Come", "California, Here I Come", "Joseph Meyer, 1924", "oldies american", "march"),
    ("reelsa-c", "She'll be Coming Round the Mountain", "She'll Be Coming 'Round the Mountain", "American traditional", "american children", "march"),
    ("reelsa-c", "O'Carolan's Concerto", "Carolan's Concerto", "Turlough O'Carolan (1670-1738)", "irish baroque", "march"),
    ("reelsa-c", "Corn Rigs", "Corn Rigs", "Scottish traditional", "scottish", "march"),
    ("reelsa-c", "Cripple Creek", "", "American traditional fiddle tune", "american", "march"),
    ("reelsd-g", "Dashing White Sergeant", "The Dashing White Sergeant", "Henry Bishop, 1826", "scottish", "march"),
    ("reelsd-g", "Devil Among the Tailors", "The Devil Among the Tailors", "Scottish/English traditional reel", "scottish", "march"),
    ("reelsd-g", "Dill Pickle Rag", "Dill Pickles Rag", "Charles L. Johnson, 1906", "rag american", "stride"),
    ("reelsd-g", "Drowsy Maggie", "", "Irish traditional reel", "irish", "march"),
    ("reelsd-g", "Drunken Sailor", "The Drunken Sailor Hornpipe", "English/Irish traditional hornpipe", "sea irish", "march"),
    ("reelsd-g", "Fairy Dance", "The Fairy Dance", "Nathaniel Gow, 1809", "scottish", "march"),
    ("reelsd-g", "Flop-eared Mule", "Flop-Eared Mule", "American traditional fiddle tune", "american", "march"),
    ("reelsd-g", "Flowers of Edinburgh", "The Flowers of Edinburgh", "Scottish traditional reel", "scottish", "march"),
    ("reelsd-g", "Grand Old Duke of York", "The Grand Old Duke of York", "English traditional", "english children", "march"),
    ("reelsd-g", "Galopede", "", "English traditional country dance", "english", "march"),
    ("reelsd-g", "Sweet Georgia Brown", "", "Ben Bernie & Maceo Pinkard, 1925", "oldies standard", "walking"),
    ("reelsd-g", "Marching Through Georgia", "", "Henry Clay Work, 1865", "american patriotic", "march"),
    ("reelsd-g", "Golden Slippers", "Oh, Dem Golden Slippers", "James A. Bland, 1879", "american", "march"),
    ("reelsd-g", "Farewell to Whisky", "Farewell to Whisky", "Niel Gow, 1799", "scottish", "march"),
    ("reelsd-g", "Liza Jane", "", "American traditional", "american", "march"),
    ("reelsh-l", "Huntsman's Chorus", "Huntsmen's Chorus", "Carl Maria von Weber (Der Freischütz, 1821)", "classical opera", "march"),
    ("reelsh-l", "It's a Long Way to Tipperary", "", "Jack Judge, 1912", "oldies english", "march"),
    ("reelsh-l", "Jenny Lind", "Jenny Lind Polka", "Anton Wallerstein, 1846", "polka", "march"),
    ("reelsh-l", "Korybushka", "Korobushka", "Russian traditional", "russian", "march"),
    ("reelsh-l", "La Russe", "", "English traditional quadrille", "english", "march"),
    ("reelsh-l", "Liberty", "", "American traditional fiddle tune", "american", "march"),
    ("reelsh-l", "Little Brown Jug", "", "Joseph Winner, 1869", "american oldies", "march"),
    ("reelsh-l", "The Leaving of Liverpool", "", "Sea song (traditional)", "sea english", "march"),
    ("reelsh-l", "Little Liza Jane", "", "American traditional", "american", "march"),
    ("reelsh-l", "Long Long Trail", "There's a Long, Long Trail", "Zo Elliott, 1914", "oldies", "ballad"),
    ("reelsh-l", "Hot Time", "A Hot Time in the Old Town", "Theodore Metz, 1896", "oldies american", "march"),
    ("reelsh-l", "High Caul Cap", "The High Caul Cap", "Irish traditional", "irish", "march"),
    ("reelsh-l", "Ho Ro My Nut Brown Maiden", "Ho Ro, My Nut-Brown Maiden", "Scottish Gaelic traditional", "scottish", "march"),
    ("reelsh-l", "Kitchen Girl", "", "American traditional fiddle tune", "american", "march"),
    ("reelsm-q", "When You And I Were Young Maggie", "When You and I Were Young, Maggie", "James A. Butterfield, 1866", "oldies american", "ballad"),
    ("reelsm-q", "The Maid Behind The Bar", "The Maid Behind the Bar", "Irish traditional reel", "irish", "march"),
    ("reelsm-q", "Marching Through Georgia", "", "", "", ""),
    ("reelsm-q", "Mason's Apron", "The Mason's Apron", "Irish/Scottish traditional reel", "irish", "march"),
    ("reelsm-q", "Merry Blacksmith", "The Merry Blacksmith", "Irish traditional reel", "irish", "march"),
    ("reelsm-q", "The Minstrel Boy", "", "Irish traditional air (The Moreen)", "irish", "march"),
    ("reelsm-q", "May Day (Miss McLeod's Reel)", "Miss McLeod's Reel", "Scottish/Irish traditional reel", "irish scottish", "march"),
    ("reelsm-q", "Mississipi Sawyer", "Mississippi Sawyer", "American traditional fiddle tune", "american", "march"),
    ("reelsm-q", "Morpeth Rant", "", "Northumbrian traditional", "english", "march"),
    ("reelsm-q", "My Love is but a Lassie Yet", "My Love She's But a Lassie Yet", "Scottish traditional", "scottish", "march"),
    ("reelsm-q", "My Old Man", "My Old Man (Said Follow the Van)", "Charles Collins, 1919", "oldies english", "march"),
    ("reelsm-q", "Nick Nack Paddy Whack", "This Old Man", "English traditional children's song", "children", "march"),
    ("reelsm-q", "Old Joe Clark 1", "Old Joe Clark", "American traditional", "american", "march"),
    ("reelsm-q", "Pack Up Your Troubles", "Pack Up Your Troubles in Your Old Kit-Bag", "Felix Powell, 1915", "oldies english", "march"),
    ("reelsm-q", "Petronella", "", "Scottish traditional country dance", "scottish", "march"),
    ("reelsm-q", "Polly Put the Kettle on", "Polly Put the Kettle On", "English traditional", "english children", "march"),
    ("reelsr-t", "Ragtime Annie", "", "American traditional fiddle tune", "american rag", "march"),
    ("reelsr-t", "Rattling Bog", "The Rattlin' Bog", "Irish traditional", "irish", "march"),
    ("reelsr-t", "Red Haired Boy", "The Red-Haired Boy", "Irish traditional", "irish", "march"),
    ("reelsr-t", "Redwing", "Red Wing", "Kerry Mills, 1907", "oldies american", "march"),
    ("reelsr-t", "Rose Tree", "The Rose Tree", "English/Irish traditional", "english", "march"),
    ("reelsr-t", "Sailor's Hornpipe", "The Sailor's Hornpipe", "English traditional (College Hornpipe)", "sea english", "march"),
    ("reelsr-t", "Saints", "When the Saints Go Marching In", "American traditional spiritual", "american spiritual", "march"),
    ("reelsr-t", "Sally Gardens", "The Sally Gardens (reel)", "Irish traditional reel", "irish", "march"),
    ("reelsr-t", "Salmon Tails", "Salmon Tails Up the Water", "Northumbrian traditional", "english", "march"),
    ("reelsr-t", "Scotland the Brave", "", "Scottish traditional", "scottish", "march"),
    ("reelsr-t", "Soldiers' Joy", "Soldier's Joy", "Scottish/American traditional reel", "scottish american", "march"),
    ("reelsr-t", "Speed The Plough", "Speed the Plough", "English traditional (1799)", "english", "march"),
    ("reelsr-t", "St Anne's (V)", "St. Anne's Reel", "French-Canadian traditional reel", "canadian", "march"),
    ("reelsr-t", "Staten Island", "Staten Island Hornpipe", "Scottish/American traditional", "scottish american", "march"),
    ("reelsr-t", "Good Old Summertime", "In the Good Old Summertime", "George Evans, 1902", "oldies american", "waltz"),
    ("reelsr-t", "Oh Susanna", "Oh! Susanna", "Stephen Foster, 1848", "american", "march"),
    ("reelsr-t", "The Swallow's Tail", "The Swallow's Tail Reel", "Irish traditional reel", "irish", "march"),
    ("reelsr-t", "Turkey in the Straw", "", "American traditional", "american", "march"),
    ("reelsr-t", "The Swiss Boy", "", "Swiss/Tyrolean traditional", "european", "march"),
    ("reelsr-t", "Roddy McCawley", "Roddy McCorley", "Irish traditional", "irish", "march"),
    ("reelsu-z", "The White Cockade", "", "Scottish traditional", "scottish", "march"),
    ("reelsu-z", "William Tell Overture", "William Tell Overture (Finale)", "Gioachino Rossini, 1829", "classical opera", "march"),
    ("reelsu-z", "Winster Galop", "The Winster Gallop", "English traditional (Derbyshire)", "english", "march"),
    ("reelsu-z", "Lord Wellington", "", "English/Irish traditional", "english", "march"),
]


# tunes that are songs rather than dance tunes (they go in the song books)
SONGS = set('''Ye Banks and Braes o' Bonnie Doon|Blow the Wind Southerly|Bonnie Dundee|Daisy Bell (A Bicycle Built for Two)
Believe Me, If All Those Endearing Young Charms|I Belong to Glasgow|Great Is Thy Faithfulness|Kelvingrove|Scots Wha Hae
The Waters of Tyne|The Road to Dundee|Slane (Be Thou My Vision)|The Minstrel Boy|The Girl I Left Behind Me|Buffalo Gals
She'll Be Coming 'Round the Mountain|Oh! Susanna|Turkey in the Straw|Oh, Dem Golden Slippers|Little Brown Jug
The Leaving of Liverpool|When the Saints Go Marching In|This Old Man|Polly Put the Kettle On|The Grand Old Duke of York
Aiken Drum|Pop! Goes the Weasel|Oh Dear! What Can the Matter Be?|Nancy Dawson (Here We Go Round the Mulberry Bush)
The Blaydon Races|D'ye Ken John Peel|The Keel Row|The Bluebells of Scotland|Rosin the Bow|Marching Through Georgia
John Brown's Body (in Jig Time)|Old Joe Clark|Liza Jane|Little Liza Jane|Angeline the Baker|Bile 'Em Cabbage Down
The Rattlin' Bog|Roddy McCorley|Scotland the Brave|The Hundred Pipers|My Love She's But a Lassie Yet
Ho Ro, My Nut-Brown Maiden|Green Grow the Rushes, O|Castles in the Air|Korobushka|The Swiss Boy|Megan's Daughter (Merch Megan)
It's a Long Way to Tipperary|My Old Man (Said Follow the Van)|Pack Up Your Troubles in Your Old Kit-Bag
There's a Long, Long Trail|A Hot Time in the Old Town|When You and I Were Young, Maggie|In the Good Old Summertime
Red Wing|I Do Like to Be Beside the Seaside|The Trail of the Lonesome Pine|Alabama Jubilee|Hector the Hero
Sheebeg and Sheemore|Planxty Irwin'''.replace("\n", "|").split("|"))


def main():
    src = Path(sys.argv[1])
    root = Path(__file__).resolve().parent.parent / "library"
    cache = {}
    done = 0
    missing = []
    seen = set()
    for fname, title, new_title, origin, tags, style in SEL:
        if not origin:
            continue
        if fname not in cache:
            cache[fname] = parse_abc((src / f"{fname}.abc").read_text(encoding="latin-1"))
        match = [a for a in cache[fname] if a.title.strip().lower() == title.lower()]
        if not match:
            match = [a for a in cache[fname] if a.title.strip().lower().startswith(title.lower())]
        if not match:
            missing.append((fname, title, "not found"))
            continue
        tune = None
        why = ""
        for abc in match:
            try:
                t = abc.to_tune()
                apply_play_order(t, abc.header("Y"))
            except Exception as exc:
                why = str(exc)
                continue
            for b in t.bars:
                b.melody = merge_ties(b.melody)
            probs = validate(t)
            if any(b.meter is not None for b in t.bars):
                probs.append("meter change")
            if not t.has_chords:
                probs.append("no chords")
            if probs:
                why = "; ".join(probs[:2])
                continue
            tune = t
            break
        if tune is None:
            missing.append((fname, title, why))
            continue
        tune.title = new_title or tune.title
        tune.composer = origin
        tl = tags.split()
        is_carol = "christmas" in tl
        tune.category = "carol" if is_carol else ("classical" if "classical" in tl else
                                                  "oldies" if "oldies" in tl else
                                                  "rag" if "rag" in tl and "oldies" not in tl else "folk")
        if tune.title in SONGS or title in SONGS:
            tl.append("song")
        tune.tags = tl
        tune.style = style
        tune.source = "Nottingham Music Database"
        tune.credit = "Melody and chords: traditional / public domain, from the Nottingham Music Database."
        tune.tempo = 0
        slug = slugify(tune.title)
        if slug in seen:
            continue
        seen.add(slug)
        tune.slug = slug
        text = write_abc(tune)
        back = tune_from_abc(parse_abc(text)[0])
        if len(back.bars) != len(tune.bars) or any(a.melody != b.melody or a.chords != b.chords
                                                   for a, b in zip(tune.bars, back.bars)):
            missing.append((fname, title, "round-trip mismatch"))
            continue
        sub = "carols" if is_carol else "folk"
        (root / sub).mkdir(parents=True, exist_ok=True)
        (root / sub / f"{slug}.abc").write_text(text, encoding="utf-8")
        done += 1
    print(f"imported {done}")
    for m in missing:
        print("  missing:", m)


if __name__ == "__main__":
    main()
