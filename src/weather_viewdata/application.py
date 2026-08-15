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

The handlers are in `handlers`, each declared beside its function,
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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Final

from sextile import Sextile, standard_pages
from sextile.middleware import log_pages, record_visits
from sextile.visits import KEPT, SqliteVisits
from weather_viewdata import handlers
from weather_viewdata.coordinates import LATITUDE, LONGITUDE
from weather_viewdata.forecast.source import ForecastSource
from weather_viewdata.handlers import FORECASTS, PLACES, SERVICE_NAME, VISITS
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
    *handlers.router,
    *standard_pages(
        history="92",
        contents="93",
        keywords="94",
        recent="96",
        popular="97",
        callers="98",
        visits=VISITS,
    ),
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
    numbering needs, what wraps every page, and the pages themselves, so
    registration order does not matter.
    """

    @asynccontextmanager
    async def lifespan(app: Sextile) -> AsyncIterator[None]:
        """What the service holds while it is up, opened and closed in one place.

        The index is an ordinary local held across the yield, which is the
        advantage of a context manager over a pair of handlers: there is
        nowhere for the opening and the closing to drift apart, and nothing has
        to be hoisted anywhere for both to see.
        """
        index = await asyncio.to_thread(Index.open, index_filepath)
        try:
            #  Refused rather than warned about. A stale index still answers,
            #  by rules the code stopped using, with nothing on the screen to
            #  say so. Better to refuse to start and name the fix than to start
            #  and answer wrongly.
            if index.stale:
                raise StaleIndexError(
                    f"{index_filepath} was built by older rules and would "
                    f"answer by them. Run `weather-viewdata import-places "
                    f"--index {index_filepath}` to rebuild it."
                )
            visits = await asyncio.to_thread(
                SqliteVisits.open, visits_filepath, kept=kept
            )
        except BaseException:
            #  Whatever went wrong after the index opened, the index closes:
            #  a service that will not start should not hold the file either,
            #  least of all against the rebuild its own error names.
            await asyncio.to_thread(index.close)
            raise
        try:
            app.state[PLACES] = index
            app.state[FORECASTS] = source
            app.state[VISITS] = visits
            yield
        finally:
            await asyncio.to_thread(visits.close)
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
        middleware=[log_pages(), record_visits(VISITS)],
        lifespan=lifespan,
    )

    return app


__all__ = ["SERVICE_NAME", "StaleIndexError", "build_application"]
