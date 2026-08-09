"""The weather, as a Viewdata service.

Global, because met.no forecasts anywhere; dialled mostly from Britain, because
that is where the working Beebs are. Those two facts pull against each other
exactly once, in the ranking, and are settled there.

    0                  the title frame
    1                  the main menu
    3                  find a place by name
    32<geoname-id>     one place's forecast
    4                  find a point by position
    42<lat><lon>       one point's forecast
    9  about   90 goodbye   91 help   92/93/94 the framework's pages

Two ways to name a forecast, failing differently. A named place carries a name,
a timezone and an altitude, and depends on GeoNames still holding that record.
A point carries none of those and depends on nothing at all.

The pages are ordinary functions, declared beside one another and given to the
constructor as a list. Nothing closes over anything: a page takes the index
from what the service holds and the numbering from the service itself, both
through the request. That is what lets the whole service be a value, and what
makes the order things were registered in unobservable.
"""

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sextile import Page, PageAddress, PageFrame, PageRequest, PageRoute, Sextile
from sextile.addressing import keyed
from sextile.middleware import log_pages
from sextile.templates import Menu, MenuItem, Prose, Template
from sextile.viewdata.canvas import Canvas, RowWriter
from sextile.viewdata.controls import Colour
from sextile.viewdata.drawing import centred, fitted
from sextile.viewdata.frame import COLUMNS
from weather_viewdata.coordinates import LATITUDE, LONGITUDE
from weather_viewdata.forecast.model import Forecast, Moment
from weather_viewdata.forecast.source import ForecastSource
from weather_viewdata.geonames import Place
from weather_viewdata.store import Index
from weather_viewdata.symbols import in_words

SERVICE_NAME: Final = "WEATHER"

DEFAULT_INDEX_FILEPATH: Final = Path("places.sqlite")

#: A cell for the colour the weather is written in. What is left after the
#: clocks, the temperature and the wind is the weather's -- counted from the
#: row rather than worked out here, an attribute costing a cell and
#: hand-arithmetic about that having been wrong the first time.
_COLOUR_CELL: Final = 1

#: What the place index and the forecast source are held under, in what the
#: service holds. Named constants rather than literals at each use, since a
#: mistyped key is a page that fails at the far end of a telephone line.
PLACES: Final = "places"
FORECASTS: Final = "forecasts"

#: Spaced to the columns `ForecastTable.draw` writes, with the units said once
#: rather than in every row: at forty columns a degree sign in eighty places is
#: a column of forecast nobody can read.
_HEADINGS: Final = "  UTC LOCAL  DEG C  M/S  WEATHER"

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
    app = _service(request)
    return Prose.of(
        "Key the name of a town and this service will find it.",
        "Letters only. There is no space bar and no accent on a viewdata "
        "keypad, so run the words together and leave the accents off: NEWYORK "
        "finds New York, TROMSO finds Tromso, MUNICH finds Munchen.",
        f"{_places(request.service).held():,} places are held: everywhere with "
        "500 inhabitants or more, and every seat of local government whatever "
        "its size.",
        "Where several places share a name, the largest is offered.",
        title=app.describe(request.address).upper(),
        home=app.index,
    ).build(request.address)


async def by_position(request: PageRequest) -> Page:
    app = _service(request)
    return Prose.of(
        "Any point on earth has a page number, whether anybody lives there or "
        "not.",
        "Key 42, then four digits of latitude and four of longitude. Add 90 to "
        "the latitude and 180 to the longitude first, so that neither is "
        "negative, and give each to a tenth of a degree.",
        "York is 54.0 north and 1.1 west. That makes 1440 and 1789, so York is "
        "*42 1440 1789#, without the spaces.",
        "A tenth of a degree is about 11km north to south, and less than that "
        "east to west away from the equator.",
        title=app.describe(request.address).upper(),
        home=app.index,
    ).build(request.address)


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
    PageRoute("32{geoname_id:int}", place, name="place", title="One place"),
    PageRoute("4", by_position, name="by_position",
              title="Find a point by position",
              detail="anywhere, to a tenth of a degree",
              keywords=("POSITION", "COORDS")),
    PageRoute("42{lat:latitude}{lon:longitude}", point, name="point",
              title="One point"),
    PageRoute("9", about, name="about", title="About this service",
              keywords=("ABOUT",)),
    PageRoute("90", goodbye, name="goodbye", title="Ring off",
              keywords=("BYE", "OFF")),
    PageRoute("91", guide, name="help", title="How to get about",
              keywords=("HELP",)),
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
    near: Place | None = None,
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


def _preamble(place: Place, forecast: Forecast, near: Place | None) -> Sequence[str]:
    """What is being forecast, where it is, and how old it is.

    The issue time is worth a row of twenty. met.no runs its models a few times
    a day, so a forecast fetched at nine may have been made at five -- and a
    reader on a slow line deciding whether to ask again wants to know which.
    """
    return [
        _where(place, near),
        _clocks(place),
        f"Issued {forecast.updated_at:%H:%M} UTC",
    ]


def _where(place: Place, near: Place | None) -> str:
    """The position, and for a point the nearest place we know of.

    A coordinate page cannot claim to be a town, so it says what it is -- a
    position -- and names the nearest place only as a landmark.
    """
    position = f"{_degrees(place.latitude, 'NS')} {_degrees(place.longitude, 'EW')}"
    if place.elevation is not None:
        position += f"  {place.elevation}m"
    if near is not None:
        return fitted(f"{position}  near {near.name}", COLUMNS - 1)
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


def _point_place(lat: float, lon: float, near: Place | None) -> Place:
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
        timezone=near.timezone if near is not None else "UTC",
    )


__all__ = ["SERVICE_NAME", "ForecastTable", "build_application"]
