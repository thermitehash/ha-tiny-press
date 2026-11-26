# Bundled data: sources and licenses

Tiny Press prefers human-written content from reputable sources whose terms
allow redistribution. Each file below lists where its content comes from.

## `facts.json`: fun facts (111)

Every fact cites the exact page it comes from (`url`) and its publisher
(`source`). Facts are shortened and simplified for 2nd–3rd grade readers
without changing their meaning.

| Source | Facts | License |
|---|---|---|
| NOAA Ocean Facts, oceanservice.noaa.gov/facts | 65 | U.S. federal government work, public domain under 17 U.S.C. §105 |
| NASA Science planet fact pages, science.nasa.gov | 40 | U.S. federal government work, public domain under 17 U.S.C. §105 |
| National Park Service, nps.gov | 6 | U.S. federal government work, public domain under 17 U.S.C. §105 |

Only text written by the agencies is used. Photos and third-party material on
those pages are not used. See https://www.usa.gov/government-copyright.

NASA Space Place was considered and not used. It is produced at JPL (managed
by Caltech), and its terms only cover images, so it is not clearly a
public-domain federal work.

## `words.json`: word-search words by grade

| Grade | Source | License |
|---|---|---|
| K | Dolch sight words: pre-primer and primer lists | See below |
| 1 | Dolch first-grade list plus the Dolch nouns | See below |
| 2 | Dolch second-grade list | See below |
| 3 | Dolch third-grade list | See below |
| 4–5 | Compiled for Tiny Press (MIT) | Placeholder until a public-domain graded speller is added |

The Dolch lists were compiled by Edward W. Dolch and published in "A Basic
Sight Vocabulary", *The Elementary School Journal*, 1936, and in *Problems in
Reading*, Garrard Press, 1948. The words are common English words, which
copyright does not protect individually. Copy used:
https://en.wikipedia.org/wiki/Dolch_word_list. Only words with three or more
letters are kept (for word searches). "Christmas" and "Santa Claus" are left
out to keep the list neutral.

## `themes.json`: interest word lists

Short lists of everyday words per interest (space, dinosaurs, horses, …),
compiled for Tiny Press (MIT). Single common words are not copyrightable.

## `jokes.json`: jokes and riddles

Currently compiled for Tiny Press (MIT). Planned replacement: riddles from
public-domain children's riddle books on Project Gutenberg (published in the
U.S. before 1930), each credited to its book. Project Gutenberg was down for
maintenance when this version was made.

## `vocab.json`: morning slip vocabulary words (200)

Hard, SAT-style words picked for Tiny Press. Each word's part of speech,
definition and example sentence (where there is one) come unchanged from
**Open English WordNet** (https://github.com/globalwordnet/english-wordnet),
choosing the sense the word is usually tested for.

Open English WordNet is derived from Princeton WordNet under the WordNet
License and further developed under the Creative Commons Attribution 4.0
International License (CC BY 4.0, https://creativecommons.org/licenses/by/4.0/).
Attribution: Princeton WordNet (WordNet 3.0, © 2006 Princeton University)
and the Open English WordNet team. Every printed definition is credited
"Open English WordNet (CC BY 4.0)".

## `quotes.json`: cryptogram and morning slip quotes (27)

Short quotes from public-domain works, each with its author (and work, where
known) and the National Park Service page it was taken from (`url`). The NPS
pages are U.S. federal works. The quotes themselves are from:

- Theodore Roosevelt (1858–1919): his books and speeches, all published before 1931.
- John Muir (1838–1914): only works published before 1931 (*Our National Parks* 1901, *My First Summer in the Sierra* 1911, *The Yosemite* 1912, *The Story of My Boyhood and Youth* 1913, *A Thousand-Mile Walk to the Gulf* 1916, *Steep Trails* 1918) and his letters of 1868 and 1873. Quotes the NPS marks as of uncertain origin are left out. So are quotes from books first published after 1930 (*John of the Mountains* 1938, *Son of the Wilderness* 1945).
- Abraham Lincoln (1859 speech) and William Shakespeare (*Troilus and Cressida*).

Planned additions, once the sources are reachable: Benjamin Franklin's
*Poor Richard* sayings and Aesop's morals from Project Gutenberg or Wikisource.

## `crossword.json`: crossword words and clues (213)

Written for Tiny Press (MIT). Each word has a straight clue and a wordplay
("NYT-style") clue. There is no openly licensed collection of NYT-style clues
to draw on, so these clues are original. Words are everyday vocabulary, with
no obscure "crosswordese". No clue contains its own answer.

## `stories.json`: offline bedtime stories (6)

Two stories per length (short, medium, long), written for Tiny Press (MIT).
They print when no AI task entity is set or the AI fails. Planned additions:
gentle public-domain classics (Thornton W. Burgess, Beatrix Potter, Aesop)
from Project Gutenberg, each credited.

## `observances.json`: holidays and themes

Banners, ASCII art, word lists, crossword clues and themed jokes were written
for Tiny Press. Descriptions are short, neutral and factual.

Moving dates (lunar and lunisolar holidays, 2026–2035) were generated with
`script/build_observances.py` from the calendars in the
[python-holidays](https://github.com/vacanza/holidays) library (MIT license).
Islamic dates follow its calculated calendar and can differ by a day where the
moon is sighted locally; Vesak follows Indonesia's date. Fixed days, Easter
(Western and Orthodox), "nth weekday" days and the solstices and equinoxes
(Meeus, *Astronomical Algorithms*) are computed at runtime.
