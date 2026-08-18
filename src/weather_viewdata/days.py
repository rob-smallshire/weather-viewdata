"""The days ahead, four periods to a row.

What the hour strip cannot do: ten days will not fit across a frame, and
nobody wants them hour by hour anyway. So each day is a row of four pictures --
night, morning, afternoon, evening -- with the day's figures beside them.

```
       ngt mrn aft eve    hi/lo  mm m/s
Today   ▨   ▨   ▨   ▨
 9 Aug  ▨   ▨   ▨   ▨     18/12   2   4
        ▨   ▨   ▨   ▨

Sun     ▨   ▨   ▨   ▨
10 Aug  ▨   ▨   ▨   ▨     16/11   0   7
        ▨   ▨   ▨   ▨
```

The periods are the reader's, not met.no's. Six hours each from local
midnight, which is what `night` and `afternoon` mean to somebody looking out of
a window. met.no's own six-hourly summaries are on the clock at Greenwich --
00, 06, 12 and 18 UTC -- so they line up with these only where a zone is on it,
and everywhere else they straddle two.

A moment goes in the period its middle falls in, which is the rule that
survives the straddling. Karachi is five hours ahead: met.no's 06:00 UTC block
is 11:00 to 17:00 there, one hour of morning and five of afternoon, and putting
it where it *starts* would call an afternoon a morning. Denver is seven behind
and the same block is 23:00 to 05:00, which by its start is an evening and is
really a night. By the middle, both come out right.

It stays one moment to a period whatever the zone, since the blocks are six
hours apart and the periods six hours wide -- and at the near end of a forecast,
where the series is hourly, a period simply holds six of them.

One symbol has to stand for six hours, and there are two ways to pick it.
Where the period holds a moment covering the whole of it, that moment's symbol
is met.no's own summary of those six hours and is better than anything we could
work out. Where it holds six hourly ones instead, the worst of them wins: a
reader asking what the afternoon will be like is asking whether they will get
wet, and an average of six hours would answer a question nobody asked.

The figures are the day's, not the period's. Four sets of three would want
a frame to themselves, and what is left of the row after sixteen cells of
pictures is fifteen. High and low, the rain in the day, and the strongest wind.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from sextile.viewdata.canvas import Canvas
from sextile.viewdata.controls import Colour, alpha_colour

from weather_viewdata.forecast.model import Moment
from weather_viewdata.icons import COLUMN_CELLS, draw, icon_for
from weather_viewdata.symbols import severity

#: Six hours each, from local midnight, and what they are called over the
#: pictures. Three letters because a picture is three cells wide.
PERIODS: Final = ("ngt", "mrn", "aft", "eve")
PERIOD_HOURS: Final = 24 // len(PERIODS)

_AN_HOUR: Final = timedelta(hours=1)

#: Cells the day's name takes, and the attribute that colours it. Six for the
#: name -- `10 Aug` and `Today` are the two things it ever says, and both are
#: five or six -- and the attribute before them, which cannot go in a margin
#: here because there is no margin to spare.
NAME_CELLS: Final = 6
_NAME_AT: Final = 1

#: Where the pictures begin, and where the figures begin after them. The row
#: comes to thirty-nine of the forty: a name, sixteen cells of picture, the
#: attribute that gets back out of graphics, and fifteen of figures.
_FIRST_PICTURE: Final = _NAME_AT + NAME_CELLS
_FIGURES_AT: Final = _FIRST_PICTURE + len(PERIODS) * COLUMN_CELLS

#: What the figures take: an attribute to get back out of graphics, then the
#: temperatures, the rain and the wind.
_ATTRIBUTE_CELL: Final = 1
_WARMTH_CELLS: Final = 7
_RAIN_CELLS: Final = 3
_WIND_CELLS: Final = 3

#: Rows a day takes. A blank between two of them, which the sequence part's
#: `gap` puts there rather than the day carrying it: charged to every
#: day it would be wasted at the foot of the frame, and it is worth a fifth day.
PICTURE_ROWS: Final = 3

#: Which row of the three carries what. The name is on the first two -- what
#: the day is called, then its date -- and the figures on the second, level
#: with the middle of the pictures.
_NAME_ROW: Final = 0
_DATE_ROW: Final = 1
_FIGURES_ROW: Final = 1

_NAME_COLOUR: Final = Colour.CYAN
_FIGURE_COLOUR: Final = Colour.WHITE

#: The heading, spaced to the columns beneath it. One cell narrower than the
#: row, since the colour attribute takes the first.
_FIGURE_HEADINGS: Final = (
    f"{'hi/lo':>{_WARMTH_CELLS}} {'mm':>{_RAIN_CELLS}} {'m/s':>{_WIND_CELLS}}"
)

#: One cell narrower than the row, since the heading's own colour attribute
#: takes the first: everything below is written a cell to the right of where
#: this says it.
HEADINGS: Final = (
    " " * (_FIRST_PICTURE - 1 + 1)
    + " ".join(PERIODS)
    + " " * (_FIGURES_AT - _FIRST_PICTURE - len(" ".join(PERIODS)))
    + _FIGURE_HEADINGS
)


@dataclass(frozen=True)
class Day:
    """One day of a forecast, as a page shows it."""

    on: date
    periods: tuple[str | None, ...]
    """A symbol for each of `PERIODS`, or None where the forecast has not got
    that far -- today begins part-way through, and the last day ends so."""

    warmest: float | None = None
    coldest: float | None = None
    rain: float | None = None
    wind: float | None = None


def days_of(
    moments: Sequence[Moment], zone: ZoneInfo | None, *, from_day: date | None = None
) -> list[Day]:
    """A forecast gathered into days and periods, in the place's own clock.

    Nothing before `from_day`, so a forecast held over the turn of a day shows
    today first rather than opening on an afternoon that is over. What is left
    of today is still today: the first row of the table is the day the reader
    is in, however little of it remains.
    """
    gathered: dict[date, list[tuple[int, Moment]]] = {}
    for moment in moments:
        middle = _middle(moment)
        local = middle.astimezone(zone) if zone is not None else middle
        gathered.setdefault(local.date(), []).append(
            (local.hour // PERIOD_HOURS, moment)
        )
    return [
        _day(on, held)
        for on, held in sorted(gathered.items())
        if from_day is None or on >= from_day
    ]


def _middle(moment: Moment) -> datetime:
    """Halfway through what a moment covers.

    Which day and which period a reading belongs to, where the reading is a
    six-hour block that straddles two of them. The last moment of a forecast
    covers nothing -- there is no next moment inside it -- and is taken as an
    hour, which is what the rest of the near series is.
    """
    return moment.at + (moment.covers or _AN_HOUR) / 2


def _day(on: date, held: list[tuple[int, Moment]]) -> Day:
    temperatures = [
        moment.temperature for _, moment in held if moment.temperature is not None
    ]
    rain = [moment.precipitation for _, moment in held if moment.precipitation is not None]
    wind = [moment.wind_speed for _, moment in held if moment.wind_speed is not None]
    return Day(
        on=on,
        periods=tuple(
            _symbol([moment for at, moment in held if at == period])
            for period in range(len(PERIODS))
        ),
        warmest=max(temperatures) if temperatures else None,
        coldest=min(temperatures) if temperatures else None,
        rain=sum(rain) if rain else None,
        wind=max(wind) if wind else None,
    )


def _symbol(moments: Sequence[Moment]) -> str | None:
    """The one symbol that stands for a period.

    The longest reading first, because a moment covering the whole six hours
    carries met.no's own summary of them; then the worst, for a period made of
    hourly readings where there is no such thing.
    """
    if not moments:
        return None
    best = max(
        moments,
        key=lambda moment: (moment.covers or timedelta(), severity(moment.symbol)),
    )
    return best.symbol


def draw_day(canvas: Canvas, row: int, day: Day, today: date) -> None:
    """One day: its name, four pictures, and the day's figures."""
    _name(canvas, row + _NAME_ROW, "Today" if day.on == today else f"{day.on:%a}")
    _name(canvas, row + _DATE_ROW, f"{day.on.day} {day.on:%b}")
    for period, symbol in enumerate(day.periods):
        picture = icon_for(symbol)
        if picture is not None:
            draw(canvas, row, _FIRST_PICTURE + period * COLUMN_CELLS, picture)
    canvas.frame.set_attribute(
        row + _FIGURES_ROW, _FIGURES_AT, alpha_colour(_FIGURE_COLOUR)
    )
    canvas.frame.write(row + _FIGURES_ROW, _FIGURES_AT + _ATTRIBUTE_CELL, _figures(day))


def _figures(day: Day) -> str:
    """High and low, the rain, and the strongest wind, spaced to the heading."""
    warmth = f"{_whole(day.warmest)}/{_whole(day.coldest)}"
    return (
        f"{warmth:>{_WARMTH_CELLS}} "
        f"{_whole(day.rain):>{_RAIN_CELLS}} "
        f"{_whole(day.wind):>{_WIND_CELLS}}"
    )


def _name(canvas: Canvas, row: int, text: str) -> None:
    canvas.frame.set_attribute(row, _NAME_AT - 1, alpha_colour(_NAME_COLOUR))
    canvas.frame.write(row, _NAME_AT, f"{text:>{NAME_CELLS}}")


def _whole(value: float | None) -> str:
    """A reading with nothing after the point, or a dash for none of one."""
    return "-" if value is None else f"{value:.0f}"
