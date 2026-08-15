"""Drawing the legend: every symbol beside the words for it.

The shape of the page that says what the symbols mean. The handler that
serves it is in `pages`; the codes themselves are `symbols`' and the drawings
are `icons`'.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Final

from sextile.formatting import SequencePart
from sextile.viewdata.canvas import Canvas
from sextile.viewdata.controls import Colour
from sextile.viewdata.frame import COLUMNS
from sextile.viewdata.wrapping import wrap_within
from weather_viewdata.icons import BANDS, COLUMN_CELLS, icon_for
from weather_viewdata.icons import draw as draw_icon

#: The legend page's grid: two symbols to a row, each with its words beside it.
#: Half a row apiece, less the drawing and the attribute that colours the
#: words, and one more cell so the two halves do not touch.
_SYMBOLS_ACROSS: Final = 2
_SYMBOL_CELLS: Final = COLUMNS // _SYMBOLS_ACROSS
WORD_CELLS: Final = _SYMBOL_CELLS - COLUMN_CELLS - 2


@dataclass(frozen=True)
class Shown:
    """One entry of the legend: a symbol code, and what to call it here.

    The words are carried rather than worked out from the code, because the
    sky variants are on the page too and `in_words` drops the time of day --
    three entries all saying `clear` would be a legend that explained nothing.
    """

    code: str
    words: str


#: The sky variants, shown after the set rather than through it. They differ
#: from the day drawings in one piece and only for the 21 codes that have a sky
#: in them, so forty more drawings would say this four times over.
SKIES: Final = (
    ("clearsky_night", "clear sky at night"),
    ("clearsky_polartwilight", "clear sky in polar twilight"),
    ("rainshowers_night", "rain showers at night"),
    ("rainshowers_polartwilight", "rain showers in polar twilight"),
)


def in_pairs(shown: Sequence[Shown]) -> list[tuple[Shown, ...]]:
    """Two to a row, because a picture and its words are half a row wide."""
    return [
        tuple(shown[at : at + _SYMBOLS_ACROSS])
        for at in range(0, len(shown), _SYMBOLS_ACROSS)
    ]


@dataclass(frozen=True, kw_only=True)
class SymbolTable(SequencePart[tuple[Shown, ...]]):
    """Pictures with their words, two to a row and four rows to each.

    A `SequencePart` rather than a `RowSequencePart`, because a mosaic picture is
    placed by cell and is three rows tall: a row writer walks one row from
    left to right, which is the wrong shape for this and the right shape for
    everything else.
    """

    #  A blank row after each, or the bottom band of one picture and the top
    #  band of the next read as one picture: they are three rows apart, in the
    #  same colours, and nothing between them says where one ends. The strip on
    #  a forecast page has no such trouble, its symbols being side by side.
    rows_per_entry: ClassVar[int] = BANDS + 1
    numbered: ClassVar[bool] = False

    def draw_entry(
        self, canvas: Canvas, row: int, entry: tuple[Shown, ...]
    ) -> None:
        for slot, shown in enumerate(entry):
            column = slot * _SYMBOL_CELLS
            picture = icon_for(shown.code)
            if picture is not None:
                draw_icon(canvas, row, column, picture)
            #  The picture is three rows tall and the words get all three, so
            #  nothing here has to be abbreviated: `heavy sleet showers and
            #  thunder` is twenty-nine cells and three fourteens is forty-two.
            said = wrap_within(shown.words, cells=WORD_CELLS, rows=BANDS)
            #  Centred against the picture, so a name of one line sits level
            #  with the cloud rather than perched above it.
            at = row + (BANDS - len(said)) // 2
            for offset, line in enumerate(said):
                #  Beside the picture, which leaves the row in graphics; the
                #  writer reads that and its white text emits the attribute that
                #  returns to letters.
                canvas.row(at + offset).starting_at(column + COLUMN_CELLS).text(
                    line, Colour.WHITE
                )
