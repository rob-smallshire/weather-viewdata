"""The weather as a picture, three cells by three.

**Nine cells, and the shape of them is decided by what an attribute costs.** A
mosaic run needs a graphics colour attribute, and an attribute takes a cell of
its own -- so an hour column four cells wide is one attribute and three cells of
picture, on each of three rows. **A row is one colour, unless it buys a second
one out of its own picture**: two attributes and two cells of mosaic still come
to four, and what is left is two blocks, a blank, two blocks.

That single fact decides every drawing here. A sun cannot sit *behind* a cloud
in a different colour, because a full-width band has one colour to spend; so it
sits *above* one. The sky goes in the top band, the cloud in the middle, and
whatever is falling in the bottom.

Only the bottom band splits, and the two things it can hold are the whole
grammar of falling weather: sleet is snow beside rain, thunder is a bolt beside
what falls, and three into two does not go.

**The pieces are composed, not tabulated.** met.no publishes 83 codes and they
are built by concatenation, so the icons are built the same way from about a
dozen pieces: a sky, a cloud, and a fall. `symbols.taken_apart` does the reading
and this module does the drawing, so there is one place that knows how a code is
spelled.

The composition also explains a thing about met.no's own list that looks
arbitrary: only the *showers* codes have `_day` and `_night` variants. It is
because only they have the sun in them -- a shower has sky between the clouds
and continuous rain has not -- which is exactly the rule the top band follows.

Six blocks across and nine down is not much. What survives at that size is
silhouette and colour, so the pieces are drawn for those and for nothing else.
"""

from dataclasses import dataclass
from typing import Final

from sextile.viewdata.blocks import Icon, icon
from sextile.viewdata.canvas import Canvas
from sextile.viewdata.charset import mosaic_code
from sextile.viewdata.controls import Colour, graphics_colour
from weather_viewdata.symbols import NIGHT, Weather, taken_apart

#: Cells an icon occupies each way, and so the shape every piece is drawn to.
#: Three cells is six blocks across; three rows is nine blocks down.
CELLS_ACROSS: Final = 3
BANDS: Final = 3

#: What a whole hour column costs: the picture, and the attribute that colours
#: each row of it.
ATTRIBUTE_CELL: Final = 1
COLUMN_CELLS: Final = CELLS_ACROSS + ATTRIBUTE_CELL


@dataclass(frozen=True)
class Patch:
    """A run of mosaic cells in one colour, and the attribute that enters it."""

    colour: Colour
    cells: tuple[int, ...]

    @property
    def width(self) -> int:
        """Cells it costs, its attribute included."""
        return ATTRIBUTE_CELL + len(self.cells)


@dataclass(frozen=True)
class Band:
    """One row of an icon, as the four cells it has to spend.

    Usually one patch: an attribute and three cells of picture, all one colour.
    A row that wants **two** colours buys the second attribute out of the
    picture, and is left with two cells of mosaic a blank cell apart -- two
    blocks, a gap, two blocks. That is the whole of the freedom there is, and
    the thunder icons are what it was spent on.

    The four cells are the invariant. A band that spent three or five would put
    the hour beneath it out of line with the picture above it, which in a strip
    of ten is the only mistake that shows from across the room.
    """

    patches: tuple[Patch, ...]

    def __post_init__(self) -> None:
        if sum(patch.width for patch in self.patches) != COLUMN_CELLS:
            raise ValueError(
                f"a band is {COLUMN_CELLS} cells, attributes included, "
                f"and this one is {sum(patch.width for patch in self.patches)}"
            )

    @property
    def cells(self) -> tuple[int, ...]:
        """Every mosaic pattern in it, in order and without the attributes."""
        return tuple(cell for patch in self.patches for cell in patch.cells)

    @property
    def colour(self) -> Colour:
        """The colour it begins in, which for most bands is the only one."""
        return self.patches[0].colour


def band(cells: tuple[int, ...], colour: Colour) -> Band:
    """The ordinary sort: one colour across the whole row."""
    return Band(patches=(Patch(colour, cells),))


@dataclass(frozen=True)
class WeatherIcon:
    """A whole picture: three bands, top to bottom."""

    bands: tuple[Band, ...]


def _piece(art: str, *, cells: int = CELLS_ACROSS) -> tuple[int, ...]:
    """A band's worth of blocks, as the mosaic patterns for it."""
    drawn: Icon = icon(art)
    if drawn.rows != 1 or drawn.cells_across > cells:
        raise ValueError(f"a piece is at most {cells} cells across and one row down")
    patterns = drawn.cells()[0]
    return tuple(patterns) + (0,) * (cells - len(patterns))


def _half(art: str) -> tuple[int, ...]:
    """Half a band: one cell, for a row that is spending the other on colour."""
    return _piece(art, cells=1)


def _figure(art: str) -> tuple[tuple[int, ...], ...]:
    """A picture drawn across all nine cells, in one colour.

    The exception to the three bands, and there are exactly two of them:
    `clearsky` and `fog` are the states with **nothing to stack** -- no cloud
    and nothing falling -- so there is no reason to spend the picture on layers
    that are not there. Six blocks by nine, all one colour, which costs no more
    attributes than three bands do.
    """
    drawn: Icon = icon(art)
    if drawn.rows != BANDS or drawn.cells_across > CELLS_ACROSS:
        raise ValueError(f"a figure is {CELLS_ACROSS} cells across and {BANDS} down")
    return tuple(
        tuple(patterns) + (0,) * (CELLS_ACROSS - len(patterns))
        for patterns in drawn.cells()
    )


#  -- the pieces -------------------------------------------------------------
#
#  Six blocks across, three down. Drawn as themselves so that changing one is a
#  matter of moving a hash, which is the only way small pictures ever get made.

EMPTY: Final = _piece("""
......
......
......
""")

#: A disc with corner rays, for fair and part cloudy weather -- a sky that is
#: mostly sky, with a sun that can afford to look like one.
SUN: Final = _piece("""
#.##.#
.####.
#.##.#
""")

#: And a smaller one for a sun above weather that is falling. The disc above is
#: too intense over rain: a shower has a sun *between* the clouds rather than
#: blazing over them, and the picture should say which of the two the hour is
#: mostly about. Low and to the left, so it reads as peeping past the cloud
#: beneath rather than sitting on top of it.
SUN_SMALL: Final = _piece("""
......
..#...
.###..
""")

#: A crescent, which is the only moon that reads as one at six blocks across.
#: Facing right because a waxing moon does, and because the cloud beneath is
#: drawn heavier on the left.
MOON: Final = _piece("""
..###.
..#...
..###.
""")

#: The top of a cloud, for the codes with no sky in them. Overcast is overcast
#: at midnight, which is why met.no gives these no time of day.
CLOUD_TOP: Final = _piece("""
......
..##..
.####.
""")

#: The cloud itself, flat along the bottom so that what falls out of it starts
#: from a line.
CLOUD: Final = _piece("""
..#...
.###..
######
""")

#: Less of one, for `fair`: a sky that is mostly not cloud.
CLOUD_SMALL: Final = _piece("""
......
...##.
..####
""")

#  -- the figures ------------------------------------------------------------
#
#  Two states have nothing to stack -- no cloud, and nothing falling -- so they
#  are not assembled from bands at all. They are one picture across all nine
#  cells, which costs no more attributes than three bands do and is not a
#  special case so much as the other half of the grammar: **either the weather
#  has layers, or it is one thing.**

#: A clear sky, which is worth the whole picture. Small it is a mark among
#: marks; large it is the one frame in a strip of ten that a reader picks out
#: without reading anything.
SUN_FIGURE: Final = _figure("""
......
......
.#.#.#
..###.
.#####
..###.
.#.#.#
......
......
""")

#: And the same by night. A crescent rather than a disc, because a full moon
#: and a sun at this size are the same drawing.
MOON_FIGURE: Final = _figure("""
......
......
...##.
....##
....##
...###
.#####
..###.
......
""")

#: Fog, as the flat bars it looks like from inside. Drawn whole so the bars are
#: evenly spaced: three bands of the same piece put two of them side by side.
FOG_FIGURE: Final = _figure("""
.####.
......
.####.
......
.####.
......
.####.
......
.####.
""")

#  Two things say how hard it is coming down, and they are the same two for
#  rain, sleet and snow: **how many fall, and how far up they reach.** Light and
#  middling leave the top row of the band clear, so that there is daylight
#  between the cloud and what is under it; heavy fills that row too, and reads
#  as heavier for touching the cloud it comes from.

#: Rain, as strokes, because rain falls in lines.
RAIN_LIGHT: Final = _piece("""
......
.#..#.
.#..#.
""")

RAIN: Final = _piece("""
......
#.#.#.
#.#.#.
""")

RAIN_HEAVY: Final = _piece("""
#.#.#.
#.#.#.
#.#.#.
""")

#: Snow, as flakes: single blocks, scattered rather than ranked, because snow
#: does not fall in lines.
SNOW_LIGHT: Final = _piece("""
......
.#....
....#.
""")

SNOW: Final = _piece("""
......
#..#..
..#..#
""")

SNOW_HEAVY: Final = _piece("""
#..#..
..#..#
#..#..
""")

#  -- half a band ------------------------------------------------------------
#
#  **The bottom band holds at most two things, and the whole grammar of falling
#  weather is which two.** A row that wants two colours buys the second
#  attribute out of its picture, so what is left is two blocks, a blank, two
#  blocks -- one cell each for two of `snow`, `rain` and a bolt.
#
#  Sleet is what makes it worth the cell. Sleet *is* snow and rain at once, and
#  drawn as one colour it can only be a compromise between them: it was cyan,
#  which is also the cloud's colour and so said "cloud" more than it said
#  "sleet". Drawn as white beside blue it says what it is.
#
#  Three into two does not go, and **the bolt always gets its place.** Thunder
#  is the exceptional condition and the one worth seeing from across a room,
#  where sleet against rain is a detail the words beside the picture carry. So
#  sleet with thunder in it is drawn as rain with thunder in it -- six of the
#  41 symbols -- and errs towards wet, which is the safer way for a reader
#  deciding whether to go out to be wrong.

#: Half a band with nothing in it, for a fall that has only one thing to say.
EMPTY_HALF: Final = _half("""
..
..
..
""")

#: A bolt, in the two blocks half a band leaves for it. A zigzag is the only
#: lightning there is at this size, and yellow does the rest of the telling.
BOLT: Final = _half("""
.#
##
#.
""")

#: Rain in half a band: one stroke, as long as the weather is hard. The same
#: rule as the full-width falls, in the one column there is room for.
RAIN_HALF_LIGHT: Final = _half("""
..
..
#.
""")

RAIN_HALF: Final = _half("""
..
#.
#.
""")

RAIN_HALF_HEAVY: Final = _half("""
#.
#.
#.
""")

#: Snow in half a band: flakes rather than a stroke, so that the two halves of
#: sleet are told apart by shape as well as by colour.
SNOW_HALF_LIGHT: Final = _half("""
..
#.
..
""")

SNOW_HALF: Final = _half("""
.#
..
#.
""")

SNOW_HALF_HEAVY: Final = _half("""
#.
.#
#.
""")

#  -- what goes where --------------------------------------------------------

#: The falls that take a whole band, by how hard they are coming down.
_WHOLE: Final = {
    "rain": (RAIN_LIGHT, RAIN, RAIN_HEAVY),
    "snow": (SNOW_LIGHT, SNOW, SNOW_HEAVY),
}

#: And the same in half a band, for a row with something else to fit in.
_HALF: Final = {
    "rain": (RAIN_HALF_LIGHT, RAIN_HALF, RAIN_HALF_HEAVY),
    "snow": (SNOW_HALF_LIGHT, SNOW_HALF, SNOW_HALF_HEAVY),
}

#: Rain blue and snow white, and sleet both of them side by side. The cloud is
#: cyan in every case, so nothing that falls shares a colour with what it falls
#: from.
RAIN_COLOUR: Final = Colour.BLUE
SNOW_COLOUR: Final = Colour.WHITE

_FALL_COLOURS: Final = {"rain": RAIN_COLOUR, "snow": SNOW_COLOUR}

#: What sleet is made of, in the order it is drawn: the frozen half first.
_SLEET: Final = ("snow", "rain")

_BY_INTENSITY: Final = {"light": 0, "": 1, "heavy": 2}

CLOUD_COLOUR: Final = Colour.CYAN
SUN_COLOUR: Final = Colour.YELLOW
MOON_COLOUR: Final = Colour.WHITE
THUNDER_COLOUR: Final = Colour.YELLOW


def _figure_for(weather: Weather) -> tuple[tuple[tuple[int, ...], ...], Colour] | None:
    """The whole-picture drawing for this weather, if it has one."""
    if weather.core == "clearsky":
        if weather.when == NIGHT:
            return MOON_FIGURE, MOON_COLOUR
        return SUN_FIGURE, SUN_COLOUR
    if weather.core == "fog":
        #  The one weather that is not above the reader but around them.
        return FOG_FIGURE, CLOUD_COLOUR
    return None


def icon_for(symbol: str | None) -> WeatherIcon | None:
    """The picture for a symbol code, or None where there is none to draw.

    None rather than a blank or a guess. A code met.no added since this was
    written is better shown as an empty column -- the words beside it still say
    what it is -- than as the nearest weather we happen to know how to draw.
    """
    weather = taken_apart(symbol)
    if weather is None:
        return None
    figure = _figure_for(weather)
    if figure is not None:
        rows, colour = figure
        return WeatherIcon(bands=tuple(band(cells, colour) for cells in rows))
    return WeatherIcon(
        bands=(
            band(*_sky(weather)),
            band(*_middle(weather)),
            _fall(weather),
        )
    )


def _sky(weather: Weather) -> tuple[tuple[int, ...], Colour]:
    """The top band: what is above the weather, or the top of the cloud."""
    if not _sunny(weather):
        return CLOUD_TOP, CLOUD_COLOUR
    if weather.when == NIGHT:
        return MOON, MOON_COLOUR
    #  Small where something is falling, full-size where the sky is mostly sky.
    return (SUN_SMALL if weather.falling else SUN), SUN_COLOUR


def _middle(weather: Weather) -> tuple[tuple[int, ...], Colour]:
    """The middle band: the cloud, less of one for fair weather."""
    if weather.core == "fair":
        return CLOUD_SMALL, CLOUD_COLOUR
    return CLOUD, CLOUD_COLOUR


def _fall(weather: Weather) -> Band:
    """The bottom band: what is coming down, and what else will fit beside it.

    At most two things, because a second colour costs a cell of picture and
    there are only three. Which two is the whole grammar of falling weather:

        rain, snow            the whole band, in their own colour
        sleet                 both, side by side: snow white, rain blue
        anything + thunder    that thing, in half a band, and a yellow bolt
        sleet + thunder       rain and a bolt -- see the note above
    """
    hard = _BY_INTENSITY[weather.intensity]
    if weather.thunder:
        return Band(patches=(_beside_the_bolt(weather, hard), Patch(THUNDER_COLOUR, BOLT)))
    if weather.core == "sleet":
        return Band(
            patches=tuple(
                Patch(_FALL_COLOURS[kind], _HALF[kind][hard]) for kind in _SLEET
            )
        )
    if not weather.falling:
        return band(EMPTY, CLOUD_COLOUR)
    return band(_WHOLE[weather.core][hard], _FALL_COLOURS[weather.core])


def _beside_the_bolt(weather: Weather, hard: int) -> Patch:
    """What shares the band with a bolt.

    Sleet is drawn as rain here, there being one cell and two things it is made
    of. Wet rather than frozen, which is the safer way to be wrong for a reader
    deciding whether to go out.
    """
    if not weather.falling:
        #  No published code is thunder with nothing falling, but a code added
        #  next year might be, and an empty half is a better answer than a
        #  lookup that fails at the far end of a telephone line.
        return Patch(CLOUD_COLOUR, EMPTY_HALF)
    kind = "rain" if weather.core == "sleet" else weather.core
    return Patch(_FALL_COLOURS[kind], _HALF[kind][hard])


def draw(canvas: Canvas, row: int, column: int, drawn: WeatherIcon) -> None:
    """Put an icon on a frame, its first attribute cell at `column`.

    Placed at an absolute column rather than written along the row, and every
    attribute is spent whether the colour changed or not. A row writer would
    charge for one only when the colour changes, so two hours running under the
    same sky would close up by a cell and the pictures would stop lining up with
    the hours beneath them.
    """
    frame = canvas.frame
    for offset, drawn_band in enumerate(drawn.bands):
        at = column
        for patch in drawn_band.patches:
            frame.set_attribute(row + offset, at, graphics_colour(patch.colour))
            at += ATTRIBUTE_CELL
            for pattern in patch.cells:
                frame.set_cell(row + offset, at, mosaic_code(pattern))
                at += 1


#: The states with sky above them: nothing is falling, or it is falling in
#: showers with breaks between. Which is met.no's own rule rather than ours --
#: these are exactly the 21 ids they give `_day` and `_night` variants to, and
#: they give them variants because these are the ones with a sun in them.
_SKY_STATES: Final = {"clearsky", "fair", "partlycloudy"}


def _sunny(weather: Weather) -> bool:
    """Whether the sky shows above this weather."""
    return weather.showers or weather.core in _SKY_STATES
