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
whatever is falling in the bottom. Only the thunder icons split a band, and only
because six of the 41 symbols carry thunder and would otherwise be drawn exactly
like the six without it.

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


#  -- the pieces -------------------------------------------------------------
#
#  Six blocks across, three down. Drawn as themselves so that changing one is a
#  matter of moving a hash, which is the only way small pictures ever get made.

EMPTY: Final = _piece("""
......
......
......
""")

#: A disc with corner rays. The rays are single blocks because anything thicker
#: at this size closes up into a square.
SUN: Final = _piece("""
#.##.#
.####.
#.##.#
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
..##..
.####.
######
""")

#: Less of one, for `fair`: a sky that is mostly not cloud.
CLOUD_SMALL: Final = _piece("""
......
...##.
..####
""")

#: Fog, as the flat bars it looks like from inside. The same in every band, so
#: the whole icon is one texture.
FOG: Final = _piece("""
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

#: Sleet, which is both at once and drawn as both: a stroke beside a flake.
SLEET_LIGHT: Final = _piece("""
......
.#....
.#..#.
""")

SLEET: Final = _piece("""
......
#...#.
#.#.#.
""")

SLEET_HEAVY: Final = _piece("""
#...#.
#.#.#.
#...#.
""")

#  Thunder is the one weather that needs two colours on one row, and it is
#  worth what it costs: six of the 41 symbols carry thunder, and drawn in the
#  fall's own colour they would differ from the plain ones by nothing at all.
#
#  So the bottom band buys a second attribute out of its picture and is left
#  with two cells a blank cell apart. What falls goes on the left in its own
#  colour, the bolt on the right in yellow.

#: A bolt, in the two blocks a split band leaves for it. A zigzag is the only
#: lightning there is at this size, and yellow does the rest of the telling.
BOLT: Final = _half("""
.#
##
#.
""")

#: What falls, beside a bolt. One stroke, as long as the weather is hard: the
#: same rule as the full-width falls, in the one column there is room for.
FALL_LIGHT: Final = _half("""
..
..
#.
""")

FALL: Final = _half("""
..
#.
#.
""")

FALL_HEAVY: Final = _half("""
#.
#.
#.
""")

#  -- what goes where --------------------------------------------------------

#: Rain blue, snow white, sleet between them. The cloud is cyan in every case,
#: so a fall is told from the cloud above it by colour as well as by shape.
_FALLING: Final = {
    "rain": ((RAIN_LIGHT, RAIN, RAIN_HEAVY), Colour.BLUE),
    "sleet": ((SLEET_LIGHT, SLEET, SLEET_HEAVY), Colour.CYAN),
    "snow": ((SNOW_LIGHT, SNOW, SNOW_HEAVY), Colour.WHITE),
}

_BY_INTENSITY: Final = {"light": 0, "": 1, "heavy": 2}

CLOUD_COLOUR: Final = Colour.CYAN
SUN_COLOUR: Final = Colour.YELLOW
MOON_COLOUR: Final = Colour.WHITE
THUNDER_COLOUR: Final = Colour.YELLOW


def icon_for(symbol: str | None) -> WeatherIcon | None:
    """The picture for a symbol code, or None where there is none to draw.

    None rather than a blank or a guess. A code met.no added since this was
    written is better shown as an empty column -- the words beside it still say
    what it is -- than as the nearest weather we happen to know how to draw.
    """
    weather = taken_apart(symbol)
    if weather is None:
        return None
    return WeatherIcon(
        bands=(
            band(*_sky(weather)),
            band(*_middle(weather)),
            _fall(weather),
        )
    )


def _sky(weather: Weather) -> tuple[tuple[int, ...], Colour]:
    """The top band: what is above the weather, or the top of the cloud."""
    if weather.core == "fog":
        return FOG, CLOUD_COLOUR
    if weather.core == "clearsky":
        #  Nothing but sky, so the sun goes in the middle band where it sits
        #  square in the column rather than perched at the top of it.
        return EMPTY, SUN_COLOUR
    if _sunny(weather):
        return (MOON, MOON_COLOUR) if weather.when == NIGHT else (SUN, SUN_COLOUR)
    return CLOUD_TOP, CLOUD_COLOUR


def _middle(weather: Weather) -> tuple[tuple[int, ...], Colour]:
    """The middle band: the cloud, or the sun where there is no cloud."""
    if weather.core == "fog":
        return FOG, CLOUD_COLOUR
    if weather.core == "clearsky":
        return (MOON, MOON_COLOUR) if weather.when == NIGHT else (SUN, SUN_COLOUR)
    if weather.core == "fair":
        return CLOUD_SMALL, CLOUD_COLOUR
    return CLOUD, CLOUD_COLOUR


def _fall(weather: Weather) -> Band:
    """The bottom band: what is coming down, and the thunder beside it."""
    if weather.core == "fog":
        #  Fog is the one weather that is not above the reader, so it is drawn
        #  through all three bands rather than hanging from a cloud.
        return band(FOG, CLOUD_COLOUR)
    if weather.thunder:
        #  The one row in the icon that spends a cell on a second colour. What
        #  falls keeps its own colour on the left; the bolt is yellow, on the
        #  right, and the blank cell between them is the attribute that pays
        #  for it.
        beside = (FALL_LIGHT, FALL, FALL_HEAVY)[_BY_INTENSITY[weather.intensity]]
        colour = _FALLING[weather.core][1] if weather.falling else CLOUD_COLOUR
        return Band(
            patches=(Patch(colour, beside), Patch(THUNDER_COLOUR, BOLT))
        )
    if not weather.falling:
        return band(EMPTY, CLOUD_COLOUR)
    pieces, colour = _FALLING[weather.core]
    return band(pieces[_BY_INTENSITY[weather.intensity]], colour)


def draw(canvas: Canvas, row: int, column: int, drawn: WeatherIcon) -> None:
    """Put an icon on a frame, its attribute cell at `column`.

    Placed at an absolute column rather than written along the row, and the
    attribute is spent whether the colour changed or not. A row writer would
    charge for it only when the colour changes, so two hours running under the
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
