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
3                  find a place by name        32<geoname-id>   its forecast
4                  find a point by position    42<lat><lon>     its forecast
9  about   90 goodbye   91 help   92/93/94 the framework's pages
```

Stardot's convention, and for its reasons: the first digit names a namespace and
the second says what kind of page within it. A namespace's root would be its
index, and here it cannot be — nobody lists 235,176 places on a screen — so the
root is the page that explains how to search it.

**Two ways to name a forecast, and they fail differently.** That is why both
exist rather than one being the poor relation:

| | carries | depends on |
|---|---|---|
| `32<geoname-id>` | a name, a timezone, an altitude | GeoNames still holding that record |
| `42<lat><lon>` | coordinates, and says so | nothing at all |

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

That resolution decides what the page can honestly *be*. Measured against the
real index, 67% of places share a cell with another and one cell in Hong Kong
holds 182 of them — so a coordinate page cannot name a town and does not
pretend to. It is the weather *about here*, and it borrows a clock from the
nearest known place because timezone borders follow habitation.

Longitude wraps and latitude does not: 190°E is 170°W spelled unusually and is
taken quietly, where 91°N is a mistake and is refused. The date line gets one
page number rather than two.

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

`ForecastTable` is a fourth `Template` shape: a run of hours, one to a row, two
clocks and a temperature and a wind and a word. Nothing on it is selectable — a
forecast is something to read, not a menu — so no digit is spent on the rows.

**Times in UTC and in the place's own zone.** `zoneinfo` reads the system
database and GeoNames gives the IANA name per place, so daylight saving is
handled and named: `Times UTC and CEST (UTC+2)`. Not every zone has letters —
Fiji reports `+12` — so the abbreviation is only shown where it is one.

**A missing reading is a dash and never a nought.** Nought degrees is weather
and no reading is not, and on a weather page that is not a distinction to lose.
Tromsø has no elevation at all in `cities500`, which is the case that made this
concrete rather than theoretical.

The weather column takes whatever the row has left, counted from the row rather
than worked out by hand — an attribute costs a cell, and hand-arithmetic about
that was wrong the first time. The longest symbol met.no has,
`heavy sleet shwrs+thunder`, does not fit and is shortened.

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
