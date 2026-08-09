# weather-viewdata, as built

The weather, served as Viewdata frames. Forecasts from the Norwegian
Meteorological Institute; places from a local GeoNames index.

## Why it exists

**To be a third application.** Two applications made the framework's claim
plausible and could not test it: Stardot is what Sextile was cut out of, and
`calendar-viewdata` depends on nothing but the standard library. A service with
an archive it built itself, a network dependency with terms of use, and a
numbering scheme with two namespaces is a harder question.

The result, recorded here because it will not be obvious later: **this is the
first application to have required a change to the framework at all.** The
calendar's design document records that it needed none. This one found five
things in a day, and every one of them was the same thing — registration order
being observable. See [what it asked for](#what-it-asked-of-the-framework).

## The shape of the thing

```
   GeoNames' dump
        |  dump          download, conditional; zip or plain
        v
   geonames        Place                             nineteen columns, thirteen wanted
        |
   places          search_key                        the fold to what a keypad sends
        |
   store/          Index, schema.sql                 the ranked place index
        |
   forecast/       model, source, met                Forecast and Moment; met.no behind a port
        |
   application     pages, ForecastTable              what a page shows
        |
   Sextile
```

`__main__.py` carries the commands that are this application's own:
`import-places`, and defaulted `serve`/`render`.

## Numbering

```
0                  the title frame the line opens on; # carries on to the index
1                  the main menu
3                  find a place by name        321<geoname-id>  its forecast
4                  find a point by position    421<lat><lon>    its forecast
9  about   90 goodbye   91 help   92/93/94 the framework's pages
                       95 what the pictures mean
```

Stardot's convention, and for its reasons: the first digit names a namespace and
the second says what kind of page within it. A namespace's root would be its
index, and here it cannot be — nobody lists 235,176 places on a screen — so the
root is the page that explains how to search it.

**A third digit says how it is drawn.** A forecast is one body of numbers with
more than one honest way of showing it — a table reads exactly, a graph reads at
a glance, a map may follow — and neither is a mode of the other. So the
presentation is part of the address: `1` a table, `2` a graph, and the subject
follows unchanged, so the same weather is `321<geoname-id>` and
`322<geoname-id>`.

That is worth a digit rather than a keypress that toggles, because a page number
is the thing a reader writes down. A number written down must fetch back what
was written down; a frame that remembered how it was last looked at would not.

It goes *before* the subject because a geoname id has no width known in advance:
`321` and then an id can be taken apart, `32` and then an id and then a digit
cannot. The cost is that the digit renumbers everything after it — `323133880`
now reads as the graph of 133880 — so there are no aliases for the old numbers
and none are possible.

**Two ways to name a forecast, and they fail differently.** That is why both
exist rather than one being the poor relation:

| | carries | depends on |
|---|---|---|
| `321<geoname-id>` | a name, a timezone, an altitude | GeoNames still holding that record |
| `421<lat><lon>` | coordinates, and says so | nothing at all |

A coordinate page number is stable by construction: 63.4N 10.4E will mean the
same thing for as long as there is an earth. A geoname id is *nearly* stable —
GeoNames publishes daily deletions, one line worldwide on 8 August 2026 — and
the likelier way it dies has nothing to do with ids at all: `cities500` means
*population over 500 or an administrative seat*, so a village revised from 520
to 480 leaves our extract while its id stays perfectly valid. The id did not
move; our window onto the ids did. Pinned as tests in
`tests/test_place_identifiers.py`.

**One decimal place of position**, which is four digits an axis biased positive
— there is no minus key on a viewdata keypad and no separator in a page number,
so two fields side by side must each be a fixed width. It is 11.1km of latitude
everywhere and 11.1km of longitude at the equator, narrowing with the cosine:
5.0km at Trondheim, 2.3km at Longyearbyen.

The position *is* in the page number, though nothing on the frame spells out
how. 59.7N 10.0E is tenths of a degree, biased into a positive range — south
pole zero, date line zero — and zero-padded:

```
59.7N  ->  (59.7 + 90) × 10  =  1497
10.0E  ->  (10.0 + 180) × 10 = 1900
                                          421 1497 1900
```

so the search leaves the reader on `42114971900`, which is the number to write
down. It is legible with the arithmetic in hand and not otherwise, which is the
price of having no minus key and no separator. The frame says the position in
degrees at the top; the number is what fetches it back.

That resolution decides what the page can honestly *be*. Measured against the
real index, 67% of places share a cell with another and one cell in Hong Kong
holds 182 of them — so a coordinate page cannot name a town and does not
pretend to. It is the weather *about here*, and it borrows a clock from the
nearest known place because timezone borders follow habitation.

Longitude wraps and latitude does not: 190°E is 170°W spelled unusually and is
taken quietly, where 91°N is a mistake and is refused. The date line gets one
page number rather than two.

## The weather as a picture

**41 symbol ids, 21 of them with `_day`, `_night` and `_polartwilight`
variants: 83 codes.** met.no's `symbol_code` is yr's own symbol set — the same
names NRK publish icons for — and the published list is captured as
`tests/data/met-symbols.csv`, with a test that takes every code in it apart.

That test earned its keep immediately. **Two codes are misspelled at the
source**: `lightssleetshowersandthunder` and `lightssnowshowersandthunder`, with
two esses, in met.no's own legend and in NRK's set, for codes 26 and 28. `lights`
is not an intensity, so the core was never found and the whole code came back
raw — twenty-eight characters trimmed to nonsense in a sixteen-cell column, on
exactly the sort of afternoon a reader would want to know about.

### The grammar

Eighty-three codes and about a dozen drawings, because the codes are built by
concatenation and the pictures are built the same way. `symbols.taken_apart` is
the one place that knows how a code is spelled; `in_words` says it and
`icons.py` draws it, so the two cannot drift apart the way the two folds of a
place name once did.

**Nine cells, and their shape is decided by what an attribute costs.** A mosaic
run needs a graphics colour attribute and an attribute takes a cell, so an hour
column four cells wide is one attribute and three cells of picture, on each of
three rows — **one colour to a row, unless the row buys a second one out of its
own picture.** Two attributes and two mosaics also come to four, and leave two
blocks, a blank, two blocks.

That decides every drawing. A sun cannot sit *behind* a cloud in a different
colour, because a full-width band has one colour to spend; so it sits *above*
one, and the icon becomes three bands:

| band | holds | colour |
|---|---|---|
| top | sun, moon, or the top of a cloud | yellow, white, cyan |
| middle | the cloud, or the sun where there is none | cyan, or yellow |
| bottom | what is falling, or a bolt | blue, cyan, white, or yellow |

and the code chooses the pieces:

```
sky      showers or nothing falling -> sun      (moon if _night)
         otherwise                  -> cloud top
cloud    fair -> a small one;  anything else -> a cloud
fall     rain -> strokes, blue      light: two, clear of the cloud
         sleet -> strokes and dots, cyan    middling: three, clear of it
         snow -> flakes, white              heavy: three, touching it
         thunder -> the band splits: the fall on the left in its own
                    colour, a yellow bolt on the right
fog      the same bars through all three bands
```

**The composition explains something in met.no's list that looks arbitrary.**
Only the *showers* codes have `_day` and `_night` variants — and it is because
only they have the sun in them: a shower has sky between the clouds and
continuous rain has not. That is exactly the rule the top band follows, so the
21 ids with variants are precisely the 21 the grammar draws a sun on.

Three consequences worth writing down, since each was a choice:

- **The cloud is always on the same row.** A dry hour leaves the bottom band
  empty rather than sitting lower, because in a strip of hours side by side a
  cloud line that moved up and down would read as weather changing when it is
  not.
- **Thunder is the one band that splits.** It is worth the cell: six of the 41
  symbols carry thunder, and drawn in the fall's own colour they would differ
  from the six plain ones by nothing at all. What falls keeps its colour on the
  left, the bolt is yellow on the right, and the blank between them is the
  attribute that paid for it. The pitch of the strip is untouched, because the
  cell came out of the picture rather than out of the column.
- **Heavier weather is more blocks**, and it fills the row nearest the cloud —
  so heavy rain touches what it falls from. It is the one rule a reader can
  learn without being told.

### `*95#`, the whole set

Every published symbol with its words, two to a row, three rows each, over four
frames. One at a time small pictures all look plausible; side by side, the two
that cannot be told apart show up at once. It is also what a reader needs, since
the table says `sleet shwrs` and gives no other clue what the picture over it
means.

The day variants only, with a line saying the sun becomes a moon at night —
which costs less than another forty drawings. Names wrap over two of the three
rows, because `heavy sleet shwrs+thunder` is twenty-five cells and half a row is
fourteen.

## The place index

SQLite, two tables. Places, and every folded string that finds one.

**The fold is to A–Z, and it is taken from what the screen shows.** Sextile
already reduces text to what the G0 set can draw — it must, or a frame would
carry bytes the hardware cannot display — and a reader keys what they see. So
the search key is that same fold with everything but the letters dropped, and
the two cannot drift apart. They did once, when this module had a table of its
own: it knew four letters the framework's did not, so `Đakovo` was findable
while the screen said `?akovo`.

`TROMSO` therefore finds Tromsø and `MUNCHEN` finds München, because that is
how the screen spells them. Digits go too — on a search frame they are spoken
for by the suggestions — so `Quận 1` is found by keying `QUAN`. What is folded
is never the data: the place is still held, forecast and *called* Tromsø.

**The ranking is computed on the way in, never at query time.** A search frame
repaints while the reader is still typing, so a keystroke may cost an indexed
range scan and an `ORDER BY` on a stored column and nothing more. It is
population on a log scale, plus what kind of place it is, plus whether it is in
the country the service is pointed at — summed rather than multiplied, so a
population of zero does not annihilate the rest. A keystroke costs 0.08ms
against 0.3–0.8 seconds of wire.

**Exactness is added to the ranking, not sorted before it.** Sorted before it,
`BERGEN` gets Bergen ahead of a larger Bergenfield — right — but `LON` gets
Lognes ahead of London on the strength of an alternate name reading `Lon'`, and
`BER` gets a French hamlet called Beure ahead of Bergen. A short alias is worth
something and it is not worth more than being a city.

**Whose weather the service is about is a setting worth a tenfold of
population**, not an override. It is a global service whose readers mostly
happen to be in one country, so home should break a tie between comparable
places and should not put Boston in Lincolnshire above Boston in Massachusetts.
A bonus of a thousandfold did exactly that.

### Only a place's own name is indexed

The dump's alternate-names column was indexed once, and it was a mistake that
took three rounds of filtering to stop being obviously wrong and never stopped
being wrong at all. It holds genuine names, IATA airport codes and romanisations
from other writing systems, with nothing to say which is which — Oslo's holds
`Christiania`, `OSL` and `awslw` — so `TRO` offered Taree, whose airport code it
is, and `A` offered Oslo by way of `Asloa`. Madrid arrived under the key `A`,
from an alternate reading `Мaдрид`: Cyrillic with a Latin `a` typed into the
middle of it.

**What a reader types is now a prefix of the place's own name and nothing
else**, so every suggestion visibly begins with what they keyed. All three
filtering rules went with the column, and the index is 57% smaller: 238,498
keys against 560,552.

What that cost is smaller than it sounds. GeoNames' own `name` is already the
name an English reader knows — Munich, Vienna, Prague, Rome, Moscow, Tokyo and
Beijing are all filed under exactly those. Köln is the exception, so `COLOGNE`
finds nothing, and `MUNCHEN` now finds Münchenstein rather than Munich, which
is not spelled that way in the dump.

Both want `alternateNamesV2`, whose entries carry a language tag: index the
English and local-language ones and neither problem arises. Noted in
[open-questions.md](../../../docs/open-questions.md) as the obvious next step if
anybody misses Cologne.

### An index built by older rules is refused

The index is derived data and the rules that derive it live in code, so changing
them does nothing until somebody re-imports — and until they do, the service
answers by the old rules with nothing whatever to say so. That is exactly what
happened when alternate names stopped being indexed: keying `A` went on offering
Cairo long after the code had stopped meaning it to.

So the index records which rules built it, in SQLite's own `user_version`, and
the service refuses to start on a stale one and says what to run. A refusal
rather than a warning, because the failure mode is not a crash but a wrong
answer given confidently on a line slow enough that nobody would question it.
Raise `store.RULES` whenever the folding or the ranking changes; nothing checks
that you remembered.

## Politeness

met.no asks for an identifying User-Agent with somewhere to complain to, at
most twenty requests a second, `Expires` honoured, `If-Modified-Since` sent with
the *exact* `Last-Modified` value, responses cached, and requests spread out.
The stated penalty for ignoring any of it is being blocked without warning.

So the terms are structural rather than remembered: there is no method that asks
twice inside an `Expires` window, none that asks anonymously, and none that
bunches requests. A conditional request quotes the string it was given rather
than a datetime round-tripped through our own formatting — equivalent is not
exact.

**Two of the terms were measured and found not to be enforced at their end.** A
request with no User-Agent was answered, and so was one carrying ten decimal
places of latitude. That is written down as measured, and complied with anyway.
Coordinates are rounded to four places regardless, because two readers asking
about the same town should be one request.

**There is a floor under how long an answer is held.** A response whose
`Expires` has already passed — a clock adrift, a cache misconfigured — would
otherwise mean re-fetching on every request, which is the very traffic the
header exists to prevent, done by us. Their mistake should not become our
rudeness.

A refusal returns `None` and is not cached, so a page can say the forecast is
unavailable rather than drawing an empty one — which on a weather service reads
as calm weather, the one wrong answer it must not give.

## Drawing a forecast

`_forecast_page` in `application.py` builds it, and `ForecastTable` — a
`Template[Moment]` — deals the moments into frames. Both `321<geoname-id>` and
`421<lat><lon>` end here; the only difference is what the preamble says.

A page with nothing to show says why: no forecast is a `Prose` page explaining
that met.no did not answer and that it is our trouble rather than the reader's.
An empty table would read as calm weather, which is the one wrong answer a
weather service must not give.

### What is on it

```
 TRONDHEIM                   3213133880a
  ▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮
NO  63.4N 10.4E  18m
Times UTC and CEST (UTC+2)
Issued 12:30 UTC

NOW   13:00   15:00   heavy rain
15.3C   SW 2.3m/s   0.4mm/h

   UTC LOCAL  DEG C  M/S  WEATHER
 13:00  15:00   15.3  2.3 heavy rain
 14:00  16:00   15.1  1.6 rain
 ...                          (12 rows)
  ▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮
 S page down, 0 index
```

A real response is **86 moments over ten days**, which comes to **five frames**:
twelve rows on the first after the lead-in, sixteen on the rest.

### The weather now

Two rows at the top, above the table, because a forecast page is mostly about
later and the first thing a reader wants is now. Before this it was the first
row of a table of eighty-six, indistinguishable from the hour after it.

**The clocks carry no labels.** `Times UTC and CEST` has just been said a row
above, and the colours say it again — **yellow for UTC, cyan for the place's own
clock**, the same convention as the table's two columns — so the four cells go
on the weather instead.

**The times are the moment's own, not the reader's.** A forecast is held for as
long as met.no asks it to be, so the hour a reader is standing in may have begun
forty minutes ago. Saying `13:00` at 13:47 lets them see that; saying `13:47`
would claim a reading we have not got. `Forecast.current` takes the last moment
that has *started* rather than the nearest — at 13:59 the weather is still the
one o'clock hour's — and falls forward to the first moment where the whole
forecast is still ahead, since an answer fetched at 09:58 can begin at 10:00.

**The weather goes last on its row**, and `RowWriter.runs` trims what will not
fit, so `heavy sleet shwrs+thunder` costs the end of itself rather than the
frame. No hand-arithmetic about how many cells are left, which is what got the
table's weather column wrong the first time.

**A reading with no figure is left out, not dashed.** The opposite of the table
below, and for a reason: a dash in a column says the column is still there to be
read, where three words with a gap where the fourth was reads as a fault. The
rainfall says what period it is for — `0.4mm/h` against `1.7mm/6h` — because
1.7mm in an hour and 1.7mm over six are different weather.

**Wind direction is sixteen points of the compass**, in `wind.py`, and it is the
direction the wind blows *from*: `wind_from_direction` is met.no's and
meteorology's convention, and saying it the other way round would be wrong
rather than unusual. Sixteen because eight loses the difference between a
southerly and a south-westerly, and the third letter costs one cell. No arrow:
the G0 set has three of the four it would need.

**Times in UTC and in the place's own zone.** `zoneinfo` reads the system
database and GeoNames gives the IANA name per place, so daylight saving is
handled and named — `Times UTC and CEST (UTC+2)`. Not every zone has letters:
Fiji reports `+12`, so the abbreviation is only shown where it is one. A point
page borrows the zone from the nearest known place, timezone borders following
habitation, and says `Times UTC` where there is nothing within a degree.

**The issue time is worth its row.** met.no runs its models a few times a day,
so a forecast fetched at nine may have been made at five, and a reader on a slow
line deciding whether to ask again wants to know which.

**A missing reading is a dash and never a nought.** Nought degrees is weather
and no reading is not. Tromsø has no elevation at all in `cities500`, which is
what made that concrete rather than theoretical.

**Column headings on every frame**, which is why `Template` grew `headings`: a
reader on frame c looking at four columns of figures has no way back to the
words that say which is the temperature and which the wind.

**The weather column takes whatever the row has left**, counted from the row
rather than worked out by hand — an attribute costs a cell, and hand-arithmetic
about that was wrong the first time. met.no's longest symbol,
`heavy sleet shwrs+thunder`, is twenty-five cells and does not fit; it is
shortened rather than allowed to overrun. `symbols.py` takes the codes apart
rather than tabulating ninety of them.

**Nothing on it is selectable.** A forecast is something to read, not a menu, so
no digit is spent on the rows and `1`–`9` do nothing — which is the rule about
naming only the keys that work rather than an exception to it. The only key that
leads anywhere is `0`.

### What it does not yet do

Written down because none of it is obvious from the code, and the page has had
no iteration since its first draft.

- **No dates anywhere.** Ten days of forecast and nothing says which day a row
  belongs to. It is worst on the later frames, where the series has coarsened
  to six-hourly and reads `12:00 18:00 00:00 06:00` over and over with no
  indication of which day is which. This is the most obviously wrong thing
  about the page.
- **The resolution changes silently.** met.no is hourly for two or three days
  and six-hourly after, and the rows give no sign of the switch. `Moment.covers`
  knows — it is `1h` or `6h` or `12h` — and nothing uses it.
- **Precipitation reaches the screen only in the now block.** The table's rows
  still do not show it, though `Moment.precipitation` and `Moment.covers` are
  there for them.
- **Cloud cover, humidity and pressure are parsed and unused**, all three on
  `Moment` and none of them drawn anywhere.
- **Five frames is a lot of `S`.** A frame is about eight seconds at 1200 baud,
  so reading to the end of the week costs the better part of a minute. A daily
  summary — one row a day, high and low and a symbol — would be a different and
  probably more useful page.
- **No keys but `0`.** The page offers nothing: not the neighbouring days, not
  the place's own position page, not back to the search. `request.arrival` is
  ignored, so a reader who arrived through a suggestion list is offered no way
  along it.
- **The last row has no weather.** Correct — the final moment carries no summary
  block, there being no next hour inside the forecast — but it reads as a gap
  rather than as the end.

### The data available to draw with

`forecast/model.py`. Every reading is optional, because a missing reading is not
nought:

| `Forecast` | |
|---|---|
| `updated_at` | when the model was run, not when we fetched it |
| `moments` | in time order, hourly then coarser |

| `Moment` | |
|---|---|
| `at` | UTC; the place's zone is applied when drawing |
| `temperature` | Celsius |
| `wind_speed`, `wind_from` | m/s, and degrees blown *from* |
| `cloud_cover`, `humidity` | percent |
| `pressure` | hPa at sea level |
| `symbol` | met.no's own word — `rain`, `partlycloudy_day` |
| `precipitation` | mm over `covers` |
| `covers` | what `symbol` and `precipitation` describe; None on the last |

## What it asked of the framework

Five things, and the first four were one thing wearing four hats: **registration
order was observable**, so each style of declaring a service was missing
whatever the other had.

- A converter could not be registered in time for a class-declared pattern that
  used one — `self.converter` needs a router that `super().__init__` creates and
  then immediately uses. Not a missing feature; an unfixable ordering deadlock
  in that style.
- A module-level application could not open anything, could not resolve a word
  of its own, and could not say a page's keywords beside it.
- `Handler` was typed as returning a `Page`, so the decorator refused the
  `-> Page | None` handlers the documentation showed on that very decorator.

The answer was to follow Starlette: a lifespan yielding what the service holds,
`request.application`, pages declared as data, and a middleware stack. See
[sextile/docs/design.md](../../sextile/docs/design.md).

## The two search pages

Both are forms: pages a reader types into, which is the one thing a viewdata
page could not previously do. The seam is the framework's — see
[sextile/docs/design.md](../../sextile/docs/design.md) — and what is here is
what a weather service does with it.

### 3, finding a place by name

A field, and the best three matching places beneath it, each on a digit. Typing
narrows them; `1`–`3` choose one; `#` takes the first, marked against it.

**Three and not nine, and the wire decided it.** Measured on real Commstar in
[spike_suggestion_block.py](../../../docs/spikes/spike_suggestion_block.py):
nine rows of name, country and population is 346 bytes even trimmed and
diffed — nearly three seconds at 1200 baud, where a reader types two characters
a second — and three rows of name and country is 121. Then measured again
through the real page and a real session in
[spike_search_page.py](../../../docs/spikes/spike_search_page.py): keying
TRONDHEIM cost 107 bytes for the first letter and **one byte** for seven of the
nine, because a keystroke that changes nothing but the cell under the cursor
sends that character and nothing else.

The form lives in the session rather than in the handler: it is one caller's
typing and lasts exactly as long as their line. It survives leaving the page
and coming back, which is what a reader who has just looked at one of three
candidates wants.

`*YORK#` still works too — a word the numbering does not know is offered to the
index, which is what `on_unresolved` is for — and reaches the same page as
keying it into the field.

### 4, finding a point by position

Two fields, latitude and longitude, in degrees to one decimal place. The
interaction is what a viewdata keypad leaves room for and that is less than it
looks:

| | |
|---|---|
| digits, `.`, `+`, `-`, `N S E W` | type into the live field |
| TAB, and the forward arrows | the next field, coming round to the first |
| the back arrows | the field before |
| RETURN | finishes a field; finishes the form from the last |
| DELETE | rubs out |
| `*1#` | the menu — see below |

**Nothing advances by itself.** A field that jumped when it thought it had
enough would put the caret where the reader did not, and with two ways of
writing a coordinate — one ending in a letter and one not — it could not be
consistent about when.

**Both spellings are taken and one is advertised.** `54.0S` and `-54.0` both
work; the advice under each field shows only the hemispheric form. A field's
advice sits under it on every frame, so it is read far more often than it is
needed: showing one way teaches the reader who does not know, and taking both
serves the reader who does. The signs are therefore *undocumented rather than
unsupported*, which is said where somebody might later tidy the parser to match
the hint.

**`0` is not the way out here**, which no other page in this workspace can say.
Digits are data, so a `0` that went to the menu would be a key that ate a
coordinate. The footer says `*1#`, which is what a frame naming only the keys
that work amounts to when the convention cannot be kept.

Beneath the fields it says how far the nearest known place is — `2km from
Skelton` — rather than calling it near. `Index.nearest` bounds its search at a
degree, which is 111km, and a service that said "near Trowbridge" about
somewhere ninety kilometres off would be lying politely. Nowhere within a degree
says that too, rather than leaving a reader wondering whether the keying took.

### What the reader is shown, and what it cost

The live field is a bar of white on blue — the command line's own colours, so a
reader learns "this is where typing goes" once. It is exactly as wide as what
fits in it, six cells being the longest a coordinate gets either way it is
written.

It also begins two cells before anything can be keyed into it, and no
arrangement avoids that: `NEW_BACKGROUND` takes the current foreground as the
background, so the order is forced and two of the three cells are already inside
the new colour. Written up in
[viewdata-encoding.md](../../sextile/docs/viewdata-encoding.md).

What RETURN does is marked beside the field where it does it — `# forecast`
against the longitude — and only while there is somewhere to send the reader.
The same rule as the suggestion list: a page that offered to go somewhere and
then did nothing would be worse than one that offered nothing, because on a slow
line a reader cannot tell a dead key from a slow one.
