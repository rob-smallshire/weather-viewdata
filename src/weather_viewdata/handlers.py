"""The weather service's page handlers, each declared beside its function.

Ordinary functions, each taking what it needs from the request: the index
from what the service holds, the numbering from the service itself. Nothing
here closes over anything. The `@page` declaration above each function is
everything the service says about it -- where it is in the numbering, what
it is called where it is listed, and the words that reach it -- and the
order the functions are written in is the order the contents page lists
them.

The drawing lives elsewhere: `forecast_page` turns a forecast into frames,
`search` builds the two forms, `legend` draws the symbols page, and
`symbols`, `icons`, `hours` and `days` are the vocabulary those three share.
"""

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Final

from sextile import (
    GuideRow,
    Held,
    Page,
    PageAddress,
    PageRequest,
    Sextile,
    keyed,
    page,
)
from sextile.formatting import Lines, Menu, MenuItem, Prose, farewell_page
from sextile.layout import (
    CHOICES_PER_FRAME,
    HOME_KEY,
    Drawn,
    Flowing,
    Once,
    PageLayout,
    Shortcut,
)
from sextile.viewdata.canvas import Canvas
from sextile.viewdata.controls import Colour
from sextile.viewdata.drawing import centred
from sextile.viewdata.frame import ROWS
from sextile.visits import Visit, Visits
from weather_viewdata.forecast.source import ForecastSource
from weather_viewdata.forecast_page import FIND_KEY, forecast_page, point_place
from weather_viewdata.geonames import Place
from weather_viewdata.legend import SKIES, Shown, SymbolTable, in_pairs
from weather_viewdata.search import position_fields, suggest_field
from weather_viewdata.store import Index
from weather_viewdata.symbols import PUBLISHED, in_full

SERVICE_NAME: Final = "WEATHER"

#: What the log is held under, in what the service holds. `found_in` rather
#: than `of` at each use, because the log is the one thing this service can
#: run without: the pages that read it say so instead of failing.
VISITS: Final[Held[Visits]] = Held.checking("visits", Visits)

#: What the place index and the forecast source are held under, in what the
#: service holds. Keys rather than strings at each use, since a mistyped key
#: is a page that fails at the far end of a telephone line -- and the key
#: carries the type, so each page narrows what it takes in the same call.
PLACES: Final = Held("places", Index)
FORECASTS: Final[Held[ForecastSource]] = Held.checking("forecasts", ForecastSource)

#: What kind of page this is, within a namespace whose root is a search frame.
#: There is only one kind so far; the digit leaves room for another about a
#: place that is not its weather.
_FORECAST: Final = "2"

#: How a forecast is drawn, as the digit that says so. A forecast is one body
#: of numbers with more than one honest presentation: a table reads exactly and
#: a graph reads at a glance, and both are wanted. So the presentation is part
#: of the address rather than a mode the reader has to get the frame into -- a
#: number written down fetches back what was written down, and a reader can key
#: straight to the one they want.
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

#: What "lately" means on the about page, where the count of callers is.
_A_WEEK: Final = timedelta(days=7)


@page("0")
async def title(request: PageRequest) -> Page:
    """The frame the line opens on.

    No page number in the header: `*0#` is the back command, so a number here
    would be an instruction that does not work.
    """
    held = PLACES.of(request.service).held()

    def draw(canvas: Canvas, row: int) -> None:
        centred(canvas, row + 2, SERVICE_NAME, Colour.YELLOW)
        centred(canvas, row + 4, "Forecasts for anywhere on earth", Colour.WHITE)
        centred(canvas, row + 7, "from the Norwegian", Colour.CYAN)
        centred(canvas, row + 8, "Meteorological Institute", Colour.CYAN)
        centred(canvas, row + 11, f"{held:,} places held", Colour.WHITE)
        centred(canvas, row + 14, "Key # to begin", Colour.YELLOW)
        centred(canvas, row + 20, "Weather from met.no, CC BY 4.0", Colour.GREEN)
        centred(canvas, row + 21, "Places from GeoNames, CC BY 4.0", Colour.GREEN)

    return PageLayout(
        #  None at all: a masthead is the whole frame, and a footer offering
        #  keys would be a footer on a page with one key.
        furniture=(),
        #  `follows` is what makes `#` mean something here, and brings the key
        #  that reaches it. Without it the title frame is a dead end under the
        #  one key a viewdata reader tries first.
        follows=request.app.index,
        parts=[Once(Drawn(rows=ROWS, draw=draw))],
    ).build(None)


@page("1", title="Main menu", keywords=("MAIN", "INDEX", "HOME"))
async def main(request: PageRequest) -> Page:
    """The index: the ways in to a forecast, and the legend for reading one."""
    app = request.app
    return PageLayout(
        title=SERVICE_NAME,
        home=app.index,
        parts=[
            Once(Lines(said=("Forecasts for anywhere on earth.", ""))),
            Flowing(
                Menu(
                    entries=[
                        #  The legend is on the menu because a page of symbols
                        #  a reader cannot read is a page of symbols they will
                        #  not trust, and this is the only place that says what
                        #  they mean. It sits under the two forecasts, which
                        #  are what a reader came for and what the symbols are
                        #  drawn on.
                        MenuItem.for_page(app, name)
                        for name in (
                            "by_name",
                            "by_position",
                            "symbols",
                            "help",
                            "about",
                            "goodbye",
                        )
                    ]
                )
            ),
        ],
    ).build(request.address)


#  No detail on either of the two searches. They were the only entries on
#  the menu that had one, so the green line under them broke the rhythm of
#  the five rather than helping any of them -- and a title that says what
#  the page is for needs no gloss.
@page("3", title="Forecast by placename", keywords=("FIND", "PLACE", "SEARCH"))
async def by_name(request: PageRequest) -> Page:
    """A field, with the best three places beneath it as the reader types.

    **The field is empty every time the page is fetched**, not kept in the
    session. A reader who has just read a forecast is looking for somewhere
    else, so a kept word would cost them ten presses of the rub-out key, each a
    round trip and a redraw at 1200 baud.

    Nothing is lost by forgetting. The typing itself does not go through here
    -- a form answers a keypress by redrawing, without the page being fetched
    again -- and a reader who wants the same search back has `*0#` and the
    history page.
    """
    app = request.app
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
    return PageLayout(
        title=app.heading_for(request.address),
        home=Shortcut(key=HOME_KEY, destination=app.index, says="menu"),
        parts=[
            Once(Lines(said=("Key a place name.", ""))),
            Once(suggest_field(app, PLACES.of(request.service))),
            Once(
                Lines(
                    said=("", f"{PLACES.of(request.service).held():,} places held.")
                )
            ),
        ],
    ).build(request.address)


@page(f"3{_FORECAST}{TABLE}{{geoname_id:int}}", title="One place")
async def place(request: PageRequest, geoname_id: int) -> Page | None:
    """The forecast for one place in the gazetteer.

    Returns None where no place has that id, which is not the same as a
    place with no forecast: the session says so and leaves the reader where
    they were.
    """
    found = await asyncio.to_thread(PLACES.of(request.service).place, geoname_id)
    if found is None:
        #  Not here, which is different from here and empty. The session says
        #  so and leaves the reader where they were.
        return None
    source = FORECASTS.of(request.service)
    return forecast_page(
        request.app,
        request.address,
        found,
        await source.forecast_for(found),
        back_to=_searched_from(request),
    )


@page("4", title="Forecast by lat/lon position", keywords=("POSITION", "COORDS"))
async def by_position(request: PageRequest) -> Page:
    """Two fields, for anywhere on earth whether anybody lives there or not.

    `0` is not the way out here and the footer does not pretend otherwise: on
    a page where digits are data, a `0` that went to the menu would be a key
    that ate a coordinate.

    **Both fields are empty every time the page is fetched**, as the search
    field is and for the same reason: a reader comes back here to look at
    somewhere else, and a remembered position would cost twelve presses of the
    rub-out key across two fields. Nudging is what the arrows and a fresh six
    characters are for.
    """
    app = request.app
    return PageLayout(
        title=app.heading_for(request.address),
        #  No way home on this page: `0` keyed into a coordinate is a nought,
        #  so the field takes it and the prompt says how to leave instead.
        parts=[
            Once(Lines(said=("Key a position in degrees,", "to one decimal place."))),
            Once(position_fields(app, PLACES.of(request.service))),
        ],
    ).build(request.address)


@page(f"4{_FORECAST}{TABLE}{{lat:latitude}}{{lon:longitude}}", title="One point")
async def point(request: PageRequest, lat: float, lon: float) -> Page:
    """The forecast for a latitude and longitude, named by what is nearest.

    A point is not a place and does not pretend to be one: at a tenth of a
    degree two thirds of the world's towns share a cell with another. It
    borrows a clock from the nearest place, and says which.
    """
    #  A point is not a place and cannot pretend to be one: at a tenth of a
    #  degree two thirds of the world's towns share a cell with another. So it
    #  borrows a clock from whatever is nearest, and says which.
    nearby = await asyncio.to_thread(PLACES.of(request.service).nearest, lat, lon)
    where = point_place(lat, lon, nearby)
    source = FORECASTS.of(request.service)
    return forecast_page(
        request.app,
        request.address,
        where,
        await source.forecast_for(where),
        near=nearby,
        back_to=_searched_from(request),
    )


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
    app = request.app
    searches = {app.address_for("by_name"), app.address_for("by_position")}
    for been in reversed(request.history):
        if been in searches:
            return been
    return app.address_for("by_name")


@page("2", title="Lately looked up", keywords=("LATELY", "RECENT"))
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
    app = request.app
    visits = VISITS.found_in(request.service)
    if visits is None:
        return _nothing_kept(app, request.address)
    seen = await visits.recent(CHOICES_PER_FRAME, prefix=_FORECASTS_PREFIX)
    return PageLayout(
        title=app.heading_for(request.address),
        home=app.index,
        parts=[
            Once(Lines(said=("Places lately looked up here.", ""))),
            Flowing(
                Menu(
                    entries=[
                        MenuItem(
                            text=place.name,
                            detail=place.country,
                            destination=visit.page,
                        )
                        for visit, place in await _places_of(
                            app, request.service, seen
                        )
                    ],
                    empty="Nobody has looked anything up yet.",
                )
            ),
        ],
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
    index = PLACES.of(service)
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


def _nothing_kept(app: Sextile, address: PageAddress) -> Page:
    return PageLayout(
        title=app.heading_for(address),
        home=app.index,
        parts=[
            Flowing(
                Prose.of("This service is not keeping a log of what has been looked up.")
            )
        ],
    ).build(address)


@page("9", title="About this service", keywords=("ABOUT",))
async def about(request: PageRequest) -> Page:
    """What this service is, who it is built out of, and who has called.

    The last of those is the only figure the service keeps about its readers,
    and it is a count of connections rather than of anybody: the log holds a
    token minted per call and nothing else, so this can say how many and can
    never say who.
    """
    app = request.app
    return PageLayout(
        title=app.heading_for(request.address),
        home=app.index,
        parts=[
            Flowing(
                Prose.of(
                    "The weather, served as Viewdata frames to computers that "
                    "were obsolete before the forecast models were written.",
                    "Forecasts come from the Norwegian Meteorological Institute, "
                    "who publish them for anyone to use. Place names come from "
                    "GeoNames. Both are licensed CC BY 4.0, and neither endorses "
                    "this service.",
                    "Forecasts are held for as long as met.no asks them to be, so "
                    "two readers asking about the same town within the half hour "
                    "are one request rather than two.",
                    await _callers(request),
                )
            )
        ],
    ).build(request.address)


async def _callers(request: PageRequest) -> str:
    """How many have called this week, and where the rest of it is.

    A week rather than the whole log, because "lately" is the only sense in
    which one figure means anything: thirty days of a service nobody has
    dialled for a fortnight reads as busier than it is. The other periods are
    on a page of their own, which this points at rather than repeating.
    """
    visits = VISITS.found_in(request.service)
    if visits is None:
        return ""
    calls = await visits.callers(since=datetime.now(UTC) - _A_WEEK)
    if not calls:
        return ""
    app = request.app
    return (
        f"{calls} call{'' if calls == 1 else 's'} in the last seven days; "
        f"{keyed(app.address_for('who_called'))} for more. The log keeps a "
        "token for each and nothing else: it can say how many and never who."
    )


@page("90", title="Log off", keywords=("BYE", "OFF"))
async def goodbye(request: PageRequest) -> Page:
    """The farewell frame, after which the line drops."""
    #  `Ring off` here and `Log off` on the menu, which are two different
    #  jobs: the menu names an action, and Prestel called that logging off,
    #  where this is an instruction to somebody holding a handset. Dated
    #  British rather than an Americanism -- the American is "hang up" -- and
    #  the register the rest of the service is written in.
    return farewell_page("GOODBYE", "Thank you for calling.", "", "Ring off.")


@page("91", name="help", title="How to get about", keywords=("HELP",))
async def guide(request: PageRequest) -> Page:
    """How to get about, which is mostly the framework's to say.

    The keys this service adds are the two a reader meets nowhere else: the
    letters that go into a search field, and the one that takes them back to
    the search they came through. Everything else on the page -- the digits,
    the way home, the shape of a request, the compass -- is the framework's,
    generated from what it actually answers rather than described here.
    """
    app = request.app
    return await app.guide(
        request,
        #  No `A` and `D` on the compass. They step through the run of pages a
        #  menu offered, and this service does not wire them: a forecast is
        #  reached from a suggestion list rather than from a menu, and there is
        #  no run of them to step through. Two keys that did nothing were being
        #  drawn on the one page a reader goes to to find out what the keys do.
        items=False,
        moving=[
            GuideRow("A-Z", "type into a search field"),
            GuideRow(FIND_KEY, "back to your search"),
        ],
        #  In the order of the numbers, which is the order a reader reads a
        #  column of numbers in. Grouped by subject it was `95` before `93`,
        #  and a list of page numbers out of order reads as a mistake whatever
        #  the grouping was for.
        asking=[
            GuideRow(keyed(app.address_for("goodbye")), "log off"),
            GuideRow(),
            GuideRow(keyed(app.address_for("contents")), "every page and its number"),
            GuideRow(keyed(app.address_for("names")), "every word you can key"),
            GuideRow(keyed(app.address_for("symbols")), "what the symbols mean"),
        ],
    )


@page("96", title="Pages lately read", keywords=("READ",))
async def read_lately(request: PageRequest) -> Page:
    """The framework's page, at this service's number."""
    app = request.app
    visits = VISITS.found_in(request.service)
    if visits is None:
        return _nothing_kept(app, request.address)
    return await app.lately_read(request, visits)


@page("97", title="Pages read most", keywords=("POPULAR",))
async def read_most(request: PageRequest) -> Page:
    """The framework's page, at this service's number."""
    app = request.app
    visits = VISITS.found_in(request.service)
    if visits is None:
        return _nothing_kept(app, request.address)
    return await app.most_read(request, visits)


@page("98", title="Who has called", keywords=("CALLERS",))
async def who_called(request: PageRequest) -> Page:
    """The framework's page, at this service's number."""
    app = request.app
    visits = VISITS.found_in(request.service)
    if visits is None:
        return _nothing_kept(app, request.address)
    return await app.who_has_called(request, visits)


#  `LEGEND` among the keywords, which is the word for this on a map and in
#  met.no's own files. It is not the title, because a page whose whole purpose
#  is explaining should not have a name that wants explaining -- but a reader
#  who reaches for the word should find the page.
#
#  Not `PICTURES`, which this page answered to for a while: a keyword is a
#  name in a namespace of one, and holding a good word against a page that has
#  stopped needing it is how the namespace fills up.
@page("95", title="What the symbols mean", keywords=("SYMBOLS", "KEY", "LEGEND"))
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
    app = request.app
    return PageLayout(
        title=app.heading_for(request.address),
        home=app.index,
        parts=[
            Once(Lines(said=("Drawn by day, except where it says.", ""))),
            Flowing(
                SymbolTable(
                    entries=in_pairs(
                        [Shown(code, in_full(code)) for code in PUBLISHED]
                        + [Shown(code, words) for code, words in SKIES]
                    )
                )
            ),
        ],
    ).build(request.address)
