# weather-viewdata

The weather, served as Viewdata frames. Forecasts from the Norwegian
Meteorological Institute; places from a local
[GeoNames](https://www.geonames.org/) index.

```sh
uv run weather-viewdata import-places            # 235,176 places, 11 seconds
uv run weather-viewdata render --page 3213133880  # Trondheim, without a Beeb
uv run weather-viewdata serve                    # answer calls on port 6850
nc localhost 6850                                # and call it
```

```
0                  the title frame
1                  the main menu
3                  find a place by name        321<geoname-id>  its forecast
4                  find a point by position    421<lat><lon>    its forecast
9  about   90 goodbye   91 help   92/93/94 the framework's pages
                       95 what the pictures mean
```


## Why a local place index

A type-ahead search cannot make a network request per keystroke — not at 1200
baud, and not against somebody else's rate limit. GeoNames publishes its
database under CC BY, so the index is ours: a range scan against a local table,
ranked for a weather service rather than for a map. A keystroke costs 0.08ms.

## What a reader can key

A viewdata keypad has twenty-six letters and ten digits, and on a search frame
the digits select from the suggestions. So the index is folded to letters alone:
keying `TROMSO` on `*3#` finds Tromsø, `MUNCHEN` finds München, `NEWYORK` finds
New York. The fold applies to the key and never to the data — the screen still
says Tromsø.

A word between the star and the hash is a *page*, never a place: `*HISTORY#`
and `*SEARCH#` go where they say, and there is no guessing which of the dozens
of Yorks somebody meant.

## Two ways to name a forecast

They fail differently, which is why there are two. A named place carries a name,
a timezone and an altitude, and depends on GeoNames still holding that record. A
point carries none of those and depends on nothing at all: 63.4N 10.4E will mean
the same thing for as long as there is an earth.

## The third Sextile application

It exists to hold the framework to its claim, and it is the first application to
have found anything: five framework defects in a day, all of them registration
order showing through. [docs/design.md](docs/design.md) is the design as built,
and says what each was.

## Attribution

Place data from [GeoNames](https://www.geonames.org/), CC BY 4.0.
Forecasts from the [Norwegian Meteorological Institute](https://www.met.no/),
CC BY 4.0. Neither endorses this service.

MIT licensed.
