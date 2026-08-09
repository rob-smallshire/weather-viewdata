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
one: a strip is for glancing at, and two clocks in three cells is neither.
The row above says which clock it is, and the hours are drawn in the cyan that
has meant "local" since the first forecast page.
"""

from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

from sextile.viewdata.canvas import Canvas
from sextile.viewdata.controls import Colour, alpha_colour
from sextile.viewdata.frame import COLUMNS
from weather_viewdata.forecast.model import Moment
from weather_viewdata.icons import BANDS, CELLS_ACROSS, COLUMN_CELLS, draw, icon_for

#: Hours across a band, and what the rest of the row is spent on. See above:
#: eight is what is left after a label column and a margin that agrees with the
#: rules.
HOURS_ACROSS: Final = 8
LABEL_CELLS: Final = COLUMN_CELLS

_USED: Final = LABEL_CELLS + HOURS_ACROSS * COLUMN_CELLS
_MARGIN: Final = (COLUMNS - _USED) // 2

#: The hour, the picture, the temperature, the wind.
BAND_ROWS: Final = 1 + BANDS + 2

#: Rows the strip takes, and hours it shows. One band: see above for what a
#: second would cost.
STRIP_ROWS: Final = BAND_ROWS
HOURS_SHOWN: Final = HOURS_ACROSS

#: What the rows are, said in the three cells the label column has for it.
#: Short because that is all there is, and worth the four cells because two
#: unlabelled rows of figures are two rows nobody can read.
_LABELS: Final = ("loc", "C", "m/s")

_HOUR_COLOUR: Final = Colour.CYAN
_FIGURE_COLOUR: Final = Colour.WHITE


def draw_strip(
    canvas: Canvas, row: int, moments: list[Moment], zone: ZoneInfo | None
) -> None:
    """The next hours: eight across, six rows down."""
    _label(canvas, row, _LABELS[0], _HOUR_COLOUR)
    _label(canvas, row + BANDS + 1, _LABELS[1], _FIGURE_COLOUR)
    _label(canvas, row + BANDS + 2, _LABELS[2], _FIGURE_COLOUR)
    for slot, moment in enumerate(moments[:HOURS_ACROSS]):
        column = _MARGIN + LABEL_CELLS + slot * COLUMN_CELLS
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
    canvas.frame.set_attribute(row, _MARGIN, alpha_colour(colour))
    canvas.frame.write(row, _MARGIN + 1, f"{text:>{LABEL_CELLS - 1}}")


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
