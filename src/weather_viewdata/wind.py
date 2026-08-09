"""Which way the wind is blowing, in the letters a forecast says it in.

**From, not towards.** A wind named south-westerly comes *from* the south-west,
which is the meteorological convention and the one met.no's `wind_from_direction`
follows. Saying it the other way round would be wrong rather than unusual, which
is why the function is named after the preposition.

Sixteen points rather than eight, and rather than the bearing in degrees. A
degree reading is three cells and tells a reader on a screen nothing they can
picture; `SSW` is three cells and tells them where to stand. Sixteen because
eight loses the distinction between a southerly and a south-westerly that anyone
watching a coast cares about, and the extra letter costs one cell at most.

There is no arrow: the G0 set has three of the four it would need, so a compass
drawn in characters would have to be drawn in mosaics, and a mosaic arrow costs
a cell for its colour attribute and reads worse than the letters at this size.
"""

from typing import Final

#: The sixteen points, from north and going clockwise.
_POINTS: Final = (
    "N", "NNE", "NE", "ENE",
    "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW",
    "W", "WNW", "NW", "NNW",
)

_DEGREES_PER_POINT: Final = 360 / len(_POINTS)


def from_the(degrees: float | None) -> str:
    """The point of the compass a wind on this bearing blows from.

    Nothing at all where there is no reading. A wind whose direction is unknown
    is not a north wind, and the row says less rather than something untrue.
    """
    if degrees is None:
        return ""
    return _POINTS[round(degrees / _DEGREES_PER_POINT) % len(_POINTS)]
