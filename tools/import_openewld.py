#!/usr/bin/env python3
"""Import public-domain lead sheets (melody + chords) from OpenEWLD into the
library.

    python tools/import_openewld.py /path/to/OpenEWLD

Source: https://github.com/00sapo/OpenEWLD (the public-domain subset of the
Enhanced Wikifonia Leadsheet Dataset).  OpenEWLD's own filter follows European
rules, so every title below was checked by hand against United States law:
only works first published in 1930 or earlier (public domain in the US since
1 January 2026 at the latest) or traditional material are taken.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from duets.abc import parse_abc                               # noqa: E402
from duets.abcwrite import write_abc                          # noqa: E402
from duets.library import slugify, tune_from_abc, validate    # noqa: E402
from duets.mxl import infer_minor, read_musicxml              # noqa: E402

# dataset title | year | credit | category | style | tags | new title (optional)
TABLE = """
'S Wonderful | 1927 | George Gershwin | standard | swing | gershwin ella sinatra
(I've Got a) Crush on You | 1928 | George Gershwin | standard | ballad | gershwin sinatra ella | I've Got a Crush on You
(What Did I Do to Be So) Black and Blue? | 1929 | Fats Waller & Harry Brooks | standard | ballad | waller | Black and Blue
After You've Gone | 1918 | Turner Layton | standard | swing | ella sinatra
Ain't Misbehavin' | 1929 | Fats Waller & Harry Brooks | standard | swing | waller ella
Ain't We Got Fun | 1921 | Richard A. Whiting | standard | swing |
Am I Blue? | 1929 | Harry Akst | standard | ballad |
Are You Lonesome Tonight? | 1927 | Lou Handman | standard | waltz |
At Sundown | 1927 | Walter Donaldson | standard | swing | sinatra
Avalon | 1920 | Vincent Rose & Al Jolson | standard | swing | natkingcole
Beyond the Blue Horizon | 1930 | Richard A. Whiting & W. Franke Harling | standard | swing |
Bidin' My Time | 1930 | George Gershwin | standard | swing | gershwin ella
Bill | 1927 | Jerome Kern | standard | ballad | kern ella
Blue Room | 1926 | Richard Rodgers | standard | swing | rodgers ella | The Blue Room
Breezin' Along with the Breeze | 1926 | Haven Gillespie, Seymour Simons & Richard A. Whiting | standard | swing |
But Not for Me | 1930 | George Gershwin | standard | ballad | gershwin ella sinatra
Can't Help Lovin' Dat Man | 1927 | Jerome Kern | standard | ballad | kern ella
Carolina in the Morning | 1922 | Walter Donaldson | standard | swing |
Charmaine | 1926 | Ernö Rapée & Lew Pollack | standard | waltz |
Chicago (That Toddling Town) | 1922 | Fred Fisher | standard | swing | sinatra | Chicago (That Toddlin' Town)
Coquette | 1928 | Johnny Green & Carmen Lombardo | standard | ballad |
Dancing on the Ceiling | 1930 | Richard Rodgers | standard | ballad | rodgers ella sinatra
Dancing with Tears in My Eyes | 1930 | Joe Burke | standard | waltz |
Deep in My Heart, Dear | 1924 | Sigmund Romberg | standard | waltz |
Dinah | 1925 | Harry Akst | standard | swing |
Do It Again | 1922 | George Gershwin | standard | ballad | gershwin
Embraceable You | 1930 | George Gershwin | standard | ballad | gershwin ella sinatra natkingcole
Fascinating Rhythm | 1924 | George Gershwin | standard | swing | gershwin ella
Five Foot Two, Eyes of Blue (Has Anybody Seen My Girl) | 1925 | Ray Henderson | standard | swing | | Five Foot Two, Eyes of Blue
Great Day | 1929 | Vincent Youmans | standard | swing |
Here in My Arms | 1925 | Richard Rodgers | standard | ballad | rodgers ella
Honey | 1928 | Seymour Simons, Haven Gillespie & Richard A. Whiting | standard | ballad |
Honeysuckle Rose | 1929 | Fats Waller | standard | swing | waller ella
How Am I to Know? | 1929 | Jack King | standard | ballad |
How Long Has This Been Going On? | 1927 | George Gershwin | standard | ballad | gershwin ella
I Can't Believe That You're in Love with Me | 1926 | Jimmy McHugh | standard | swing | sinatra
I Got Rhythm | 1930 | George Gershwin | standard | swing | gershwin ella
I Know That You Know | 1926 | Vincent Youmans | standard | swing | natkingcole
I Wanna Be Loved by You | 1928 | Herbert Stothart & Harry Ruby | standard | swing |
I Want to Be Happy | 1924 | Vincent Youmans | standard | swing | ella
I Wonder Where My Baby Is Tonight | 1925 | Walter Donaldson | standard | swing |
I'll Build a Stairway to Paradise | 1922 | George Gershwin | standard | swing | gershwin
I'll Get By (As Long as I Have You) | 1928 | Fred E. Ahlert | standard | ballad |
I'll See You in My Dreams | 1924 | Isham Jones | standard | ballad | ella
I'm Sitting on Top of the World | 1925 | Ray Henderson | standard | swing |
If I Could Be with You (One Hour Tonight) | 1926 | James P. Johnson | standard | ballad |
In a Little Spanish Town | 1926 | Mabel Wayne | standard | waltz |
It Had to Be You | 1924 | Isham Jones | standard | swing | sinatra
Japanese Sandman | 1920 | Richard A. Whiting | standard | swing | | The Japanese Sandman
Just You, Just Me | 1929 | Jesse Greer | standard | swing | natkingcole ella
Let a Smile Be Your Umbrella | 1927 | Sammy Fain | standard | swing |
Limehouse Blues | 1922 | Philip Braham | standard | swing |
Linger Awhile | 1923 | Vincent Rose | standard | swing |
Little White Lies | 1930 | Walter Donaldson | standard | swing | ella
Liza (All the Clouds'll Roll Away) | 1929 | George Gershwin | standard | swing | gershwin
Look for the Silver Lining | 1920 | Jerome Kern | standard | ballad | kern
Louise | 1929 | Richard A. Whiting | standard | swing |
Love Me or Leave Me | 1928 | Walter Donaldson | standard | swing | ella
Ma, He's Making Eyes at Me | 1921 | Con Conrad | standard | swing |
Make Believe | 1927 | Jerome Kern | standard | ballad | kern
Makin' Whoopee! | 1928 | Walter Donaldson | standard | swing | ella sinatra natkingcole
Manhattan | 1925 | Richard Rodgers | standard | swing | rodgers ella
Margie | 1920 | Con Conrad & J. Russel Robinson | standard | swing |
Mean to Me | 1929 | Fred E. Ahlert | standard | ballad | ella
More Than You Know | 1929 | Vincent Youmans | standard | ballad | ella sinatra
Mountain Greenery | 1926 | Richard Rodgers | standard | swing | rodgers ella
My Baby Just Cares for Me | 1930 | Walter Donaldson | standard | swing | natkingcole
My Blue Heaven | 1927 | Walter Donaldson | standard | swing | sinatra
My Buddy | 1922 | Walter Donaldson | standard | waltz | sinatra
My Heart Stood Still | 1927 | Richard Rodgers | standard | ballad | rodgers ella sinatra
My Ideal | 1930 | Richard A. Whiting & Newell Chase | standard | ballad | sinatra
My Melancholy Baby | 1912 | Ernie Burnett | standard | ballad | ella sinatra
Nobody Knows You When You're down and Out | 1923 | Jimmie Cox | standard | ballad | | Nobody Knows You When You're Down and Out
Nobody's Sweetheart | 1924 | Billy Meyers & Elmer Schoebel | standard | swing |
Oh, Lady Be Good! | 1924 | George Gershwin | standard | swing | gershwin ella
Ol' Man River | 1927 | Jerome Kern | standard | ballad | kern sinatra
On the Alamo | 1922 | Isham Jones | standard | ballad |
She's Funny That Way | 1928 | Neil Moret | standard | ballad | sinatra
Sleepy Time Gal | 1925 | Ange Lorenzo & Richard A. Whiting | standard | ballad |
Somebody Loves Me | 1924 | George Gershwin | standard | swing | gershwin ella
Sometimes I'm Happy (Sometimes I'm Blue) | 1927 | Vincent Youmans | standard | swing | natkingcole ella | Sometimes I'm Happy
Soon | 1930 | George Gershwin | standard | ballad | gershwin ella
Strike Up the Band | 1927 | George Gershwin | standard | march | gershwin
Swanee | 1919 | George Gershwin | standard | march | gershwin
Swingin' down the Lane | 1923 | Isham Jones | standard | swing | | Swingin' Down the Lane
Tea for Two | 1924 | Vincent Youmans | standard | swing | ella
Ten Cents a Dance | 1930 | Richard Rodgers | standard | ballad | rodgers ella
That Certain Feeling | 1925 | George Gershwin | standard | swing | gershwin ella
The One I Love Belongs to Somebody Else | 1924 | Isham Jones | standard | ballad | sinatra
The Sheik of Araby | 1921 | Ted Snyder | standard | swing |
They Didn't Believe Me | 1914 | Jerome Kern | standard | ballad | kern
This Funny World | 1926 | Richard Rodgers | standard | ballad | rodgers
Thou Swell | 1927 | Richard Rodgers | standard | swing | rodgers ella natkingcole
Three Little Words | 1930 | Harry Ruby | standard | swing | ella
Time on My Hands | 1930 | Vincent Youmans | standard | ballad |
Toot, Toot, Tootsie (Goo' Bye) | 1922 | Gus Kahn, Ernie Erdman & Dan Russo | standard | swing |
Walkin' My Baby Back Home | 1930 | Fred E. Ahlert | standard | swing | natkingcole
Way Down Yonder in New Orleans | 1922 | Turner Layton | standard | swing |
Wedding Bells Are Breaking up That Old Gang of Mine | 1929 | Sammy Fain | standard | ballad | | Wedding Bells Are Breaking Up That Old Gang of Mine
Who's Sorry Now? | 1923 | Ted Snyder | standard | swing | ella
Why Do I Love You? | 1927 | Jerome Kern | standard | swing | kern
Why Was I Born? | 1929 | Jerome Kern | standard | ballad | kern ella
With a Song in My Heart | 1929 | Richard Rodgers | standard | ballad | rodgers ella sinatra
Without a Song | 1929 | Vincent Youmans | standard | ballad | sinatra
Yes Sir, That's My Baby | 1925 | Walter Donaldson | standard | swing | sinatra natkingcole
You Brought a New Kind of Love to Me | 1930 | Sammy Fain, Irving Kahal & Pierre Norman | standard | swing | sinatra
You Took Advantage of Me | 1928 | Richard Rodgers | standard | swing | rodgers ella
You're Driving Me Crazy (What Did I Do?) | 1930 | Walter Donaldson | standard | swing | ella | You're Driving Me Crazy
Tin Roof Blues | 1923 | New Orleans Rhythm Kings | standard | ballad | blues
Squeeze Me | 1925 | Fats Waller | standard | swing | waller
West End Blues | 1928 | Joe "King" Oliver | standard | ballad | blues
A Ship Without a Sail | 1929 | Richard Rodgers | standard | ballad | rodgers ella
Chloe | 1927 | Neil Moret | standard | ballad |
Rose of Washington Square | 1920 | James F. Hanley | standard | swing |
A Bird in a Gilded Cage | 1900 | Harry Von Tilzer | oldies | waltz |
A Kiss in the Dark | 1922 | Victor Herbert | oldies | waltz |
After the Ball | 1892 | Charles K. Harris | oldies | waltz |
Ah! Sweet Mystery of Life | 1910 | Victor Herbert | oldies | ballad |
Alice Blue Gown | 1919 | Harry Tierney | oldies | waltz |
Aloha Oe | 1878 | Queen Liliʻuokalani | oldies | ballad |
American Patrol | 1885 | F. W. Meacham | march | march | american
Ballin' the Jack | 1913 | Chris Smith | oldies | march |
Because | 1902 | Guy d'Hardelot | oldies | ballad |
Bill Bailey, Won't You Please Come Home? | 1902 | Hughie Cannon | oldies | march |
By the Light of the Silvery Moon | 1909 | Gus Edwards | oldies | swing |
Chinatown My Chinatown | 1910 | Jean Schwartz | oldies | march | | Chinatown, My Chinatown
Ciribiribin | 1898 | Alberto Pestalozza | oldies | waltz | italian
Colonel Bogey March | 1914 | Kenneth J. Alford | march | march | english
Come Josephine in My Flying Machine (Up She Goes!) | 1910 | Fred Fisher | oldies | waltz | | Come, Josephine, in My Flying Machine
Cuddle Up a Little Closer, Lovey Mine | 1908 | Karl Hoschna | oldies | ballad |
Daddy Wouldn't Buy Me a Bow-Wow | 1892 | Joseph Tabrar | oldies | waltz | english
Dardanella | 1919 | Felix Bernard & Johnny S. Black | oldies | march |
Fascination | 1904 | Fermo Dante Marchetti | oldies | waltz |
Give My Regards to Broadway | 1904 | George M. Cohan | oldies | march | cohan
I Want a Girl (Just Like the Girl That Married Dear Old Dad) | 1911 | Harry Von Tilzer | oldies | march | | I Want a Girl
I'll Be with You in Apple Blossom Time | 1920 | Albert Von Tilzer | oldies | waltz |
I'll Take You Home Again, Kathleen | 1875 | Thomas P. Westendorf | oldies | ballad |
I'm Always Chasing Rainbows | 1918 | Harry Carroll (after Chopin) | oldies | ballad |
I'm Falling in Love with Someone | 1910 | Victor Herbert | oldies | waltz |
I'm Forever Blowing Bubbles | 1919 | John Kellette | oldies | waltz |
Ida! Sweet as Apple Cider | 1903 | Eddie Munson | oldies | march |
If You Were the Only Girl (In the World) | 1916 | Nat D. Ayer | oldies | ballad | | If You Were the Only Girl in the World
In My Merry Oldsmobile | 1905 | Gus Edwards | oldies | waltz |
In the Shade of the Old Apple Tree | 1905 | Egbert Van Alstyne | oldies | waltz |
Indian Summer | 1919 | Victor Herbert | oldies | ballad | sinatra
Keep the Home Fires Burning ('Till the Boys Come Home) | 1914 | Ivor Novello | oldies | march | | Keep the Home Fires Burning
Kiss Me Again | 1905 | Victor Herbert | oldies | waltz |
Let Me Call You Sweetheart | 1910 | Leo Friedman | oldies | waltz |
Lily of Laguna | 1898 | Leslie Stuart | oldies | march | english
Marcheta | 1913 | Victor Schertzinger | oldies | waltz |
Mary's a Grand Old Name | 1905 | George M. Cohan | oldies | ballad | cohan
Melody of Love | 1903 | H. Engelmann | oldies | waltz |
Memories | 1915 | Egbert Van Alstyne | oldies | ballad |
Missouri Waltz | 1914 | Frederic Knight Logan | oldies | waltz |
Moonlight and Roses | 1925 | Edwin H. Lemare (Andantino in D flat) | oldies | ballad |
My Gal Sal | 1905 | Paul Dresser | oldies | ballad |
My Wild Irish Rose | 1899 | Chauncey Olcott | oldies | waltz | irish
Oh Johnny, oh Johnny, Oh! | 1917 | Abe Olman | oldies | march | | Oh Johnny, Oh Johnny, Oh!
On the Banks of the Wabash, Far Away | 1897 | Paul Dresser | oldies | ballad |
Over There | 1917 | George M. Cohan | oldies | march | cohan patriotic
Peg O' My Heart | 1913 | Fred Fisher | oldies | ballad | | Peg o' My Heart
Pretty Baby | 1916 | Tony Jackson & Egbert Van Alstyne | oldies | march |
Rock-a-Bye Your Baby with a Dixie Melody | 1918 | Jean Schwartz | oldies | march |
Roses of Picardy | 1916 | Haydn Wood | oldies | ballad | sinatra
Row, Row, Row | 1912 | James V. Monaco | oldies | march |
School Days | 1907 | Gus Edwards | oldies | waltz |
Second Hand Rose | 1921 | James F. Hanley | oldies | march |
Shine On, Harvest Moon | 1908 | Nora Bayes & Jack Norworth | oldies | ballad | thanksgiving
Silver Threads Among the Gold | 1873 | H. P. Danks | oldies | ballad |
Smilin' Through | 1919 | Arthur A. Penn | oldies | ballad |
The Band Played On | 1895 | Charles B. Ward | oldies | waltz |
The Bells of St. Mary's | 1917 | A. Emmett Adams | oldies | ballad |
The Daring Young Man on the Flying Trapeze | 1867 | Gaston Lyle | oldies | waltz |
The Honeysuckle and the Bee | 1901 | William H. Penn | oldies | march |
The Love Nest | 1920 | Louis A. Hirsch | oldies | ballad |
The Parade of the Wooden Soldiers | 1905 | Leon Jessel | march | march | christmas
The Teddy Bears Picnic | 1907 | John W. Bratton | march | march | children | The Teddy Bears' Picnic
Three O'Clock in the Morning | 1919 | Julián Robledo | oldies | waltz |
Till We Meet Again | 1918 | Richard A. Whiting | oldies | waltz |
Toyland | 1903 | Victor Herbert | oldies | waltz | christmas
Wait Till the Sun Shines Nellie | 1905 | Harry Von Tilzer | oldies | march | | Wait Till the Sun Shines, Nellie
Waiting for the Robert E. Lee | 1912 | Lewis F. Muir | oldies | march |
When Irish Eyes Are Smiling | 1912 | Ernest R. Ball | oldies | waltz | irish
When You Were Sweet Sixteen | 1898 | James Thornton | oldies | ballad |
When You Wore a Tulip and I Wore a Big Red Rose | 1914 | Percy Wenrich | oldies | march | | When You Wore a Tulip
Where the River Shannon Flows | 1905 | James I. Russell | oldies | ballad | irish
Whispering Hope | 1868 | Septimus Winner | oldies | waltz | hymn
Yankee Doodle Boy | 1904 | George M. Cohan | oldies | march | cohan patriotic | The Yankee Doodle Boy
You Made Me Love You | 1913 | James V. Monaco | oldies | ballad |
You Tell Me Your Dream, I'll Tell You Mine | 1899 | Charles N. Daniels | oldies | waltz |
Amapola | 1920 | Joseph Lacalle | oldies | ballad | spanish
La cumparsita | 1916 | Gerardo Matos Rodríguez | oldies | march | tango | La Cumparsita
La paloma | 1863 | Sebastián Yradier | oldies | ballad | spanish | La Paloma
La golondrina | 1862 | Narciso Serradell | oldies | waltz | spanish | La Golondrina
'O sole mio | 1898 | Eduardo di Capua | oldies | ballad | italian
Core 'ngrato | 1911 | Salvatore Cardillo | oldies | ballad | italian
Funiculì funiculà | 1880 | Luigi Denza | oldies | jig | italian
Santa Lucia | 1849 | Neapolitan traditional | folk | waltz | italian
Le temps des cerises | 1866 | Antoine Renard | folk | waltz | french
The Entertainer | 1902 | Scott Joplin | rag | stride | joplin
Maple Leaf Rag | 1899 | Scott Joplin | rag | stride | joplin
The Stars and Stripes Forever | 1897 | John Philip Sousa | march | march | american patriotic
Radetzky-Marsch | 1848 | Johann Strauss I | classical | march | | Radetzky March
Für Elise | 1810 | Ludwig van Beethoven | classical | flowing |
Hungarian Dance No. 5 in F♯ minor | 1869 | Johannes Brahms | classical | march | | Hungarian Dance No. 5
Liebestraum Nr. 3 | 1850 | Franz Liszt | classical | flowing | | Liebestraum No. 3
Intermezzo | 1890 | Pietro Mascagni (Cavalleria rusticana) | classical | flowing | opera | Intermezzo from Cavalleria Rusticana
Rêverie | 1890 | Claude Debussy | classical | flowing |
O mio babbino caro | 1918 | Giacomo Puccini (Gianni Schicchi) | classical | flowing | opera
Je crois entendre encore | 1863 | Georges Bizet (The Pearl Fishers) | classical | flowing | opera
Ave Maria | 1859 | Charles Gounod, on a prelude by J. S. Bach | classical | flowing | church
Jesu, Joy of Man's Desiring | 1723 | Johann Sebastian Bach | classical | flowing | church
Jerusalem | 1916 | C. Hubert H. Parry | hymn | chorale | english
The Holy City | 1892 | Stephen Adams | oldies | ballad | church
Song of the Indian Guest {Песня Индийского гостя} | 1896 | Nikolai Rimsky-Korsakov (Sadko) | classical | flowing | opera | Song of India
Alouette | 0 | French-Canadian traditional | folk | march | children french
Annie Laurie | 1838 | Alicia Scott | folk | ballad | scottish
Auld Lang Syne | 0 | Scottish traditional | folk | ballad | scottish newyear
Banks of the Ohio | 0 | American traditional | folk | ballad | american
Careless Love | 0 | American traditional | folk | ballad | american blues
Drink to Me Only with Thine Eyes | 0 | English traditional | folk | ballad | english
For He's a Jolly Good Fellow | 0 | Traditional | folk | jig | children
Frankie and Johnny | 0 | American traditional | folk | swing | american blues
Home on the Range | 1873 | Daniel E. Kelley | folk | waltz | american
Home Sweet Home | 1823 | Henry Bishop | folk | ballad | english | Home, Sweet Home
Loch Lomond | 0 | Scottish traditional | folk | ballad | scottish
Mademoiselle from Armentières | 1915 | Traditional (World War I) | folk | jig |
Molly Malone | 0 | Irish traditional | folk | waltz | irish
On Top of Old Smoky | 0 | American traditional | folk | waltz | american
Polly Wolly Doodle | 0 | American traditional | folk | march | american children
Red River Valley | 0 | American traditional | folk | ballad | american
Scarborough Fair | 0 | English traditional | folk | waltz | english
Shady Grove | 0 | American traditional | folk | march | american
Shenandoah | 0 | American traditional (river shanty) | folk | ballad | american sea
Simple Gifts | 1848 | Joseph Brackett (Shaker song) | folk | march | american thanksgiving hymn
The Skye Boat Song | 0 | Scottish traditional air | folk | jig | scottish
The Ash Grove | 0 | Welsh traditional (Llwyn Onn) | folk | waltz | welsh thanksgiving
The Black Velvet Band | 0 | Irish traditional | folk | waltz | irish
There Is a Tavern in the Town | 0 | English traditional | folk | march | english
Waltzing Matilda | 1895 | Christina Macpherson / Marie Cowan | folk | march | australian
The Wild Rover | 0 | Irish traditional | folk | waltz | irish
The Wild Colonial Boy | 0 | Irish/Australian traditional | folk | waltz | irish australian
Yellow Rose of Texas | 1858 | American traditional | folk | march | american | The Yellow Rose of Texas
What Shall We Do with a Drunken Sailor? | 0 | Sea shanty (traditional) | folk | march | sea
The Road to the Isles | 1917 | Scottish traditional pipe tune | folk | march | scottish
Calon Lân | 1899 | John Hughes | hymn | waltz | welsh
Happy Birthday to You | 1893 | Mildred J. Hill & Patty Hill | folk | waltz | children
Carry Me Back to Old Virginny | 1878 | James A. Bland | folk | ballad | american
Beautiful Dreamer | 1864 | Stephen Foster | folk | jig | american foster
Gwine to Run All Night, or De Camptown Races | 1850 | Stephen Foster | folk | march | american foster | Camptown Races
Hard Times Come Again No More | 1854 | Stephen Foster | folk | ballad | american foster
Jeanie with the Light Brown Hair | 1854 | Stephen Foster | folk | ballad | american foster
My Old Kentucky Home - Good-Night! | 1853 | Stephen Foster | folk | ballad | american foster | My Old Kentucky Home
Old Folks at Home | 1851 | Stephen Foster | folk | ballad | american foster | Old Folks at Home (Swanee River)
America the Beautiful | 1882 | Samuel A. Ward | patriotic | chorale | american patriotic thanksgiving
Battle Hymn of the Republic | 1856 | William Steffe | patriotic | march | american patriotic
The Battle Cry of Freedom | 1862 | George F. Root | patriotic | march | american patriotic
I Wish I Was in Dixie's Land | 1859 | Daniel Decatur Emmett | patriotic | march | american | Dixie
La Marseillaise | 1792 | Claude Joseph Rouget de Lisle | patriotic | march | french
Down by the Riverside | 0 | African-American spiritual | spiritual | march | spiritual
Go Tell It on the Mountain | 0 | African-American spiritual | spiritual | march | spiritual christmas
He's Got the Whole World in His Hands | 0 | African-American spiritual | spiritual | march | spiritual children
Joshua Fit the Battle of Jericho | 0 | African-American spiritual | spiritual | march | spiritual
Just a Closer Walk with Thee | 0 | Traditional gospel song | spiritual | ballad | spiritual
Let Us Break Bread Together | 0 | African-American spiritual | spiritual | ballad | spiritual communion
Sometimes I Feel Like a Motherless Child | 0 | African-American spiritual | spiritual | ballad | spiritual
Swing Low, Sweet Chariot | 0 | African-American spiritual (Wallace Willis) | spiritual | ballad | spiritual
Were You There When They Crucified My Lord | 0 | African-American spiritual | spiritual | ballad | spiritual lent good-friday | Were You There
Didn't My Lord Deliver Daniel | 0 | African-American spiritual | spiritual | march | spiritual
Angels We Have Heard on High | 0 | French traditional carol (Gloria) | carol | march | christmas
Angels from the Realms of Glory | 1867 | Henry Smart (Regent Square) | carol | chorale | christmas
Bring a Torch, Jeanette, Isabella | 0 | French traditional carol (Provence) | carol | waltz | christmas
Coventry Carol | 0 | English traditional carol (16th century) | carol | waltz | christmas
Hark! The Herald Angels Sing | 1840 | Felix Mendelssohn | carol | chorale | christmas
I Heard the Bells on Christmas Day | 1872 | John Baptiste Calkin | carol | chorale | christmas
I Saw Three Ships | 0 | English traditional carol | carol | jig | christmas
In the Bleak Midwinter | 1906 | Gustav Holst (Cranham) | carol | ballad | christmas
It Came upon the Midnight Clear | 1850 | Richard Storrs Willis (Carol) | carol | jig | christmas
Jingle Bells | 1857 | James Lord Pierpont | carol | march | christmas
Joy to the World | 1839 | Lowell Mason (Antioch) | carol | march | christmas
O Christmas Tree | 0 | German traditional (O Tannenbaum) | carol | waltz | christmas
O Come, All Ye Faithful | 1751 | John Francis Wade (Adeste Fideles) | carol | chorale | christmas
O Little Town of Bethlehem | 1868 | Lewis Redner (St. Louis) | carol | ballad | christmas
Still, Still, Still | 0 | Austrian traditional carol | carol | lullaby | christmas
The Holly and the Ivy | 0 | English traditional carol | carol | waltz | christmas
Up on the Housetop | 1864 | Benjamin Hanby | carol | march | christmas children
We Wish You a Merry Christmas | 0 | English traditional carol | carol | waltz | christmas
Wexford Carol | 0 | Irish traditional carol | carol | waltz | christmas irish | The Wexford Carol
What Child Is This? | 0 | English traditional (Greensleeves) | carol | jig | christmas | What Child Is This? (Greensleeves)
How Can I Keep from Singing? | 1868 | Robert Lowry | hymn | waltz | hymn trust
Life's Railway to Heaven | 1890 | Charles D. Tillman | hymn | waltz | hymn gospel
In the Garden | 1912 | C. Austin Miles | hymn | jig | hymn gospel
"""


def main():
    src = Path(sys.argv[1])
    root = Path(__file__).resolve().parent.parent / "library"
    con = sqlite3.connect(str(src / "OpenEWLD.db"))
    rows = con.execute("select title, path_leadsheet from works order by id").fetchall()
    by_title: dict = {}
    for title, path in rows:
        by_title.setdefault(title, []).append(path)
    existing = {p.stem for p in root.rglob("*.abc")}
    done = 0
    problems = []
    folder = {"standard": "standards", "oldies": "oldies", "march": "oldies", "rag": "rags",
              "classical": "classical", "folk": "folk", "patriotic": "folk", "spiritual": "spirituals",
              "carol": "carols", "hymn": "hymns-leadsheet"}
    for line in TABLE.strip().splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 6:
            problems.append((line, "bad table row"))
            continue
        title, year, credit, category, style, tags = parts[:6]
        new_title = parts[6] if len(parts) > 6 and parts[6] else title
        year = int(year)
        if year > 1930:
            problems.append((title, "not public domain in the US"))
            continue
        paths = by_title.get(title)
        if not paths:
            problems.append((title, "not in dataset"))
            continue
        best = None
        why = ""
        for rel in paths:
            f = src / rel
            if not f.exists():
                why = "file missing"
                continue
            try:
                t = read_musicxml(f)
            except Exception as exc:
                why = f"{type(exc).__name__}: {exc}"
                continue
            pr = validate(t)
            if any(b.meter is not None for b in t.bars):
                pr.append("meter change")
            if not t.has_chords:
                pr.append("no chords")
            if pr:
                why = "; ".join(pr[:2])
                continue
            n_chords = sum(len(b.chords) for b in t.bars)
            if best is None or n_chords > best[0]:
                best = (n_chords, t)
        if best is None:
            problems.append((title, why))
            continue
        tune = best[1]
        infer_minor(tune)
        tune.title = new_title
        tune.composer = credit + (f", {year}" if year and str(year) not in credit else "")
        tune.year = year or None
        tune.category = category
        tune.tags = tags.split()
        tune.style = style
        tune.source = "OpenEWLD"
        tune.credit = ("Melody and chords: public domain in the United States"
                       + (f" (published {year})" if year else " (traditional)")
                       + "; lead sheet from OpenEWLD.")
        if not tune.tempo_set:
            tune.tempo = 0
        elif tune.meter.beat_len != 1:
            tune.tempo = int(round(tune.tempo / float(tune.meter.beat_len)))
        slug = slugify(new_title)
        if slug in existing:
            continue
        existing.add(slug)
        tune.slug = slug
        text = write_abc(tune)
        back = tune_from_abc(parse_abc(text)[0])
        if len(back.bars) != len(tune.bars) or any(a.melody != b.melody or a.chords != b.chords
                                                   for a, b in zip(tune.bars, back.bars)):
            problems.append((title, "round-trip mismatch"))
            existing.discard(slug)
            continue
        sub = folder.get(category, "folk")
        (root / sub).mkdir(parents=True, exist_ok=True)
        (root / sub / f"{slug}.abc").write_text(text, encoding="utf-8")
        done += 1
    print(f"imported {done}")
    for p in problems:
        print("  problem:", p)


if __name__ == "__main__":
    main()
