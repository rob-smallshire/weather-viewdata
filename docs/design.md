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

**The fold is to A–Z and nothing else.** The terminal decides the alphabet
twice over: Sextile's parser admits only alphanumerics, and on a search frame
the digits are spoken for by the suggestions. So `TROMSO` finds Tromsø,
`NEWYORK` finds New York, `MUNICH` finds München — and a digit is dropped from
the *key* rather than the place being dropped from the index, so `Quận 1` is
still findable by keying `QUAN`. What is folded is never the data: the screen
still says Tromsø.

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

### What the dump does not tell you

The alternate-names column holds three different things and says which is which
nowhere: genuine names, IATA airport codes, and romanisations from other
scripts. Oslo's holds `Christiania`, `OSL` and `awslw`.

**Capitalisation separates them**, measured against the real `cities500` and
documented nowhere — so it is a rule of thumb, and `alternateNamesV2` carries a
proper language tag at a further 193M if it ever misleads. Before the rule,
`TRO` returned Taree in Australia, whose airport code it is, ahead of both
Tromsø and Trondheim.

And a fold that keeps a sixth of a name has destroyed it rather than folded it.
Madrid's column carries `Мaдрид` — Cyrillic with a Latin `a` typed into the
middle — which put Madrid under the key `A`, and `A` is the first thing anybody
types.

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

## Still to come

The **search page** is what all of this was clearing the way for: a field the
reader types into, with the best three places beneath it on the digits. Three
rather than nine because the wire says so — nine rows repainted per keystroke is
2.9 seconds at 1200 baud even trimmed and diffed, and three is 0.8. It needs a
form seam in the framework, and a Beebium spike
(`docs/spikes/spike_suggestion_block.py`) is written and not yet run.

Until then `*YORK#` works: a word the numbering does not know is offered to the
index, which is what `on_unresolved` is for.
