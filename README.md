# weather-viewdata

The weather, served as Viewdata frames. Forecasts from
[yr.no](https://developer.yr.no), places from a local
[GeoNames](https://www.geonames.org/) index.

The third Sextile application, and the one that asks the framework for something
it has not got: **a page a reader types into**, with the best three matching
places beneath the field, each on a digit.

## Why a local place index

A type-ahead search cannot make a network request per keystroke — not at 1200
baud, and not against somebody else's rate limit. GeoNames publishes its
database under CC BY, so the index is ours: an indexed `LIKE 'trond%'` against a
local table, ranked for a weather service rather than for a map.

## What a reader can key

A viewdata keypad has twenty-six letters and ten digits, and on a search frame
the digits select from the suggestions. So the index is folded to letters alone:
`TROMSO` finds Tromsø, `MUNCHEN` finds München, `NEWYORK` finds New York. The
fold applies to the key and never to the data — the screen still says Tromsø.

## Attribution

Place data from [GeoNames](https://www.geonames.org/), CC BY 4.0.
Forecasts from the [Norwegian Meteorological Institute](https://www.met.no/),
CC BY 4.0. Neither endorses this service.

MIT licensed.
