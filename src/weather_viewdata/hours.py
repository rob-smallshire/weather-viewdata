"""The next hours, side by side, in figures and in charts.

The forecast read across instead of down. A table of hours is exact and has to
be read a row at a time; a strip of them is a shape, and a reader takes in
"cold and wet till six, clearing after" without reading anything at all.

**Eight hours to a band, and the arithmetic is forced rather than chosen.** An
hour column is four cells -- for a picture, an attribute and three cells of it
-- and a row of forty holds ten. Ten leaves nothing for saying which row is the
temperature and which the wind, and unlabelled rows of figures on a page a
reader sees once is a page that has to be explained; so four cells go to a
label column, which leaves nine. Nine fills the row to the last cell, where
eight leaves two at each end and lines the strip up with the rules above and
below it. Eight.

```
  ····································
  CEST 19  20  21  22  23  00  01  02
        ▨   ▨   ▨   ▨   ▨   ▨   ▨   ▨     the pictures
     C 13  14  15  16  17  18  19  20
    19 ▁▁▂▂▃▃▄▄▅▅▆▆▇▇██████████████████   warmer, in red
       ▁▁▂▂▃▃▄▄▅▅▆▆▇▇██████████████████   colder, in cyan
    12 ▁▁▂▂▃▃▄▄▅▅▆▆▇▇██████████████████
    mm ▄▄▄▄        ▂▂▂▂████████
   m/s  2   2   2   2   1   1   1   1
     5 ▁▁▂▂▃▃▄▄▅▅▆▆▇▇██████████████████   the wind, in magenta
       ▁▁▂▂▃▃▄▄▅▅▆▆▇▇██████████████████
   dir  S   S  SW  SW   W   W  NW  NW
```

**A chart takes all four cells of an hour, where a picture takes three.** The
figures and the pictures each need an attribute at the head of their column;
a chart needs one for the whole row, since a row of a chart is one colour
throughout. So a chart is eight blocks to the hour, and the attribute it would
otherwise have spent comes out of the label column -- which is why a chart's
label is three characters where `CEST` is four.

**The temperature scale puts freezing on a row boundary.** One colour to a row
is the rule the whole page is built on, so a chart wanting warm in red and cold
in cyan has to put nought degrees where one row ends and the next begins: a
third of the way up, or two thirds. That choice then fixes the rest of the
scale rather than the data fixing it, and the one that wastes less of the
height wins. A series that stays one side of freezing needs no boundary and is
drawn in a single colour over all three rows.

**Rain is not scaled at all.** Its four levels are millimetres in the hour and
mean the same on every page, which a scaled bar could not: on a dry afternoon a
scaled chart draws a drizzle full height, and the reader who wanted to know
whether to take a coat has been told the wrong thing loudly.

Local time only. met.no's own pages show one clock here and it is the right
one: a strip is for glancing at, and two clocks in three cells is neither. The
label says *which* clock -- `CEST`, the zone's own abbreviation -- and the
hours are drawn in the cyan that has meant local since the first forecast page.

A light rule above, and none below: the chrome's own rule closes the frame a
row later, and two lines together read as a border rather than as a division.
The rule that is there is light because the chrome's is a bar, and a bar
belongs where a page ends -- between two things that are both content it reads
as a second frame beginning.
"""

from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

from sextile.viewdata.blocks import BLOCKS_ACROSS, BLOCKS_DOWN, block_runs
from sextile.viewdata.canvas import Canvas
from sextile.viewdata.charset import mosaic_code
from sextile.viewdata.charting import bars, curve
from sextile.viewdata.controls import Colour, alpha_colour, graphics_colour
from sextile.viewdata.drawing import thin_rule
from sextile.viewdata.encoding import fitted
from weather_viewdata.forecast.model import Moment
from weather_viewdata.icons import BANDS, CELLS_ACROSS, COLUMN_CELLS, draw, icon_for
from weather_viewdata.wind import from_the

#: Hours across a band. See above: eight is what is left after a label column
#: and a margin that agrees with the rules.
HOURS_ACROSS: Final = 8

#: Characters the label column holds, and where its attribute goes -- in the
#: left margin, which was going to be a blank cell whatever happened. That is
#: what buys the fourth character, and the fourth character is what lets the
#: label be `CEST` rather than something abbreviated twice.
LABEL_CELLS: Final = 4
_ATTRIBUTE_AT: Final = 1
_FIRST_COLUMN: Final = _ATTRIBUTE_AT + 1 + LABEL_CELLS

#: A chart is one colour to the row, so it spends one attribute where a row of
#: pictures spends eight -- and it takes that one out of the label column,
#: which is why a chart's label is three characters and a figure row's is four.
_CHART_CELLS: Final = HOURS_ACROSS * COLUMN_CELLS
_CHART_LABEL_CELLS: Final = LABEL_CELLS - 1
_CHART_ATTRIBUTE_AT: Final = _FIRST_COLUMN - 1
_CHART_ACROSS: Final = _CHART_CELLS * BLOCKS_ACROSS

#: The rows of a band, in the order they are drawn, and what they add up to.
_HOURS_ROW: Final = 0
_PICTURE_ROW: Final = 1
_DEGREES_ROW: Final = _PICTURE_ROW + BANDS
_WARMTH_ROW: Final = _DEGREES_ROW + 1
_WARMTH_ROWS: Final = 3
_RAIN_ROW: Final = _WARMTH_ROW + _WARMTH_ROWS
_SPEED_ROW: Final = _RAIN_ROW + 1
_GUST_ROW: Final = _SPEED_ROW + 1
_GUST_ROWS: Final = 2
_QUARTER_ROW: Final = _GUST_ROW + _GUST_ROWS
BAND_ROWS: Final = _QUARTER_ROW + 1

#: Rows the strip takes, its rule included, and hours it shows. One rule and
#: not two: the strip fills the frame, so a rule under the last row of it would
#: sit against the chrome's own and read as a double line.
_RULES: Final = 1
STRIP_ROWS: Final = BAND_ROWS + _RULES
HOURS_SHOWN: Final = HOURS_ACROSS

#: What each row of figures is. The hour row is labelled with the zone's own
#: name instead, which says both what the row is and which clock it keeps.
_DEGREES: Final = "C"
_SPEED: Final = "m/s"
_RAIN: Final = "mm"
_QUARTER: Final = "dir"

_HOUR_COLOUR: Final = Colour.CYAN
_FIGURE_COLOUR: Final = Colour.WHITE
_WARM_COLOUR: Final = Colour.RED
_COLD_COLOUR: Final = Colour.CYAN
_RAIN_COLOUR: Final = Colour.BLUE
_GUST_COLOUR: Final = Colour.MAGENTA

#: Where freezing may sit: at one of the two row boundaries, as a fraction of
#: the height. Nowhere else will do, because a row is one colour.
_FREEZING_AT: Final = (1 / 3, 2 / 3)

#: Millimetres in the hour that fill one, two and three blocks. Fixed, so the
#: same bar means the same rain on every page.
_RAIN_LEVELS: Final = (0.1, 1.0, 4.0)

#: The narrowest a temperature chart may be, in degrees. A day that never moves
#: would otherwise be drawn as a line on the floor, which reads as cold rather
#: than as steady.
_LEAST_SPREAD: Final = 2.0


def draw_strip(
    canvas: Canvas,
    row: int,
    moments: list[Moment],
    zone: ZoneInfo | None,
    clock: str,
) -> None:
    """The next hours: eight across, under a light rule."""
    thin_rule(canvas, row)
    _draw_band(canvas, row + 1, moments[:HOURS_ACROSS], zone, clock)


def _draw_band(
    canvas: Canvas,
    row: int,
    moments: list[Moment],
    zone: ZoneInfo | None,
    clock: str,
) -> None:
    _draw_figures(canvas, row, moments, zone, clock)
    _draw_warmth(canvas, row + _WARMTH_ROW, moments)
    _draw_rain(canvas, row + _RAIN_ROW, moments)
    _draw_wind(canvas, row + _GUST_ROW, moments)


def _draw_figures(
    canvas: Canvas,
    row: int,
    moments: list[Moment],
    zone: ZoneInfo | None,
    clock: str,
) -> None:
    """The rows that are read, and the pictures between them."""
    _label(canvas, row + _HOURS_ROW, clock, _HOUR_COLOUR)
    for at, text in ((_DEGREES_ROW, _DEGREES), (_SPEED_ROW, _SPEED), (_QUARTER_ROW, _QUARTER)):
        _label(canvas, row + at, text, _FIGURE_COLOUR)
    #  The rain row is a chart, so its label gives up a cell to the attribute
    #  that enters graphics, as the other charts' labels do.
    _label(canvas, row + _RAIN_ROW, _RAIN, _FIGURE_COLOUR, cells=_CHART_LABEL_CELLS)
    for slot, moment in enumerate(moments):
        column = _FIRST_COLUMN + slot * COLUMN_CELLS
        _figure(canvas, row + _HOURS_ROW, column, _hour(moment.at, zone))
        picture = icon_for(moment.symbol)
        if picture is not None:
            draw(canvas, row + _PICTURE_ROW, column, picture)
        _figure(canvas, row + _DEGREES_ROW, column, _whole(moment.temperature))
        _figure(canvas, row + _SPEED_ROW, column, _whole(moment.wind_speed))
        _figure(canvas, row + _QUARTER_ROW, column, from_the(moment.wind_from) or "-")


def _draw_warmth(canvas: Canvas, row: int, moments: list[Moment]) -> None:
    """The temperature, as a line over three rows, warm above cold."""
    readings = [moment.temperature for moment in moments]
    known = [reading for reading in readings if reading is not None]
    if not known:
        return
    low, high, freezing = warmth_scale(min(known), max(known))
    _draw_chart(
        canvas,
        row,
        curve(
            [_between(low, high, reading) for reading in readings],
            across=_CHART_ACROSS,
            down=_WARMTH_ROWS * BLOCKS_DOWN,
        ),
        [_WARM_COLOUR if band < freezing else _COLD_COLOUR for band in range(3)],
    )
    _label(canvas, row, _whole(high), _FIGURE_COLOUR, cells=_CHART_LABEL_CELLS)
    _label(
        canvas,
        row + _WARMTH_ROWS - 1,
        _whole(low),
        _FIGURE_COLOUR,
        cells=_CHART_LABEL_CELLS,
    )


def warmth_scale(coldest: float, warmest: float) -> tuple[float, float, int]:
    """The bottom and top of the temperature chart, and where freezing sits.

    Freezing is given as the number of rows above it, counting from the top: 3
    where the whole series is above freezing and every row is warm, 0 where the
    whole series is below it and every row is cold, and 1 or 2 where it is
    crossed.

    Where it is crossed, putting freezing at a third or two thirds of the
    height fixes the rest of the scale: at a third the top of the chart is
    twice what the bottom is, and at two thirds it is half. Both are worked out
    and the one that leaves less waste wins, ties going to the lower boundary.
    """
    if coldest >= 0:
        return _spread(coldest, warmest) + (3,)
    if warmest <= 0:
        return _spread(coldest, warmest) + (0,)
    tried = []
    for fraction in _FREEZING_AT:
        #  Freezing a third of the way up leaves the bottom row cold and the
        #  two above it warm; two thirds of the way up, the other way about.
        warm_rows = round(_WARMTH_ROWS * (1 - fraction))
        below = fraction / (1 - fraction)
        high = max(warmest, -coldest / below)
        tried.append((high + high * below, -high * below, high, warm_rows))
    #  On a tie the lower boundary wins, which is the first listed: a series
    #  as far below freezing as above fits either way, and giving the warm
    #  colour the spare row is as good a rule as any and better than none.
    _, low, high, warm_rows = min(tried, key=lambda option: option[0])
    return low, high, warm_rows


def _spread(coldest: float, warmest: float) -> tuple[float, float]:
    """A range with a little air in it, so a flat series is not a flat line."""
    if warmest - coldest >= _LEAST_SPREAD:
        return coldest, warmest
    middle = (coldest + warmest) / 2
    return middle - _LEAST_SPREAD / 2, middle + _LEAST_SPREAD / 2


def _draw_rain(canvas: Canvas, row: int, moments: list[Moment]) -> None:
    """Rain as four levels, and the levels are millimetres and not fractions.

    Scaled to the series, a chart of one wet hour among seven dry ones draws
    that hour full height whether it held a drizzle or a downpour. Fixed, the
    same bar is the same rain on every page a reader ever fetches.
    """
    levels = [rain_level(moment.precipitation) for moment in moments]
    if not any(levels):
        return
    _draw_chart(
        canvas,
        row,
        bars(
            [None if level is None else level / BLOCKS_DOWN for level in levels],
            across=_CHART_ACROSS,
            down=BLOCKS_DOWN,
        ),
        [_RAIN_COLOUR],
    )


def rain_level(millimetres: float | None) -> int | None:
    """Which of the four levels a reading falls in."""
    if millimetres is None:
        return None
    return sum(1 for level in _RAIN_LEVELS if millimetres >= level)


def _draw_wind(canvas: Canvas, row: int, moments: list[Moment]) -> None:
    """The wind, as a line over two rows, from a standstill to the strongest.

    **The bottom is nought and the top is whatever the strongest hour is**, and
    the top is written beside it. The temperature chart needs a floor under how
    narrow it may be, because a flat line halfway up a chart of unsaid limits
    means nothing; wind needs none, because the bottom of the chart is a real
    place -- no wind -- and the one number that has to be said is the top. A
    breeze drawn full height under a label reading 2 is a breeze, and a reader
    who looks at the label knows it.
    """
    readings = [moment.wind_speed for moment in moments]
    known = [reading for reading in readings if reading is not None]
    if not known:
        return
    high = max(known)
    #  A dead calm all through has no top to scale to, and every reading is on
    #  the floor of the chart, which is where a dead calm belongs.
    fractions = [
        None if reading is None else (reading / high if high > 0 else 0.0)
        for reading in readings
    ]
    _draw_chart(
        canvas,
        row,
        curve(fractions, across=_CHART_ACROSS, down=_GUST_ROWS * BLOCKS_DOWN),
        [_GUST_COLOUR],
    )
    _label(canvas, row, _whole(high), _FIGURE_COLOUR, cells=_CHART_LABEL_CELLS)


def _draw_chart(
    canvas: Canvas, row: int, bitmap: list[list[bool]], colours: list[Colour]
) -> None:
    """Put a bitmap on the frame, one attribute and one colour to a row."""
    for offset, patterns in enumerate(block_runs(bitmap)):
        colour = colours[offset] if offset < len(colours) else colours[-1]
        canvas.frame.set_attribute(
            row + offset, _CHART_ATTRIBUTE_AT, graphics_colour(colour)
        )
        for cell, pattern in enumerate(patterns[:_CHART_CELLS]):
            canvas.frame.set_cell(
                row + offset, _FIRST_COLUMN + cell, mosaic_code(pattern)
            )


def _between(low: float, high: float, value: float | None) -> float | None:
    """Where a reading falls between the bottom and the top of a chart."""
    if value is None or high <= low:
        return None
    return (value - low) / (high - low)


def _label(
    canvas: Canvas,
    row: int,
    text: str,
    colour: Colour,
    *,
    cells: int = LABEL_CELLS,
) -> None:
    """The label column, and the one attribute a row of figures needs.

    Set once at the left margin and good for everything after it, since the
    label and the figures beside it are the same colour. A chart's label is a
    character shorter, the cell going on the attribute that enters graphics;
    the picture row is not labelled at all, a column of pictures saying what it
    is without help.
    """
    canvas.frame.set_attribute(row, _ATTRIBUTE_AT, alpha_colour(colour))
    canvas.frame.write(row, _ATTRIBUTE_AT + 1, f"{fitted(text, cells):>{cells}}")


def _figure(canvas: Canvas, row: int, column: int, text: str) -> None:
    """One value, centred over the picture above or below it."""
    canvas.frame.write(row, column + 1, f"{text:^{CELLS_ACROSS}}")


def _hour(at: datetime, zone: ZoneInfo | None) -> str:
    """The hour, in the place's own clock where we know it."""
    return f"{at.astimezone(zone):%H}" if zone is not None else f"{at:%H}"


def _whole(value: float | None) -> str:
    """A reading rounded to nothing after the point, or a dash for none of one.

    Three cells will not hold a decimal, and a strip is not the place for one:
    the table underneath keeps the tenths, and nobody glancing at a shape wants
    to know the wind to a tenth of a metre.

    A dash rather than a nought, as everywhere else. Nought degrees is weather
    and no reading is not.
    """
    return "-" if value is None else f"{value:.0f}"
