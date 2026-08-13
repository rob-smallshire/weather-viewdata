"""The weather, as a Viewdata service.

Global, because met.no forecasts anywhere; dialled mostly from Britain, because
that is where the working Beebs are. Those two facts pull against each other
exactly once, in the ranking, and are settled there.

    0                  the title frame
    1                  the main menu
    2                  the places lately looked up here
    3                  forecast by placename
    321<geoname-id>    one place's forecast, as a table
    4                  forecast by lat/lon position
    421<lat><lon>      one point's forecast, as a table
    9  about   90 log off   91 how to get about   95 what the symbols mean
    92 history  93 contents  94 keywords  96/97 what has been read

Seven of those are the framework's, drawn from what it already knows and mapped
into this numbering. What is this service's own is 0-4, 9, 90 and 95.

The pages are in `pages`, each declared beside the function that builds it,
and this module only assembles them into a running service. The drawing is
elsewhere again: `forecast_page` turns a forecast into frames, `search`
builds the two forms, `legend` draws the symbols page; beneath those,
`symbols` takes met.no's codes apart, `icons` draws one, `hours` puts eight
of them across a frame with the charts between, and `days` puts ten days
down one.

Two ways to name a forecast, failing differently. A named place carries a name,
a timezone and an altitude, and depends on GeoNames still holding that record.
A point carries none of those and depends on nothing at all.
"""

import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Final

from sextile import PageRoute, Sextile, routes_in
from sextile.middleware import log_pages, record_visits
from sextile.pages import contents, history, names
from sextile.visits import KEPT, SqliteVisits
from weather_viewdata import pages
from weather_viewdata.coordinates import LATITUDE, LONGITUDE
from weather_viewdata.forecast.source import ForecastSource
from weather_viewdata.pages import FORECASTS, PLACES, SERVICE_NAME, VISITS
from weather_viewdata.store import Index

DEFAULT_INDEX_FILEPATH: Final = Path("places.sqlite")

#: Where the log of what has been read is kept. A file of its own, beside the
#: place index rather than in it: the index is derived and `import-places`
#: rebuilds it wholesale, where this is the only copy of what it holds.
DEFAULT_VISITS_FILEPATH: Final = Path("visits.sqlite")


class StaleIndexError(RuntimeError):
    """The place index was built by rules this code no longer uses."""


#: What the service is made of: its own pages, declared beside the functions
#: that build them, and three the framework builds and hands over as handlers,
#: mapped into this numbering. Each of those is generated from what the
#: framework already knows, so none of them can drift from the service it
#: describes.
PAGES: Final = (
    *routes_in(pages),
    PageRoute("92", history, title="Where you have been",
              detail="this call, newest first", keywords=("HISTORY",)),
    PageRoute("93", contents, title="Every page",
              detail="and the number that fetches it", keywords=("PAGES",)),
    PageRoute("94", names, title="Words you can key",
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
            yield PLACES.holding(index) | FORECASTS.holding(source) | VISITS.holding(visits)
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
        middleware=[log_pages(), record_visits(VISITS.find)],
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


__all__ = ["SERVICE_NAME", "StaleIndexError", "build_application"]
