"""The next hours, side by side.

The forecast read across instead of down. A table of hours is exact and has to
be read a row at a time; a strip of them is a shape, and a reader takes in
"clear this afternoon, rain by six" without reading anything at all. Both are
worth having, which is why the table is still there underneath.

**Eight hours to a band, and the arithmetic is forced rather than chosen.** An
hour column is four cells -- an attribute and three cells of picture -- and a
row of forty holds ten of them. Ten leaves nothing for saying which row is the
temperature and which the wind, and two unlabelled rows of figures on a page a
reader sees once is a page that has to be explained. So four cells go to a
label column, which leaves nine; and nine fills the row to the last cell, where
eight leaves two cells at each end and lines the strip up with the rules above
and below it. Eight.

**One band, and so eight hours.** A band is six rows -- the hour, three of
picture, the temperature, the wind -- and the frame has thirteen left once the
position, the clocks, the issue time and the weather now have had their seven.
Two bands and a blank between them would fill every one of the thirteen, take
the table off the first frame entirely, and buy eight more hours; eight hours
is enough to see the afternoon out, and the table is what the rest of the day
is for.

Local time only. met.no's own pages show one clock here and it is the right
one: a strip is for glancing at, and two clocks in three cells is neither. The
label says *which* clock -- `CEST`, the zone's own abbreviation -- and the hours
are drawn in the cyan that has meant local since the first forecast page.

The label column gets four characters rather than three by putting its
attribute in the left margin, where a blank cell was going to be anyway. Which
is exactly enough for the abbreviations: `CEST`, `AEDT`, `NZDT`.

A light rule top and bottom. The chrome's rule is a bar and belongs where the
page ends; between two things that are both content a bar reads as a second
frame beginning, so this is the same construction with a sixth of the ink.
"""

from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

from sextile.viewdata.canvas import Canvas
from sextile.viewdata.controls import Colour, alpha_colour
from sextile.viewdata.drawing import thin_rule
from sextile.viewdata.encoding import fitted
from weather_viewdata.forecast.model import Moment
from weather_viewdata.icons import BANDS, CELLS_ACROSS, COLUMN_CELLS, draw, icon_for

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

#: The hour, the picture, the temperature, the wind.
BAND_ROWS: Final = 1 + BANDS + 2

#: Rows the strip takes, its two rules included, and hours it shows. One band:
#: see above for what a second would cost.
_RULES: Final = 2
STRIP_ROWS: Final = BAND_ROWS + _RULES
HOURS_SHOWN: Final = HOURS_ACROSS

#: What the two rows of figures are. The hour row is labelled with the zone's
#: own name instead, which says both what the row is and which clock it keeps.
_DEGREES: Final = "C"
_SPEED: Final = "m/s"

_HOUR_COLOUR: Final = Colour.CYAN
_FIGURE_COLOUR: Final = Colour.WHITE


def draw_strip(
    canvas: Canvas,
    row: int,
    moments: list[Moment],
    zone: ZoneInfo | None,
    clock: str,
) -> None:
    """The next hours: eight across, and a light rule above and below."""
    thin_rule(canvas, row)
    thin_rule(canvas, row + BAND_ROWS + 1)
    _draw_band(canvas, row + 1, moments, zone, clock)


def _draw_band(
    canvas: Canvas,
    row: int,
    moments: list[Moment],
    zone: ZoneInfo | None,
    clock: str,
) -> None:
    _label(canvas, row, clock, _HOUR_COLOUR)
    _label(canvas, row + BANDS + 1, _DEGREES, _FIGURE_COLOUR)
    _label(canvas, row + BANDS + 2, _SPEED, _FIGURE_COLOUR)
    for slot, moment in enumerate(moments[:HOURS_ACROSS]):
        column = _FIRST_COLUMN + slot * COLUMN_CELLS
        _figure(canvas, row, column, _hour(moment.at, zone))
        picture = icon_for(moment.symbol)
        if picture is not None:
            draw(canvas, row + 1, column, picture)
        _figure(canvas, row + BANDS + 1, column, _whole(moment.temperature))
        _figure(canvas, row + BANDS + 2, column, _whole(moment.wind_speed))


def _label(canvas: Canvas, row: int, text: str, colour: Colour) -> None:
    """The label column, and the one attribute the whole row needs.

    Set once at the left margin and good for everything after it, since the
    label and the figures beside it are the same colour. The picture rows carry
    their own attributes, one to a column, and are not labelled at all: a
    column of pictures says what it is.
    """
    canvas.frame.set_attribute(row, _ATTRIBUTE_AT, alpha_colour(colour))
    canvas.frame.write(row, _ATTRIBUTE_AT + 1, f"{fitted(text, LABEL_CELLS):>{LABEL_CELLS}}")


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
