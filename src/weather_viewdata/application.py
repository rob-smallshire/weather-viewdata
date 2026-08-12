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
from collections import Counter
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
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
from sextile.guidance import Key
from sextile.middleware import held_in, log_pages, record_visits
from sextile.templates import (
    CHOICES_PER_FRAME,
    HOME_KEY,
    Block,
    Entry,
    Menu,
    MenuItem,
    PreambleLine,
    Prose,
    Shortcut,
    Template,
)
from sextile.viewdata.canvas import Canvas, RowWriter, Run
from sextile.viewdata.chrome import CONTENT_FIRST_ROW, CONTENT_ROWS, draw_chrome
from sextile.viewdata.controls import Colour, Control
from sextile.viewdata.drawing import centred
from sextile.viewdata.encoding import cell_count, fitted
from sextile.viewdata.footer import ROOM, FooterItem, Priority, render_footer
from sextile.viewdata.frame import COLUMNS
from sextile.viewdata.wrapping import wrap_within
from sextile.visits import KEPT, SqliteVisits, Visit, Visits
from weather_viewdata.coordinates import LATITUDE, LONGITUDE
from weather_viewdata.days import HEADINGS, PICTURE_ROWS, Day, days_of, draw_day
from weather_viewdata.forecast.model import Forecast, Moment
from weather_viewdata.forecast.source import ForecastSource
from weather_viewdata.geonames import Place
from weather_viewdata.hours import (
    HOURS_SHOWN,
    LABEL_CELLS,
    STRIP_ROWS,
    draw_strip,
)
from weather_viewdata.icons import BANDS, COLUMN_CELLS, icon_for
from weather_viewdata.icons import draw as draw_icon
from weather_viewdata.store import Index, Nearby
from weather_viewdata.symbols import PUBLISHED, in_full, in_words
from weather_viewdata.wind import from_the

SERVICE_NAME: Final = "WEATHER"

#: The key that goes back to the search a reader came through. `F` for find,
#: which is what the page it leads to is called; `S` for search would have been
#: the obvious letter and is the framework's key for paging down.
FIND_KEY: Final = "F"

DEFAULT_INDEX_FILEPATH: Final = Path("places.sqlite")

#: Where the log of what has been read is kept. A file of its own, beside the
#: place index rather than in it: the index is derived and `import-places`
#: rebuilds it wholesale, where this is the only copy of what it holds.
DEFAULT_VISITS_FILEPATH: Final = Path("visits.sqlite")

#: What the log is held under, in what the service holds.
VISITS: Final = "visits"


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

#: The namespace of forecasts by name, which is what the page of places lately
#: looked up asks the log for. A prefix is a namespace here, which is what a
#: first digit already means.
_FORECASTS_PREFIX: Final = f"3{_FORECAST}{TABLE}"

#: Rows the weather-now block takes: the picture is three cells tall and the
#: words beside it are two, so the first of the three is the picture's top band
#: and nothing else.
NOW_ROWS: Final = BANDS

#: What an attribute costs, where the cost has to be counted before the writing
#: rather than charged during it.
_ATTRIBUTE_CELL: Final = 1

#: Seconds an hour, for saying what period a rainfall figure covers, and an
#: hour itself for the moment at the end of a forecast, which carries no period
#: of its own because there is no next moment inside it.
_SECONDS_AN_HOUR: Final = 3600
_AN_HOUR: Final = timedelta(hours=1)

#: What separates the two ends of a range. A bar the full width of the cell,
#: which G0 keeps at 0x60 where ASCII has its backtick, rather than the hyphen
#: at 0x2D -- read out of Beebium's font. Not the underscore, whatever a
#: teletext editor's keyboard suggests: 0x5F is the hash.
_TO: Final = "―"

#: A cell for the colour the weather is written in. What is left after the
#: clocks, the temperature and the wind is the weather's -- counted from the
#: row rather than worked out here, an attribute costing a cell and
#: hand-arithmetic about that having been wrong the first time.
_COLOUR_CELL: Final = 1

#: Where the field and its suggestions sit on the search page.
FIELD_ROW: Final = CONTENT_FIRST_ROW + 2
FIRST_SUGGESTION_ROW: Final = FIELD_ROW + 2

#: How many suggestions the list shows, and the most it will ever show. Three
#: is the measured number -- a fourth row costs a keystroke more than it is
#: worth on a 1200 baud line -- and is right for the ordinary case, where the
#: three are three different places and the reader is choosing between them.
#:
#: It is wrong for one case. Search for Wellington and the three are all called
#: Wellington, and there is nothing to say whether there are four of them or
#: nine, nor any way to reach the rest. So where the likeliest name is shared
#: by more than three places, the list grows to what a single keypress can
#: choose from.
MANY_SUGGESTIONS: Final = CHOICES_PER_FRAME
_SHARING_A_NAME: Final = 3

#: The last content row, where the count of places held sits. At the foot
#: rather than under the list: it is a thing to read once and never again,
#: and the rows it was taking are the ones a long list needs.
PLACES_HELD_ROW: Final = CONTENT_FIRST_ROW + CONTENT_ROWS - 1

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

#: The legend page's grid: two symbols to a row, each with its words beside it.
#: Half a row apiece, less the drawing and the attribute that colours the
#: words, and one more cell so the two halves do not touch.
_SYMBOLS_ACROSS: Final = 2
_SYMBOL_CELLS: Final = COLUMNS // _SYMBOLS_ACROSS
_WORD_CELLS: Final = _SYMBOL_CELLS - COLUMN_CELLS - 2


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
            #  The legend is on the menu because a page of symbols a reader
            #  cannot read is a page of symbols they will not trust, and this
            #  is the only place that says what they mean. It sits under the
            #  two forecasts, which are what a reader came for and what the
            #  symbols are drawn on.
            for name in (
                "by_name",
                "by_position",
                "symbols",
                "help",
                "about",
                "goodbye",
            )
        ],
        home=app.index,
        preamble=["Forecasts for anywhere on earth."],
    ).build(request.address)


async def by_name(request: PageRequest) -> Page:
    """A field, with the best three places beneath it as the reader types.

    **The field is empty every time the page is fetched.** It used to be kept
    in the session and to survive leaving the page and coming back, on the
    argument that a reader looking at one of three candidates would want the
    word still there to refine. Used, it turns out the other way round: a
    reader who has just read a forecast is looking for somewhere *else*, and
    what the kept word costs them is ten presses of the rub-out key, each one a
    round trip and a redraw at 1200 baud.

    Nothing is lost by forgetting. The typing itself does not go through here
    -- a form answers a keypress by redrawing, without the page being fetched
    again -- and a reader who did want the same search back has `*0#` and the
    history page, which is what a history is for.
    """
    app = _service(request)
    form = _field(app, _places(request.service))

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
                #  A range rather than a count, as it always was: with one
                #  match on offer `1-3` already named two keys that did
                #  nothing, and the list numbers itself where a reader is
                #  looking anyway.
                FooterItem("1-9", "choose one", Priority.PRIMARY),
                FooterItem(HOME_KEY, "menu", Priority.ESSENTIAL),
            ],
            ROOM,
        ),
    )
    canvas.row(CONTENT_FIRST_ROW).text("Key a place name.", Colour.WHITE)
    draw_form(canvas.frame, form)
    #  There were two lines of advice here and neither earned its rows.
    #
    #  "Key a name as it is shown here" was not actionable: nothing is shown
    #  until the reader types, and by then they have found what they wanted.
    #  What it was trying to say is true and needs no saying -- a reader never
    #  sees the o-slash in Tromso, because the screen cannot draw it either, so
    #  they never wonder how to key it. Both folds are the same fold.
    #
    #  "Spaces do not matter" was true of the index and not of the field: a
    #  space typed into it left the cursor a cell behind, because a space over
    #  a blank changes nothing and the repaint had nothing to send. That is
    #  fixed in the framework rather than warned about here.
    canvas.row(PLACES_HELD_ROW).text(
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
        #  Asked for the long list every time and cut to the short one, which
        #  costs nothing worth counting -- a range scan already ordered, nine
        #  rows instead of three -- and is what lets the count of homographs be
        #  known before the list is drawn.
        found = await asyncio.to_thread(places.matching, typed, MANY_SUGGESTIONS)
        shown = found[: _how_many(found)]
        return [
            MenuItem(
                text=place.name,
                detail=detail,
                destination=app.address_for("place", geoname_id=place.geoname_id),
            )
            for place, detail in zip(shown, _details(shown), strict=True)
        ]

    return Suggest(
        look_up=look_up,
        field_row=FIELD_ROW,
        first_row=FIRST_SUGGESTION_ROW,
        label="PLACE:",
        limit=MANY_SUGGESTIONS,
        empty="No place of that name is held.",
    )


def _details(found: Sequence[Place]) -> list[str]:
    """What goes beside each name: the country, and where that is not enough.

    Five of the nine Wellingtons are in the United States, so a column of `US`
    tells a reader which four to rule out and nothing about the other five. The
    division within the country is what separates them, and GeoNames has it:
    `admin1` is the state code in the US and the home nation in the United
    Kingdom -- `FL`, `KS`, `CO`, `OH`, `TX`, `ENG` -- which are the letters
    somebody looking for Wellington, Ohio already has in mind.

    **Only where it is needed.** A column that appeared on every row would be a
    column of numbers in most countries, `admin1` being a code rather than a
    name outside the few that use letters; and the room it takes is room the
    name has. So it is added to the entries that would otherwise read alike and
    to no others, which leaves the ordinary list exactly as it was.
    """
    alike = Counter((place.name, place.country) for place in found)
    return [
        f"{place.country} {place.admin1}".rstrip()
        if alike[(place.name, place.country)] > 1
        else place.country
        for place in found
    ]


def _how_many(found: Sequence[Place]) -> int:
    """How many suggestions to offer: three, or as many as a digit can choose.

    Three is right when the three are three different places. It is wrong when
    they are three Wellingtons, because then it says nothing about whether
    there is a fourth and offers no way to reach one. So the list grows when
    the likeliest name is shared -- by the top one and more than two besides.

    Counted over what came back rather than asked of the index, since the
    ranking has already put the places of that name together at the top: they
    match the query exactly and nothing else can outrank all of them.
    """
    if not found:
        return SUGGESTIONS
    sharing = sum(1 for place in found if place.name == found[0].name)
    return MANY_SUGGESTIONS if sharing > _SHARING_A_NAME else SUGGESTIONS


async def by_position(request: PageRequest) -> Page:
    """Two fields, for anywhere on earth whether anybody lives there or not.

    `0` is not the way out here and the footer does not pretend otherwise: on
    a page where digits are data, a `0` that went to the menu would be a key
    that ate a coordinate.

    **Both fields are empty every time the page is fetched**, as the search
    field is and for the same reason. This one looked like the exception --
    two figures are more trouble to type than a name, and a reader nudging a
    latitude would want the old one there -- and it is not: a reader comes back
    here to look at somewhere *else*, and what a remembered position costs them
    is twelve presses of the rub-out key across two fields. Nudging is what the
    arrows and a fresh six characters are for.
    """
    app = _service(request)
    form = _position_fields(app, _places(request.service))

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
        return fitted(_landmark(found), COLUMNS - 1)

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
        _service(request),
        request.address,
        found,
        await source.forecast_for(found),
        back_to=_searched_from(request),
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
        back_to=_searched_from(request),
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


async def lately(request: PageRequest) -> Page:
    """The places other readers have looked up, newest first.

    The framework has a page of what has been read lately and this is not it.
    That one is a list of *pages*, named as the service names them -- `One
    place`, nine times over -- because a page number is all a framework can
    know. This one asks the index what the numbers mean, so the reader sees
    Trondheim and Wellington and can tell one row from another.

    Points are left off rather than shown as coordinates. A position is a page
    and not a place: nobody looking at a list of somewhere-elses wants
    `59.7N 10.0E`, and the reader who keyed it has it in their own history.
    """
    app = _service(request)
    visits = _visits(request.service)
    if visits is None:
        return _nothing_kept(app, request.address)
    seen = await visits.recent(CHOICES_PER_FRAME, prefix=_FORECASTS_PREFIX)
    return Menu(
        title=app.describe(request.address).upper(),
        entries=[
            MenuItem(text=place.name, detail=place.country, destination=visit.page)
            for visit, place in await _places_of(app, request.service, seen)
        ],
        home=app.index,
        preamble=["Places lately looked up here."],
        empty="Nobody has looked anything up yet.",
    ).build(request.address)


async def _places_of(
    app: Sextile, service: Mapping[str, object], seen: Sequence[Visit]
) -> list[tuple[Visit, Place]]:
    """What each visited page number was a forecast *of*.

    The router is asked, rather than the digits being taken apart here: it is
    what turned the number into a place when the page was served, and a second
    reading of the same number is a second thing to get wrong when the
    numbering changes.
    """
    index = _places(service)
    found = []
    for visit in seen:
        meant = app.params_for(visit.page)
        geoname_id = meant.get("geoname_id") if meant is not None else None
        if not isinstance(geoname_id, int):
            continue
        place = await asyncio.to_thread(index.place, geoname_id)
        if place is not None:
            found.append((visit, place))
    return found


def _visits(service: Mapping[str, object]) -> Visits | None:
    """The log, if this service was given one."""
    held = service.get(VISITS)
    return held if isinstance(held, Visits) else None


def _nothing_kept(app: Sextile, address: PageAddress) -> Page:
    return Prose.of(
        "This service is not keeping a log of what has been looked up.",
        title=app.describe(address).upper(),
        home=app.index,
    ).build(address)


async def guide(request: PageRequest) -> Page:
    """How to get about, which is mostly the framework's to say.

    The keys this service adds are the two a reader meets nowhere else: the
    letters that go into a search field, and the one that takes them back to
    the search they came through. Everything else on the page -- the digits,
    the way home, the shape of a request, the compass -- is the framework's,
    generated from what it actually answers rather than described here.
    """
    app = _service(request)
    return await app.guide(
        request,
        #  No `A` and `D` on the compass. They step through the run of pages a
        #  menu offered, and this service does not wire them: a forecast is
        #  reached from a suggestion list rather than from a menu, and there is
        #  no run of them to step through. Two keys that did nothing were being
        #  drawn on the one page a reader goes to to find out what the keys do.
        items=False,
        moving=[
            Key("A-Z", "type into a search field"),
            Key(FIND_KEY, "back to your search"),
        ],
        #  In the order of the numbers, which is the order a reader reads a
        #  column of numbers in. Grouped by subject it was `95` before `93`,
        #  and a list of page numbers out of order reads as a mistake whatever
        #  the grouping was for.
        asking=[
            Key(keyed(app.address_for("goodbye")), "log off"),
            Key(),
            Key(keyed(app.address_for("contents")), "every page and its number"),
            Key(keyed(app.address_for("names")), "every word you can key"),
            Key(keyed(app.address_for("symbols")), "what the symbols mean"),
        ],
    )


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
_SKIES: Final = (
    ("clearsky_night", "clear sky at night"),
    ("clearsky_polartwilight", "clear sky in polar twilight"),
    ("rainshowers_night", "rain showers at night"),
    ("rainshowers_polartwilight", "rain showers in polar twilight"),
)


async def symbols(request: PageRequest) -> Page:
    """Every symbol the service draws, beside the words for it.

    The set, as met.no publishes it, in their order. Which is the only way to
    judge a set of symbols: one at a time they all look plausible, and side by
    side the two that cannot be told apart show up at once.

    The set is drawn by day, and the four sky variants follow it: a moon at
    night and a sun on the horizon in the polar twilight, on a clear sky and on
    a shower, which is the whole of what the time of day changes. Forty more
    drawings would say the same thing four times over.

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
            [Shown(code, in_full(code)) for code in PUBLISHED]
            + [Shown(code, words) for code, words in _SKIES]
        ),
        home=app.index,
        preamble=["Drawn by day, except where it says."],
    ).build(request.address)


def _in_pairs(shown: Sequence[Shown]) -> list[tuple[Shown, ...]]:
    """Two to a row, because a picture and its words are half a row wide."""
    return [
        tuple(shown[at : at + _SYMBOLS_ACROSS])
        for at in range(0, len(shown), _SYMBOLS_ACROSS)
    ]


class SymbolTable(Template[tuple[Shown, ...]]):
    """Pictures with their words, two to a row and four rows to each.

    Everything is drawn from `draw_entry` rather than from `draw`, because a
    mosaic picture is placed by cell and is three rows tall: a row writer walks
    one row from left to right, which is the wrong shape for this and the right
    shape for everything else.
    """

    #  A blank row after each, or the bottom band of one picture and the top
    #  band of the next read as one picture: they are three rows apart, in the
    #  same colours, and nothing between them says where one ends. The strip on
    #  a forecast page has no such trouble, its symbols being side by side.
    rows_per_entry = BANDS + 1
    numbered = False

    def draw(
        self, row: RowWriter, entry: tuple[Shown, ...], digit: str | None
    ) -> None:
        """Nothing. This shape draws from `draw_entry`; see the class docstring."""

    def draw_entry(
        self, canvas: Canvas, row: int, entry: tuple[Shown, ...], digit: str | None
    ) -> None:
        del digit  # a legend numbers nothing
        for slot, shown in enumerate(entry):
            column = slot * _SYMBOL_CELLS
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
    #  `Ring off` here and `Log off` on the menu, which are two different
    #  jobs: the menu names an action, and Prestel called that logging off,
    #  where this is an instruction to somebody holding a handset. Dated
    #  British rather than an Americanism -- the American is "hang up" -- and
    #  the register the rest of the service is written in.
    canvas.row(4).text("Ring off.", Colour.WHITE)
    return Page(frames=(PageFrame(frame=canvas.frame),), hang_up=True)


async def history(request: PageRequest) -> Page:
    return await _service(request).history(request)


async def contents(request: PageRequest) -> Page:
    return await _service(request).contents(request)


async def read_lately(request: PageRequest) -> Page:
    """The framework's page, at this service's number."""
    app = _service(request)
    visits = _visits(request.service)
    if visits is None:
        return _nothing_kept(app, request.address)
    return await app.lately_read(request, visits)


async def read_most(request: PageRequest) -> Page:
    """The framework's page, at this service's number."""
    app = _service(request)
    visits = _visits(request.service)
    if visits is None:
        return _nothing_kept(app, request.address)
    return await app.most_read(request, visits)


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
    #  No detail on either of the two searches. They were the only entries on
    #  the menu that had one, so the green line under them broke the rhythm of
    #  the five rather than helping any of them -- and a title that says what
    #  the page is for needs no gloss.
    PageRoute("3", by_name, name="by_name", title="Forecast by placename",
              keywords=("FIND", "PLACE", "SEARCH")),
    PageRoute(f"3{_FORECAST}{TABLE}{{geoname_id:int}}", place, name="place",
              title="One place"),
    PageRoute("4", by_position, name="by_position",
              title="Forecast by lat/lon position",
              keywords=("POSITION", "COORDS")),
    PageRoute(f"4{_FORECAST}{TABLE}{{lat:latitude}}{{lon:longitude}}", point,
              name="point", title="One point"),
    PageRoute("2", lately, name="lately", title="Lately looked up",
              keywords=("LATELY", "RECENT")),
    PageRoute("9", about, name="about", title="About this service",
              keywords=("ABOUT",)),
    PageRoute("90", goodbye, name="goodbye", title="Log off",
              keywords=("BYE", "OFF")),
    PageRoute("91", guide, name="help", title="How to get about",
              keywords=("HELP",)),
    PageRoute("96", read_lately, name="read_lately", title="Pages lately read",
              keywords=("READ",)),
    PageRoute("97", read_most, name="read_most", title="Pages read most",
              keywords=("POPULAR",)),
    PageRoute("95", symbols, name="symbols", title="What the symbols mean",
              #  `LEGEND` among them, which is the word for this on a map and
              #  in met.no's own files. It is not the title, because a page
              #  whose whole purpose is explaining should not have a name that
              #  wants explaining -- but a reader who reaches for the word
              #  should find the page.
              #
              #  Not `PICTURES`, which this page answered to for a while: a
              #  keyword is a name in a namespace of one, and holding a good
              #  word against a page that has stopped needing it is how the
              #  namespace fills up.
              keywords=("SYMBOLS", "KEY", "LEGEND")),
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
    visits_filepath: Path = DEFAULT_VISITS_FILEPATH,
    kept: timedelta = KEPT,
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
        visits = await asyncio.to_thread(
            SqliteVisits.open, visits_filepath, kept=kept
        )
        try:
            yield {PLACES: index, FORECASTS: source, VISITS: visits}
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
        #  One writes to the machine's log, for whoever runs the service; the
        #  other to a log the service reads back, for whoever reads it.
        middleware=[log_pages(), record_visits(held_in(VISITS))],
        lifespan=lifespan,
    )

    #  `*YORK#` used to be a search: a word the numbering did not know was
    #  offered to the place index, and the best match was where it went. It is
    #  gone, and both reasons are worth keeping.
    #
    #  It shared a namespace it could not share. `*HISTORY#` is a page and
    #  `*YORK#` was a place, and nothing about either says which it will be --
    #  so a reader could not tell what a word between the star and the hash was
    #  going to do until it had done it, and a place called Pages or Words
    #  could not be found at all.
    #
    #  And it answered a question with one answer where there are many. There
    #  are dozens of Yorks; the index picked the likeliest and said nothing
    #  about the others. `*3#` shows three and lets the reader choose, which is
    #  what the search page is for and why it was built.
    return app


def _forecasts(service: Mapping[str, object]) -> ForecastSource:
    source = service.get(FORECASTS)
    if not isinstance(source, ForecastSource):
        raise RuntimeError("the forecast source is not open")
    return source


# -- drawing a forecast ------------------------------------------------------


def _searched_from(request: PageRequest) -> PageAddress:
    """The search page this reader came through, or the likelier of the two.

    Looked for in the history rather than remembered in the session, because
    the history is what the reader would use to get back by hand and this is
    only a shorter way of doing the same thing. Newest first, since a reader
    who has used both wants the one they used last.

    A reader who keyed the page number, or arrived by a keyword, went through
    no search at all -- and is offered the one they would most likely have used,
    a name being how nearly everybody looks for weather.
    """
    app = _service(request)
    searches = {app.address_for("by_name"), app.address_for("by_position")}
    for been in reversed(request.history):
        if been in searches:
            return been
    return app.address_for("by_name")


def _forecast_page(
    app: Sextile,
    address: PageAddress,
    place: Place,
    forecast: Forecast | None,
    *,
    near: "Nearby | None" = None,
    back_to: PageAddress | None = None,
) -> Page:
    """One place's weather, dealt into frames.

    A page with nothing to show says why. An empty table would read as calm
    weather, which is the one wrong answer a weather service must not give.
    """
    #  Offered on the page that says there is no forecast as well as on the one
    #  that has it: a reader told to come back in a few minutes is a reader
    #  who may prefer to go and look somewhere else instead.
    shortcuts = () if back_to is None else (Shortcut(FIND_KEY, back_to, "find"),)
    if forecast is None or not forecast.moments:
        return Prose.of(
            f"No forecast for {place.name} just now.",
            "The Norwegian Meteorological Institute did not answer. This is our "
            "trouble rather than yours.",
            f"Key {keyed(address)} again in a few minutes.",
            title=_heading(place),
            home=app.index,
            shortcuts=shortcuts,
        ).build(address)
    zone = _zone_of(place)
    now = forecast.current(datetime.now(UTC))
    #  The strip shows the hours after now; the days show all of them, today
    #  included. They are not one forecast said twice: the first is what this
    #  afternoon will do, the second which day to go out on.
    coming = [moment for moment in forecast.moments if now is None or moment.at > now.at]
    return ForecastTable(
        title=_heading(place),
        entries=days_of(forecast.moments, zone, from_day=_today(zone)),
        home=app.index,
        #  Not `S`, which pages down, and not `0`, which is the index. A reader
        #  who has just found a place usually wants the next place, and the way
        #  back to the search is otherwise three keys and a page they have to
        #  remember the number of.
        shortcuts=shortcuts,
        preamble=_preamble(place, forecast, near, coming),
        #  On every frame: a reader on frame c looking at four columns of
        #  figures has no way back to the words that say what they are.
        headings=HEADINGS,
        today=_today(zone),
    ).build(address)


class ForecastTable(Template[Day]):
    """The days ahead, one to a block of four rows.

    Three rows of pictures and a blank, or two days running would read as one
    six-row block. Nothing on it is selectable: a forecast is something to
    read, not a menu, so no digit is spent on the rows and 1-9 do nothing here
    -- which is the rule about naming only the keys that work, rather than an
    exception to it.
    """

    rows_per_entry = PICTURE_ROWS
    separation = 1
    numbered = False

    def __init__(self, *, today: date, **wanted: object) -> None:
        super().__init__(**wanted)  # type: ignore[arg-type]
        self.today = today

    def draw(self, row: RowWriter, entry: Day, digit: str | None) -> None:
        """Nothing. A day is placed by cell; see `draw_entry`."""

    def draw_entry(
        self, canvas: Canvas, row: int, entry: Day, digit: str | None
    ) -> None:
        del digit  # a forecast numbers nothing
        draw_day(canvas, row, entry, self.today)


def _heading(place: Place) -> str:
    return fitted(place.name.upper(), COLUMNS - 12)


def _preamble(
    place: Place,
    forecast: Forecast,
    near: "Nearby | None",
    coming: Sequence[Moment],
) -> Sequence[PreambleLine]:
    """Where this is, which clocks it keeps, how old it is, and the weather now.

    A blank row after the position, and then the weather the reader is standing
    in -- three rows of it, since that is what a picture is tall, with the issue
    time filling the first of them beside the picture's top band.
    """
    lines: list[PreambleLine] = [_where(place, near), ""]
    zone = _zone_of(place)
    now = forecast.current(datetime.now(UTC))
    issued = f"Issued {forecast.updated_at:%H:%M} UTC"
    if now is not None:
        lines.append(
            Block(
                NOW_ROWS,
                lambda canvas, row: _draw_now(canvas, row, now, zone, issued),
            )
        )
    else:
        lines.append(issued)
    if coming:
        #  Drawn rather than written, and the template counts its rows like any
        #  others -- so the strip filling what is left of the frame simply
        #  leaves the table to start on the next one. Its own rules separate it
        #  from what is above and below.
        hours = list(coming[:HOURS_SHOWN])
        clock = _clock_name(zone)
        lines.append(
            Block(
                STRIP_ROWS,
                lambda canvas, row: draw_strip(canvas, row, hours, zone, clock),
            )
        )
    return lines


def _draw_now(
    canvas: Canvas, row: int, moment: Moment, zone: ZoneInfo | None, issued: str
) -> None:
    """The weather now: a picture, and three rows of words beside it.

    Three rows, because the picture is three cells tall. The issue time takes
    the first of them, which was blank when the picture arrived and is a row
    the charts below now want: met.no runs its models a few times a day, so a
    forecast fetched at nine may have been made at five, and a reader on a slow
    line deciding whether to ask again wants to know which.

    **Both clocks on one row, each saying which it is.** They were on separate
    rows -- `Times UTC and CEST (UTC+2)` above `NOW 16:00 18:00` -- and the
    saving is a row and a repetition: put the labels beside the times and the
    times explain the labels, so the offset in brackets is the only part that
    has to be said at all.

    **An hour, said as an hour.** `NOW 16:00` under `Issued 16:29` reads as a
    contradiction and is not one: met.no's series begins at the hour containing
    the model run -- measured, `updated_at` 15:29 with a first moment of 15:00
    -- so a forecast issued at half past can perfectly well tell you about the
    hour that began at the top of it. What was wrong was the word `NOW` beside
    a single time, which promises an instant. `16-17` promises the hour, which
    is what the readings are for and what a reader at 16:45 is standing in.
    """
    room = COLUMNS
    picture = icon_for(moment.symbol)
    if picture is not None:
        draw_icon(canvas, row, COLUMNS - COLUMN_CELLS, picture)
        #  No gap is added: the picture's own attribute cell is a blank one,
        #  and a second would be a cell spent twice on the same air.
        room = COLUMNS - COLUMN_CELLS
    canvas.row(row).text(fitted(issued, room), Colour.WHITE)
    canvas.row(row + 1).runs(_within(_clock_runs(moment, zone, room), room))
    canvas.row(row + 2).runs(_within(_figure_runs(moment), room))


def _clock_runs(moment: Moment, zone: ZoneInfo | None, room: int) -> list[Run]:
    """`NOW 16-17 UTC 18-19 CEST (UTC+2)`, in yellow and cyan.

    One space between the runs rather than two, because each of them already
    begins with an attribute cell that draws as a space. Two would be a gap of
    three, and the offset in brackets is what would pay for it.

    The offset goes only if the whole of it fits. Trimmed, `(UTC+5.75)` becomes
    `(UTC+5.` -- an answer that looks like a fact and is not one -- so it is
    dropped whole where there is no room, the two clocks side by side saying
    the same thing to anyone who cares to subtract.
    """
    runs = [Run("NOW", Colour.WHITE), Run(f" {_span(moment, None)} UTC", Colour.YELLOW)]
    if zone is None:
        return runs
    named, offset = _zone_named(zone)
    local = f" {_span(moment, zone)} {named}".rstrip()
    with_offset = f"{local} (UTC{offset})" if offset else local
    spent = sum(_ATTRIBUTE_CELL + cell_count(run.text) for run in runs)
    fits = spent + _ATTRIBUTE_CELL + cell_count(with_offset) <= room
    runs.append(Run(with_offset if fits else local, Colour.CYAN))
    return runs


def _span(moment: Moment, zone: ZoneInfo | None) -> str:
    """The hours a moment covers, in one clock, as a range.

    Hours alone where the range falls on them, which is everywhere a zone is a
    whole number of hours from UTC. Where it is not -- Kolkata is half an hour
    off and Kathmandu three quarters -- the minutes are shown, and it is the
    offset in brackets that gives way to make room for them.

    **The separator is a long dash and not a hyphen.** G0 has both: 0x2D is the
    hyphen and 0x60 -- where ASCII keeps its backtick -- is a bar the full width
    of the cell, which is what a range wants. Read out of Beebium's font rather
    than guessed. It is *not* the underscore, whatever a teletext editor's
    keyboard suggests: 0x5F is the hash, the viewdata command key.
    """
    ends = moment.at + (moment.covers or _AN_HOUR)
    start = moment.at.astimezone(zone) if zone is not None else moment.at
    finish = ends.astimezone(zone) if zone is not None else ends
    if start.minute or finish.minute:
        return f"{start:%H:%M}{_TO}{finish:%H:%M}"
    return f"{start:%H}{_TO}{finish:%H}"


def _figure_runs(moment: Moment) -> list[Run]:
    """The readings, and what the weather is called, in that order.

    The words go last and take what is left, which on a bad day is not all of
    them -- `heavy sleet shwrs+thunder` is twenty-five cells. That is a cost
    worth paying here and nowhere else: the picture at the end of the row is
    saying the same thing, and a reader who loses the tail of the words has not
    lost the weather.
    """
    return [
        Run(" ".join(_figures(moment)), Colour.WHITE),
        Run(f" {in_words(moment.symbol)}", Colour.GREEN),
    ]


def _within(runs: list[Run], room: int) -> list[Run]:
    """Runs trimmed to a budget, the last of them giving way first.

    `RowWriter.runs` trims to the end of the row, which is the wrong edge where
    something else is drawn further along it.
    """
    kept: list[Run] = []
    used = 0
    for run in runs:
        left = room - used - _ATTRIBUTE_CELL
        if left <= 0:
            break
        text = fitted(run.text, left)
        kept.append(Run(text, run.colour))
        used += _ATTRIBUTE_CELL + cell_count(text)
    return kept


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
        return fitted(f"{position}  {_landmark(near)}", COLUMNS - 1)
    return fitted(f"{place.country}  {position}", COLUMNS - 1)


def _zone_named(zone: ZoneInfo) -> tuple[str, str]:
    """What a place's clock calls itself, and how far it is from UTC.

    Not every zone has letters -- Fiji reports `+12` -- so a name that is only
    an offset is dropped and the offset in brackets does the saying.
    """
    sample = datetime.now(UTC).astimezone(zone)
    named = sample.tzname() or ""
    offset = sample.utcoffset()
    hours = "" if offset is None else f"{offset.total_seconds() / 3600:+g}"
    return ("" if named.startswith(("+", "-")) else named), hours


def _clock_name(zone: ZoneInfo | None) -> str:
    """The four cells the hour strip has for saying which clock it keeps.

    `CEST`, `AEDT`, `NZDT` -- the abbreviations are four characters or fewer
    wherever a zone has one. Where it has not, or has one too long to draw,
    `loc` says the only thing left that is true.
    """
    if zone is None:
        return "UTC"
    named, _ = _zone_named(zone)
    return named if named and len(named) <= LABEL_CELLS else "loc"


def _landmark(near: "Nearby") -> str:
    """The nearest place we know of, as a landmark for a position.

    With the country, because a name on its own is not an answer: there are
    nine Wellingtons, and a reader who keys a position in the wrong hemisphere
    is told which one they have found rather than left to wonder. And with the
    distance, because the nearest place may be ninety kilometres away and
    "near" would then be a polite lie.
    """
    return f"{near.kilometres:.0f}km from {near.place.name}, {near.place.country}"


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


def _today(zone: ZoneInfo | None) -> date:
    """The date it is where the forecast is, which is not always ours."""
    return datetime.now(UTC).astimezone(zone).date()


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
