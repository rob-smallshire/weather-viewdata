"""The weather, as a Viewdata service.

Global, because met.no forecasts anywhere; dialled mostly from Britain, because
that is where the working Beebs are. Those two facts pull against each other
exactly once, in the ranking, and are settled there.

    0                  the title frame
    1                  the main menu
    3                  find a place by name
    321<geoname-id>    one place's forecast, as a table
    4                  find a point by position
    421<lat><lon>      one point's forecast, as a table
    9  about   90 goodbye   91 help   92/93/94 the framework's pages

Two ways to name a forecast, failing differently. A named place carries a name,
a timezone and an altitude, and depends on GeoNames still holding that record.
A point carries none of those and depends on nothing at all.

Three digits of prefix rather than two, because a forecast is one body of
numbers with more than one honest way of showing it: the last of them says
which. The subject follows unchanged, so the same weather is a table at
`321<geoname-id>` and a graph at `322<geoname-id>`.

The pages are ordinary functions, declared beside one another and given to the
constructor as a list. Nothing closes over anything: a page takes the index
from what the service holds and the numbering from the service itself, both
through the request. That is what lets the whole service be a value, and what
makes the order things were registered in unobservable.
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sextile import (
    Page,
    PageAddress,
    PageFrame,
    PageRequest,
    PageRoute,
    Sextile,
    Suggest,
    draw_form,
)
from sextile.addressing import keyed
from sextile.forms import SUGGESTIONS, Field, Fields
from sextile.middleware import log_pages
from sextile.templates import (
    HOME_KEY,
    Entry,
    Menu,
    MenuItem,
    PreambleLine,
    Prose,
    Template,
)
from sextile.viewdata.canvas import Canvas, RowWriter, Run
from sextile.viewdata.chrome import CONTENT_FIRST_ROW, draw_chrome
from sextile.viewdata.controls import Colour, Control
from sextile.viewdata.drawing import centred
from sextile.viewdata.encoding import fitted
from sextile.viewdata.footer import ROOM, FooterItem, Priority, render_footer
from sextile.viewdata.frame import COLUMNS
from sextile.viewdata.wrapping import wrap_within
from weather_viewdata.coordinates import LATITUDE, LONGITUDE
from weather_viewdata.forecast.model import Forecast, Moment
from weather_viewdata.forecast.source import ForecastSource
from weather_viewdata.geonames import Place
from weather_viewdata.icons import BANDS, COLUMN_CELLS, icon_for
from weather_viewdata.icons import draw as draw_icon
from weather_viewdata.store import Index, Nearby
from weather_viewdata.symbols import PUBLISHED, in_full, in_words
from weather_viewdata.wind import from_the

SERVICE_NAME: Final = "WEATHER"

DEFAULT_INDEX_FILEPATH: Final = Path("places.sqlite")

#: What kind of page this is, within a namespace whose root is a search frame.
#: There is only one kind so far, and naming it leaves room beside it for a
#: page about a place that is not its weather.
_FORECAST: Final = "2"

#: How a forecast is drawn, as the digit that says so. A forecast is one body
#: of numbers and there is more than one honest way to show it: a table reads
#: exactly and a graph reads at a glance, and neither is the poor relation. So
#: the presentation is part of the address rather than a mode the reader has to
#: get the frame into -- a number written down fetches back what was written
#: down, and a reader can key straight to the one they want.
#:
#: It goes before the subject and not after because a geoname id has no fixed
#: width: `321` then the id can be split apart, `32` then the id then a digit
#: cannot. The cost is that the digit renumbers everything after it, so there
#: is no reading `323133880` under both schemes and no aliasing the old one.
TABLE: Final = "1"
GRAPH: Final = "2"

#: Seconds an hour, for saying what period a rainfall figure covers.
_SECONDS_AN_HOUR: Final = 3600

#: A cell for the colour the weather is written in. What is left after the
#: clocks, the temperature and the wind is the weather's -- counted from the
#: row rather than worked out here, an attribute costing a cell and
#: hand-arithmetic about that having been wrong the first time.
_COLOUR_CELL: Final = 1

#: What this caller's search field is held under, in what the caller has
#: accumulated. The session's, not the service's: it is one reader's typing and
#: lasts exactly as long as their line.
SEARCH: Final = "search"

#: Where the field and its suggestions sit on the search page.
FIELD_ROW: Final = CONTENT_FIRST_ROW + 2
FIRST_SUGGESTION_ROW: Final = FIELD_ROW + 2

#: What this caller's position form is held under.
POSITION: Final = "position"

#: Where the position form's own rows sit. Each field has its advice on the
#: row beneath it and a blank row after that: two labelled fields set solid
#: read as a block of text rather than as two places to type, and a screen of
#: twenty content rows has the room to spare.
LATITUDE_ROW: Final = CONTENT_FIRST_ROW + 2
LONGITUDE_ROW: Final = LATITUDE_ROW + 3

#: Where it says what is nearest to what has been keyed.
NOTE_ROW: Final = LONGITUDE_ROW + 3

#: Cells a coordinate may take, and the width of the bar that says so. Six is
#: the longest there is: `-179.9` signed, `179.9W` with the hemisphere. A
#: seventh would be a cell of blue promising room that nothing could go in.
_POSITION_CELLS: Final = 6

#: What the place index and the forecast source are held under, in what the
#: service holds. Named constants rather than literals at each use, since a
#: mistyped key is a page that fails at the far end of a telephone line.
PLACES: Final = "places"
FORECASTS: Final = "forecasts"

#: The legend page's grid: two pictures to a row, each with its words beside
#: it. Half a row apiece, less the picture and the attribute that colours the
#: words, and one more cell so the two halves do not touch.
_PICTURES_ACROSS: Final = 2
_PICTURE_CELLS: Final = COLUMNS // _PICTURES_ACROSS
_WORD_CELLS: Final = _PICTURE_CELLS - COLUMN_CELLS - 2

#: Spaced to the columns `ForecastTable.draw` writes, with the units said once
#: rather than in every row: at forty columns a degree sign in eighty places is
#: a column of forecast nobody can read.
_HEADINGS: Final = "  UTC LOCAL  DEG C  M/S  WEATHER"

class StaleIndexError(RuntimeError):
    """The place index was built by rules this code no longer uses."""


def _places(service: Mapping[str, object]) -> Index:
    """The place index, out of what the service holds.

    A narrowing with a reason attached: what a service holds is typed as
    objects, because the framework cannot know what any service puts in it, and
    this is the one function that does know.
    """
    index = service.get(PLACES)
    if not isinstance(index, Index):
        raise RuntimeError("the place index is not open; the service has not started")
    return index


def _service(request: PageRequest) -> Sextile:
    """The application a page belongs to, narrowed to the one it is.

    `request.application` is optional because a request built by hand in a test
    has no service behind it. Every request the session or the renderer makes
    carries one, so a handler reached through either may say so.
    """
    app = request.application
    if not isinstance(app, Sextile):
        raise RuntimeError("this page was asked for outside a running service")
    return app


# -- the pages ---------------------------------------------------------------
#
#  Ordinary functions, declared beside one another and given to the constructor
#  below. Each takes what it needs from the request: the index from what the
#  service holds, the numbering from the service itself. Nothing here closes
#  over anything, which is what lets the service be a list.


async def title(request: PageRequest) -> Page:
    """The frame the line opens on.

    No page number in the header: `*0#` is the back command, so a number here
    would be an instruction that does not work.
    """
    canvas = Canvas()
    centred(canvas, 2, SERVICE_NAME, Colour.YELLOW)
    centred(canvas, 4, "Forecasts for anywhere on earth", Colour.WHITE)
    centred(canvas, 7, "from the Norwegian", Colour.CYAN)
    centred(canvas, 8, "Meteorological Institute", Colour.CYAN)
    centred(canvas, 11, f"{_places(request.service).held():,} places held", Colour.WHITE)
    centred(canvas, 14, "Key # to begin", Colour.YELLOW)
    centred(canvas, 20, "Weather from met.no, CC BY 4.0", Colour.GREEN)
    centred(canvas, 21, "Places from GeoNames, CC BY 4.0", Colour.GREEN)
    #  `follows` is what makes `#` mean something here. Without it the title
    #  frame is a dead end under the one key a viewdata reader tries first.
    return Page(
        frames=(PageFrame(frame=canvas.frame),), follows=_service(request).index
    )


async def main(request: PageRequest) -> Page:
    app = _service(request)
    return Menu(
        title=SERVICE_NAME,
        entries=[
            MenuItem.for_page(app, name)
            for name in ("by_name", "by_position", "help", "about", "goodbye")
        ],
        home=app.index,
        preamble=["Forecasts for anywhere on earth."],
    ).build(request.address)


async def by_name(request: PageRequest) -> Page:
    """A field, with the best three places beneath it as the reader types.

    The form lives in the session rather than in this function, because it is
    one caller's typing and lasts as long as their line. It survives leaving
    the page and coming back, which is what a reader who has just looked at one
    of three candidates wants: the word is still there to be refined rather
    than typed again.
    """
    app = _service(request)
    form = request.session.get(SEARCH)
    if not isinstance(form, Suggest):
        form = _field(app, _places(request.service))
        request.session[SEARCH] = form

    canvas = Canvas()
    draw_chrome(
        canvas,
        title=app.describe(request.address).upper(),
        page_number=request.address.frame_number(0),
        prompt=render_footer(
            [
                #  What `#` does is marked against the suggestion it would
                #  take, which is where a reader is looking anyway -- so the
                #  row has the room to say the rest in words.
                FooterItem("A-Z", "type a name", Priority.PRIMARY),
                FooterItem("1-3", "choose one", Priority.PRIMARY),
                FooterItem(HOME_KEY, "menu", Priority.ESSENTIAL),
            ],
            ROOM,
        ),
    )
    canvas.row(CONTENT_FIRST_ROW).text("Key a place name.", Colour.WHITE)
    draw_form(canvas.frame, form)
    #  There is nothing to say about letters this keypad has not got, because
    #  the screen has not got them either: a reader never sees the o-slash in
    #  Tromso, so they never wonder how to key it. Both folds are the same
    #  fold, which is what makes "as it is shown here" the whole rule.
    #
    #  It said "no space bar, no accents". There is a space bar -- it sends
    #  0x20 like any other key -- and the letters in question are not accented
    #  Latin ones but letters of other alphabets, which this hardware cannot
    #  draw and so never shows.
    canvas.row(FIRST_SUGGESTION_ROW + SUGGESTIONS + 1).text(
        "Key a name as it is shown here.", Colour.GREEN
    )
    canvas.row(FIRST_SUGGESTION_ROW + SUGGESTIONS + 2).text(
        "Spaces do not matter.", Colour.GREEN
    )
    canvas.row(FIRST_SUGGESTION_ROW + SUGGESTIONS + 4).text(
        f"{_places(request.service).held():,} places held.", Colour.WHITE
    )
    return Page(
        frames=(
            PageFrame(frame=canvas.frame, form=form, choices={HOME_KEY: app.index}),
        )
    )


def _field(app: Sextile, places: Index) -> Suggest:
    """The search field, told where to look and where its digits lead."""

    async def look_up(typed: str) -> Sequence[Entry]:
        found = await asyncio.to_thread(places.matching, typed, SUGGESTIONS)
        return [
            MenuItem(
                text=place.name,
                detail=place.country,
                destination=app.address_for("place", geoname_id=place.geoname_id),
            )
            for place in found
        ]

    return Suggest(
        look_up=look_up,
        field_row=FIELD_ROW,
        first_row=FIRST_SUGGESTION_ROW,
        label="PLACE:",
        limit=SUGGESTIONS,
        empty="No place of that name is held.",
    )


async def by_position(request: PageRequest) -> Page:
    """Two fields, for anywhere on earth whether anybody lives there or not.

    `0` is not the way out here and the footer does not pretend otherwise: on
    a page where digits are data, a `0` that went to the menu would be a key
    that ate a coordinate.
    """
    app = _service(request)
    form = request.session.get(POSITION)
    if not isinstance(form, Fields):
        form = _position_fields(app, _places(request.service))
        request.session[POSITION] = form

    canvas = Canvas()
    draw_chrome(
        canvas,
        title=app.describe(request.address).upper(),
        page_number=request.address.frame_number(0),
        prompt=render_footer(
            [
                #  Not `#`. It moves to the next field from every field but
                #  the last, so a footer saying "# go there" is false wherever
                #  the reader most likely is. What it does on the last field is
                #  marked against that field, where the reader is looking.
                FooterItem("TAB", "next field", Priority.PRIMARY),
                FooterItem("DEL", "rub out", Priority.SECONDARY),
                FooterItem(keyed(app.index), "menu", Priority.ESSENTIAL),
            ],
            ROOM,
        ),
    )
    canvas.row(CONTENT_FIRST_ROW).text("Key a position in degrees,", Colour.WHITE)
    canvas.row(CONTENT_FIRST_ROW + 1).text("to one decimal place.", Colour.WHITE)
    draw_form(canvas.frame, form)
    return Page(frames=(PageFrame(frame=canvas.frame, form=form),))


def _position_fields(app: Sextile, places: Index) -> Fields:
    """The two coordinate fields, and what they add up to."""

    async def nearest(values: Mapping[str, str]) -> str:
        where = _position(values)
        if where is None:
            return ""
        found = await asyncio.to_thread(places.nearest, *where)
        if found is None:
            #  Somewhere with nothing within a degree, which is most of the
            #  earth's surface. Said rather than left blank: a reader who has
            #  keyed a valid position should not wonder whether it took.
            return "Nowhere within 111km."
        return fitted(
            f"{found.kilometres:.0f}km from {found.place.name}", COLUMNS - 1
        )

    def complete(values: Mapping[str, str]) -> PageAddress | None:
        where = _position(values)
        if where is None:
            return None
        return app.address_for("point", lat=where[0], lon=where[1])

    return Fields(
        fields=[
            Field(
                name="latitude",
                label="LATITUDE",
                row=LATITUDE_ROW,
                takes=_takes("NS"),
                width=_POSITION_CELLS,
                hint=" north or south: 54.0N or 54.0S",
                hint_row=LATITUDE_ROW + 1,
            ),
            Field(
                name="longitude",
                label="LONGITUDE",
                row=LONGITUDE_ROW,
                takes=_takes("EW"),
                width=_POSITION_CELLS,
                hint=" east or west: 17.2E or 17.2W",
                hint_row=LONGITUDE_ROW + 1,
            ),
        ],
        complete=complete,
        note=nearest,
        note_row=NOTE_ROW,
        sends="forecast",
    )


def _takes(hemispheres: str) -> Callable[[str], bool]:
    """What belongs in a coordinate field.

    Both spellings are taken, because both are in use and a reader arriving
    with one should not have to discover that this service wanted the other.

    **Only the hemispheric one is advertised.** A field's advice sits under it
    on every frame, so it is read far more often than it is needed, and one
    that showed all four spellings shouted louder than the field it was
    explaining. Showing one way of writing a coordinate teaches the reader who
    does not know; taking both serves the reader who does.

    So the signs are deliberately undocumented rather than unsupported, and
    nothing above should be tidied to match the hint.
    """

    def takes(key: str) -> bool:
        return key.isdigit() or key in {".", "+", "-", *hemispheres}

    return takes


def _degrees_from(written: str, hemispheres: str) -> float | None:
    """One coordinate, written either way round, or None if it is not one."""
    said = written.strip().upper()
    if not said:
        return None
    negative = said.startswith("-") or said.endswith(hemispheres[1])
    figures = said.lstrip("+-").rstrip(hemispheres)
    try:
        degrees = float(figures)
    except ValueError:
        return None
    return -degrees if negative else degrees


def _position(values: Mapping[str, str]) -> tuple[float, float] | None:
    """Both fields as degrees, or None while either is not a coordinate."""
    latitude = _degrees_from(values.get("latitude", ""), "NS")
    longitude = _degrees_from(values.get("longitude", ""), "EW")
    if latitude is None or longitude is None:
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return latitude, longitude


async def place(request: PageRequest, geoname_id: int) -> Page | None:
    found = await asyncio.to_thread(_places(request.service).place, geoname_id)
    if found is None:
        #  Not here, which is different from here and empty. The session says
        #  so and leaves the reader where they were.
        return None
    source = _forecasts(request.service)
    return _forecast_page(
        _service(request), request.address, found, await source.forecast_for(found)
    )


async def point(request: PageRequest, lat: float, lon: float) -> Page:
    #  A point is not a place and cannot pretend to be one: at a tenth of a
    #  degree two thirds of the world's towns share a cell with another. So it
    #  borrows a clock from whatever is nearest, and says which.
    nearby = await asyncio.to_thread(_places(request.service).nearest, lat, lon)
    where = _point_place(lat, lon, nearby)
    source = _forecasts(request.service)
    return _forecast_page(
        _service(request),
        request.address,
        where,
        await source.forecast_for(where),
        near=nearby,
    )


async def about(request: PageRequest) -> Page:
    app = _service(request)
    return Prose.of(
        "The weather, served as Viewdata frames to computers that were obsolete "
        "before the forecast models were written.",
        "Forecasts come from the Norwegian Meteorological Institute, who "
        "publish them for anyone to use. Place names come from GeoNames. Both "
        "are licensed CC BY 4.0, and neither endorses this service.",
        "Forecasts are held for as long as met.no asks them to be, so two "
        "readers asking about the same town within the half hour are one "
        "request rather than two.",
        title=app.describe(request.address).upper(),
        home=app.index,
    ).build(request.address)


async def guide(request: PageRequest) -> Page:
    app = _service(request)
    finding = MenuItem.for_page(app, "by_name")
    return Prose.of(
        "Key a page number between * and #, as *1#.",
        f"{keyed(app.address_for('by_name'))} to {finding.text.lower()}, or "
        "simply key the name itself: *YORK#.",
        "# alone shows the next frame of a long page. *0# goes back where you "
        "came from, and 0 returns to the main menu from anywhere.",
        "W and S page up and down, and the cursor keys do the same.",
        "*09# fetches a page again, which on a forecast means asking whether "
        "there is a fresher one.",
        title=app.describe(request.address).upper(),
        home=app.index,
    ).build(request.address)


@dataclass(frozen=True)
class Pictured:
    """One entry of the legend: a symbol code, and what to call it here.

    The words are carried rather than worked out from the code, because the
    sky variants are on the page too and `in_words` drops the time of day --
    three entries all saying `clear` would be a legend that explained nothing.
    """

    code: str
    words: str


#: The sky variants, shown after the set rather than through it. They differ
#: from the day drawings in one piece and only for the 21 codes that have a sky
#: in them, so forty more pictures would say this four times over.
_SKIES: Final = (
    ("clearsky_night", "clear sky at night"),
    ("clearsky_polartwilight", "clear sky in polar twilight"),
    ("rainshowers_night", "rain showers at night"),
    ("rainshowers_polartwilight", "rain showers in polar twilight"),
)


async def pictures(request: PageRequest) -> Page:
    """Every picture the service draws, beside the words for it.

    The set, as met.no publishes it, in their order. Which is the only way to
    judge a set of pictures: one at a time they all look plausible, and side by
    side the two that cannot be told apart show up at once.

    The set is drawn by day, and the four sky variants follow it: a moon at
    night and a sun on the horizon in the polar twilight, on a clear sky and on
    a shower, which is the whole of what the time of day changes. Forty more
    pictures would say the same thing four times over.

    **The set is drawn by day whatever the hour.** A legend is a legend and not
    a forecast: there is no clock it could sensibly follow. Not the reader's --
    somebody in Britain at midnight may be looking up Auckland at noon -- and
    not any place's either, since the page is about none of them. Drawing it by
    day and showing what changes is the only reading that is right for every
    reader at once.
    """
    app = _service(request)
    return SymbolTable(
        title=app.describe(request.address).upper(),
        entries=_in_pairs(
            [Pictured(code, in_full(code)) for code in PUBLISHED]
            + [Pictured(code, words) for code, words in _SKIES]
        ),
        home=app.index,
        preamble=["Drawn by day, except where it says."],
    ).build(request.address)


def _in_pairs(shown: Sequence[Pictured]) -> list[tuple[Pictured, ...]]:
    """Two to a row, because a picture and its words are half a row wide."""
    return [
        tuple(shown[at : at + _PICTURES_ACROSS])
        for at in range(0, len(shown), _PICTURES_ACROSS)
    ]


class SymbolTable(Template[tuple[Pictured, ...]]):
    """Pictures with their words, two to a row and four rows to each.

    Everything is drawn from `draw_entry` rather than from `draw`, because a
    mosaic picture is placed by cell and is three rows tall: a row writer walks
    one row from left to right, which is the wrong shape for this and the right
    shape for everything else.
    """

    #  A blank row after each, or the bottom band of one picture and the top
    #  band of the next read as one picture: they are three rows apart, in the
    #  same colours, and nothing between them says where one ends. The strip on
    #  a forecast page has no such trouble, its pictures being side by side.
    rows_per_entry = BANDS + 1
    numbered = False

    def draw(
        self, row: RowWriter, entry: tuple[Pictured, ...], digit: str | None
    ) -> None:
        """Nothing. This shape draws from `draw_entry`; see the class docstring."""

    def draw_entry(
        self, canvas: Canvas, row: int, entry: tuple[Pictured, ...], digit: str | None
    ) -> None:
        del digit  # a legend numbers nothing
        for slot, shown in enumerate(entry):
            column = slot * _PICTURE_CELLS
            picture = icon_for(shown.code)
            if picture is not None:
                draw_icon(canvas, row, column, picture)
            #  The picture is three rows tall and the words get all three, so
            #  nothing here has to be abbreviated: `heavy sleet showers and
            #  thunder` is twenty-nine cells and three fourteens is forty-two.
            said = wrap_within(shown.words, cells=_WORD_CELLS, rows=BANDS)
            #  Centred against the picture, so a name of one line sits level
            #  with the cloud rather than perched above it.
            at = row + (BANDS - len(said)) // 2
            for offset, line in enumerate(said):
                canvas.frame.set_attribute(
                    at + offset, column + COLUMN_CELLS, Control.ALPHA_WHITE
                )
                canvas.frame.write(at + offset, column + COLUMN_CELLS + 1, line)


async def goodbye(request: PageRequest) -> Page:
    #  No footer and nothing below: the reader is about to be talking to their
    #  modem, and needs somewhere blank for the cursor to be left.
    canvas = Canvas()
    canvas.row(0).text("GOODBYE", Colour.CYAN)
    canvas.row(2).text("Thank you for calling.", Colour.WHITE)
    canvas.row(4).text("Ring off.", Colour.WHITE)
    return Page(frames=(PageFrame(frame=canvas.frame),), hang_up=True)


async def history(request: PageRequest) -> Page:
    return await _service(request).history(request)


async def contents(request: PageRequest) -> Page:
    return await _service(request).contents(request)


async def keywords(request: PageRequest) -> Page:
    return await _service(request).names(request)


#: What the service is made of, in the order a reader meets it. Everything
#: about a page is on one line of this: where it is in the numbering, what
#: builds it, what it is called where it is listed, and the words that reach
#: it. Nothing about a page is anywhere else.
PAGES: Final = (
    PageRoute("0", title, name="title"),
    PageRoute("1", main, name="main", title="Main menu",
              keywords=("MAIN", "INDEX", "HOME")),
    PageRoute("3", by_name, name="by_name", title="Find a place by name",
              detail="key its name, as *YORK#",
              keywords=("FIND", "PLACE", "SEARCH")),
    PageRoute(f"3{_FORECAST}{TABLE}{{geoname_id:int}}", place, name="place",
              title="One place"),
    PageRoute("4", by_position, name="by_position",
              title="Find a point by position",
              detail="anywhere, to a tenth of a degree",
              keywords=("POSITION", "COORDS")),
    PageRoute(f"4{_FORECAST}{TABLE}{{lat:latitude}}{{lon:longitude}}", point,
              name="point", title="One point"),
    PageRoute("9", about, name="about", title="About this service",
              keywords=("ABOUT",)),
    PageRoute("90", goodbye, name="goodbye", title="Ring off",
              keywords=("BYE", "OFF")),
    PageRoute("91", guide, name="help", title="How to get about",
              keywords=("HELP",)),
    PageRoute("95", pictures, name="pictures", title="What the pictures mean",
              detail="every symbol, and its words",
              keywords=("PICTURES", "SYMBOLS", "KEY")),
    #  Three the framework builds, mapped into this service's numbering. Each
    #  is generated from what the framework already knows, so none of them can
    #  drift from the service it describes.
    PageRoute("92", history, name="history", title="Where you have been",
              detail="this call, newest first", keywords=("HISTORY",)),
    PageRoute("93", contents, name="contents", title="Every page",
              detail="and the number that fetches it", keywords=("PAGES",)),
    PageRoute("94", keywords, name="names", title="Words you can key",
              detail="instead of a page number", keywords=("KEYWORDS", "WORDS")),
)


def build_application(
    *,
    source: ForecastSource,
    index_filepath: Path = DEFAULT_INDEX_FILEPATH,
) -> Sextile:
    """The service, assembled.

    Everything it is arrives in one call: what it holds, what field shapes its
    numbering needs, what wraps every page, and the pages themselves. There is
    no "before" and no "after", which is what stops registration order being
    something a service can get wrong.
    """

    @asynccontextmanager
    async def lifespan(app: Sextile) -> AsyncIterator[Mapping[str, object]]:
        """What the service holds while it is up, opened and closed in one place.

        The index is an ordinary local held across the yield, which is the
        advantage of a context manager over a pair of handlers: there is
        nowhere for the opening and the closing to drift apart, and nothing has
        to be hoisted anywhere for both to see.
        """
        index = await asyncio.to_thread(Index.open, index_filepath)
        #  Refused rather than warned about. A stale index does not fail, it
        #  answers -- by rules the code stopped using, with nothing on the
        #  screen to say so. A service that will not start says exactly what to
        #  run; one that starts and lies costs somebody an afternoon.
        if index.stale:
            await asyncio.to_thread(index.close)
            raise StaleIndexError(
                f"{index_filepath} was built by older rules and would answer by "
                f"them. Run `weather-viewdata import-places --index "
                f"{index_filepath}` to rebuild it."
            )
        try:
            yield {PLACES: index, FORECASTS: source}
        finally:
            await asyncio.to_thread(index.close)
            await source.aclose()

    app = Sextile(
        name=SERVICE_NAME.title(),
        #  A caller arrives on the title frame once and is never sent back to
        #  it; `0` means the main menu from everywhere else.
        home="0",
        index="1",
        converters={"latitude": LATITUDE, "longitude": LONGITUDE},
        pages=PAGES,
        #  A forecast page goes to the network, so how long one took to build
        #  is the question this service will actually be asked. At 1200 baud
        #  the wire and the page are indistinguishable from the reader's end.
        middleware=[log_pages()],
        lifespan=lifespan,
    )

    @app.on_unresolved
    def find_a_place(target: str) -> PageAddress | None:
        """Letters the numbering does not know are a place to look for.

        This is what makes `*YORK#` work before there is any such thing as a
        search *page*. Only the best match, a page number being one
        destination; where several places share a name the reader gets the
        likeliest, and the search page is where the other two will be offered.
        """
        if target.isdigit():
            return None
        found = _places(app.service).matching(target, limit=1)
        return app.address_for("place", geoname_id=found[0].geoname_id) if found else None

    return app


def _forecasts(service: Mapping[str, object]) -> ForecastSource:
    source = service.get(FORECASTS)
    if not isinstance(source, ForecastSource):
        raise RuntimeError("the forecast source is not open")
    return source


# -- drawing a forecast ------------------------------------------------------


def _forecast_page(
    app: Sextile,
    address: PageAddress,
    place: Place,
    forecast: Forecast | None,
    *,
    near: "Nearby | None" = None,
) -> Page:
    """One place's weather, dealt into frames.

    A page with nothing to show says why. An empty table would read as calm
    weather, which is the one wrong answer a weather service must not give.
    """
    if forecast is None or not forecast.moments:
        return Prose.of(
            f"No forecast for {place.name} just now.",
            "The Norwegian Meteorological Institute did not answer. This is our "
            "trouble rather than yours.",
            f"Key {keyed(address)} again in a few minutes.",
            title=_heading(place),
            home=app.index,
        ).build(address)
    return ForecastTable(
        title=_heading(place),
        entries=list(forecast.moments),
        home=app.index,
        preamble=_preamble(place, forecast, near),
        #  On every frame: a reader on frame c looking at four columns of
        #  figures has no way back to the words that say what they are.
        headings=_HEADINGS,
        zone=_zone_of(place),
    ).build(address)


class ForecastTable(Template[Moment]):
    """A run of hours, one to a row.

    A fourth template shape, which is what the framework asked for rather than
    a fifth copy of the six steps. Nothing on it is selectable: a forecast is
    something to read, not a menu, so no digit is spent on the rows and 1-9 do
    nothing here -- which is the rule about naming only the keys that work,
    rather than an exception to it.
    """

    rows_per_entry = 1
    numbered = False

    def __init__(self, *, zone: ZoneInfo | None = None, **wanted: object) -> None:
        super().__init__(**wanted)  # type: ignore[arg-type]
        self.zone = zone

    def draw(self, row: RowWriter, entry: Moment, digit: str | None) -> None:
        del digit  # a forecast numbers nothing
        row.text(f"{entry.at:%H:%M}", Colour.YELLOW)
        row.text(f" {_local(entry.at, self.zone)}", Colour.CYAN)
        #  Temperature and wind in one write, so the row pays for one colour
        #  attribute rather than two. An attribute is a cell here.
        row.text(
            f"{_reading(entry.temperature, 1):>6}{_reading(entry.wind_speed, 1):>5}",
            Colour.WHITE,
        )
        #  Whatever is left, which the longest symbol met.no has does not fit
        #  into: `heavy sleet shwrs+thunder` is twenty-five cells. Shortened
        #  rather than allowed to overrun, and the reader keeps the half of it
        #  that matters.
        room = row.remaining - _COLOUR_CELL
        row.text(fitted(in_words(entry.symbol), room), Colour.GREEN)


def _heading(place: Place) -> str:
    return fitted(place.name.upper(), COLUMNS - 12)


def _preamble(
    place: Place, forecast: Forecast, near: "Nearby | None"
) -> Sequence[PreambleLine]:
    """Where this is, which clocks it keeps, how old it is, and the weather now.

    The issue time is worth a row of twenty. met.no runs its models a few times
    a day, so a forecast fetched at nine may have been made at five -- and a
    reader on a slow line deciding whether to ask again wants to know which.

    Then a blank row, and the weather the reader is standing in. It was the
    first row of a table of eighty-six before this, which is to say it was
    indistinguishable from the hour after it.
    """
    lines: list[PreambleLine] = [
        _where(place, near),
        _clocks(place),
        f"Issued {forecast.updated_at:%H:%M} UTC",
    ]
    now = forecast.current(datetime.now(UTC))
    if now is not None:
        lines.append("")
        lines += _now_lines(now, _zone_of(place))
    return lines


def _now_lines(moment: Moment, zone: ZoneInfo | None) -> list[PreambleLine]:
    """The weather now, in two rows.

    The clocks carry no `UTC` and no `CEST`: the row above has just said which
    clocks the page keeps, and the colours say it again -- yellow for UTC, cyan
    for the place's own -- so the four cells go on the weather instead.

    **The times shown are the moment's own, not the reader's.** A forecast is
    held for as long as met.no asks it to be, so the hour a reader is standing
    in may have begun forty minutes ago; saying 10:00 at 10:47 lets them see
    that for themselves, where saying 10:47 would claim a reading we have not
    got.

    The weather goes last on its row deliberately. Runs are trimmed to what is
    left, so the longest symbol met.no has -- `heavy sleet shwrs+thunder`, at
    twenty-five cells -- costs the end of itself rather than the frame.
    """
    clocks = [Run("NOW", Colour.WHITE), Run(f"  {moment.at:%H:%M}", Colour.YELLOW)]
    if zone is not None:
        clocks.append(Run(f"  {_local(moment.at, zone)}", Colour.CYAN))
    clocks.append(Run(f"  {in_words(moment.symbol)}", Colour.GREEN))
    return [clocks, [Run("   ".join(_figures(moment)), Colour.WHITE)]]


def _figures(moment: Moment) -> list[str]:
    """Temperature, wind and rain, leaving out what there is no reading for.

    Left out rather than dashed, which is what the table below does. A dash in
    a column means the column is still there to be read; here there are no
    columns, and three words with a gap where the fourth was reads as a gap.
    """
    figures = [f"{_reading(moment.temperature, 1)}C"]
    speed = f"{_reading(moment.wind_speed, 1)}m/s"
    bearing = from_the(moment.wind_from)
    figures.append(f"{bearing} {speed}" if bearing else speed)
    if moment.precipitation is not None:
        figures.append(f"{moment.precipitation:.1f}mm{_over(moment.covers)}")
    return figures


def _over(covers: timedelta | None) -> str:
    """What period a rainfall figure is for.

    1.7mm in an hour and 1.7mm over six are different weather, and the figure
    alone cannot tell them apart. Said as `/h` rather than `/1h` because that is
    how a rate is written and it saves a cell.
    """
    if covers is None:
        return ""
    hours = round(covers.total_seconds() / _SECONDS_AN_HOUR)
    return "/h" if hours == 1 else f"/{hours}h"


def _where(place: Place, near: "Nearby | None") -> str:
    """The position, and for a point the nearest place we know of.

    A coordinate page cannot claim to be a town, so it says what it is -- a
    position -- and names the nearest place only as a landmark.
    """
    position = f"{_degrees(place.latitude, 'NS')} {_degrees(place.longitude, 'EW')}"
    if place.elevation is not None:
        position += f"  {place.elevation}m"
    if near is not None:
        #  With the distance, because the nearest place may be ninety
        #  kilometres away and "near" would then be a polite lie.
        return fitted(
            f"{position}  {near.kilometres:.0f}km from {near.place.name}",
            COLUMNS - 1,
        )
    return fitted(f"{place.country}  {position}", COLUMNS - 1)


def _clocks(place: Place) -> str:
    """Which clocks the rows keep, said once rather than in every row."""
    zone = _zone_of(place)
    if zone is None:
        return "Times UTC"
    sample = datetime.now(UTC).astimezone(zone)
    named = sample.tzname() or ""
    offset = sample.utcoffset()
    hours = "" if offset is None else f"{offset.total_seconds() / 3600:+g}"
    #  Not every zone has letters -- Fiji reports "+12" -- so the abbreviation
    #  is only shown where it is one.
    if named and not named.startswith(("+", "-")):
        return fitted(f"Times UTC and {named} (UTC{hours})", COLUMNS - 1)
    return fitted(f"Times UTC and local (UTC{hours})", COLUMNS - 1)


def _degrees(value: float, poles: str) -> str:
    return f"{abs(value):.1f}{poles[0] if value >= 0 else poles[1]}"


def _local(at: datetime, zone: ZoneInfo | None) -> str:
    return "  -  " if zone is None else f"{at.astimezone(zone):%H:%M}"


def _reading(value: float | None, places: int) -> str:
    """A number, or a dash where there is no reading.

    Not nought. Nought degrees is weather and no reading is not, and a service
    that confuses them is worse than one that says less.
    """
    return "-" if value is None else f"{value:.{places}f}"


def _zone_of(place: Place) -> ZoneInfo | None:
    try:
        return ZoneInfo(place.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        #  A zone the system database has not heard of. Times go in UTC and the
        #  page says so, which is better than being an hour wrong in silence.
        return None


def _point_place(lat: float, lon: float, near: "Nearby | None") -> Place:
    """A position, dressed as somewhere a forecast can be asked for.

    It borrows a clock from the nearest known place, because timezone borders
    follow habitation and there is no other way to know one from coordinates
    alone. It borrows no altitude: the nearest town may be a fjord beneath a
    mountain, and met.no's own topography is a better guess than that.
    """
    return Place(
        geoname_id=0,
        name=f"{_degrees(lat, 'NS')} {_degrees(lon, 'EW')}",
        ascii_name="",
        alternate_names=(),
        latitude=lat,
        longitude=lon,
        feature_class="",
        feature_code="",
        country="",
        admin1="",
        population=0,
        elevation=None,
        timezone=near.place.timezone if near is not None else "UTC",
    )


__all__ = ["SERVICE_NAME", "ForecastTable", "build_application"]
