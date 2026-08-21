"""met.no's `locationforecast/2.0/compact`, read into the domain.

Everything above this deals in `Forecast` and `Moment` and has never heard of
JSON. The parsing is a pure function over a decoded response, which is what
lets it be exercised against a real capture rather than a mock.

Two things about the format are worth knowing before reading the code, both
established from a real response rather than from documentation:

The series changes resolution part way along. The first two or three days
are hourly and the rest six-hourly, so `next_1_hours` is present at the start
and absent later. Which blocks a moment carries shows how specific the source
is at that point.

A block describes the period *after* the moment it hangs on, not the moment
itself. So a moment's symbol is what the weather will do next, and the last
moment in the series has no block at all -- there is no next hour inside the
forecast for it to summarise.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Any, Final, Self

import httpx2
from sextile import __version__

from weather_viewdata.forecast.model import Forecast, Moment
from weather_viewdata.forecast.source import AnonymousError, ForecastSource
from weather_viewdata.geonames import Place

_logger = logging.getLogger(__name__)

FORECAST_URL: Final = "https://api.met.no/weatherapi/locationforecast/2.0/compact"

#: Who is asking, and where to complain. The terms ask for an application name
#: and a contact -- an email or a website -- and say that going without risks
#: being blocked without warning.
USER_AGENT: Final = f"Sextile/{__version__} (+https://github.com/rob-smallshire/sextile)"

#: Decimal places kept of a latitude or longitude. About eleven metres, which
#: is finer than any forecast model, and coarse enough that two readers asking
#: about the same town are one request rather than two.
#:
#: Not enforced at their end -- ten decimal places were tried and answered --
#: so this is courtesy and cache-efficiency rather than a rule.
_PLACES: Final = 4

#: Least time between two requests. The ceiling is twenty a second; the terms
#: also ask that requests be spread out rather than bunched, and a viewdata
#: board answering a handful of callers has all the time in the world.
MIN_INTERVAL: Final = 1.0

#: Used only when a response names no expiry of its own.
DEFAULT_FRESHNESS: Final = timedelta(minutes=30)

#: The least time an answer is held, whatever the response said.
#:
#: A response whose `Expires` has already passed -- a clock adrift, a cache
#: misconfigured, a header we misread -- would otherwise mean re-fetching on
#: every request, which is exactly the traffic the header exists to prevent,
#: and it would be us doing it. Their mistake should not become our rudeness.
MIN_FRESHNESS: Final = timedelta(minutes=5)

#: The blocks a moment may carry, shortest first. The shortest present is used,
#: which keeps the answer as specific as the data allows.
_BLOCKS: Final = (
    ("next_1_hours", timedelta(hours=1)),
    ("next_6_hours", timedelta(hours=6)),
    ("next_12_hours", timedelta(hours=12)),
)


def parse_forecast(document: Mapping[str, Any]) -> Forecast:
    """Read a decoded `compact` response."""
    properties = document["properties"]
    return Forecast(
        updated_at=_instant(properties["meta"]["updated_at"]),
        moments=tuple(_moment(entry) for entry in properties["timeseries"]),
    )


def _moment(entry: Mapping[str, Any]) -> Moment:
    data = entry["data"]
    details = data.get("instant", {}).get("details", {})
    block, covers = _shortest_block(data)
    return Moment(
        at=_instant(entry["time"]),
        temperature=details.get("air_temperature"),
        wind_speed=details.get("wind_speed"),
        wind_from=details.get("wind_from_direction"),
        cloud_cover=details.get("cloud_area_fraction"),
        humidity=details.get("relative_humidity"),
        pressure=details.get("air_pressure_at_sea_level"),
        symbol=block.get("summary", {}).get("symbol_code"),
        precipitation=block.get("details", {}).get("precipitation_amount"),
        covers=covers,
    )


def _shortest_block(
    data: Mapping[str, Any],
) -> tuple[Mapping[str, Any], timedelta | None]:
    """The most specific summary a moment carries, and what period it covers."""
    for name, covers in _BLOCKS:
        block = data.get(name)
        if block is not None:
            return block, covers
    #  The last moment in the series, which has nothing after it to describe.
    return {}, None


def _instant(stamp: str) -> datetime:
    """One of met.no's times, which are Zulu.

    `fromisoformat` reads the `Z` from Python 3.11, and the result is made
    explicitly UTC-aware rather than left to be inferred -- a naive datetime
    escaping into a service that shows times in a place's own zone would be
    wrong by hours and look plausible.
    """
    return datetime.fromisoformat(stamp).astimezone(UTC)


@dataclass
class _Held:
    """A forecast, and what the server said about how long it is good for."""

    forecast: Forecast
    expires: datetime
    last_modified: str | None
    """Kept as the string it arrived as. The terms ask for the *exact* value to
    be sent back, and a datetime round-tripped through our own formatting is
    not exact -- it is merely equivalent, which is not what was asked."""


class MetNoSource(ForecastSource):
    """met.no's locationforecast, fetched on met.no's terms.

    The terms are not onerous and the penalty for ignoring them is being
    blocked without warning, so they are structural here rather than
    remembered: a caller cannot ask twice inside an `Expires` window, cannot
    ask anonymously, and cannot bunch requests together, because there is no
    method that does any of those things.
    """

    def __init__(
        self,
        *,
        client: httpx2.AsyncClient | None = None,
        user_agent: str = USER_AGENT,
        now: Callable[[], datetime] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not user_agent.strip():
            raise AnonymousError(
                "met.no asks who is calling and where to complain; say so in the "
                "User-Agent"
            )
        self._user_agent = user_agent
        self._client = client or httpx2.AsyncClient()
        self._now = now or (lambda: datetime.now(UTC))
        self._sleep = sleep
        self._held: dict[tuple[float, float], _Held] = {}
        self._last_asked: datetime | None = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def forecast_for(self, place: Place) -> Forecast | None:
        """This place's weather, from the cache if it is still good.

        Returns None where the service would not answer, so that a page can say
        the forecast is not available. Drawing an empty forecast instead would
        read as calm weather, which is the one wrong answer a weather service
        must not give.
        """
        where = (round(place.latitude, _PLACES), round(place.longitude, _PLACES))
        held = self._held.get(where)
        if held is not None and self._now() < held.expires:
            return held.forecast
        return await self._fetch(place, where, held)

    async def _fetch(
        self,
        place: Place,
        where: tuple[float, float],
        held: _Held | None,
    ) -> Forecast | None:
        await self._wait_our_turn()
        headers = {"User-Agent": self._user_agent}
        if held is not None and held.last_modified is not None:
            headers["If-Modified-Since"] = held.last_modified

        parameters: dict[str, str] = {"lat": str(where[0]), "lon": str(where[1])}
        if place.elevation is not None:
            #  Recommended in hilly terrain, and left out entirely where it is
            #  unknown: nought is a claim about sea level, not an absence.
            parameters["altitude"] = str(place.elevation)

        try:
            response = await self._client.get(
                FORECAST_URL, params=parameters, headers=headers
            )
        except httpx2.HTTPError:
            _logger.exception("Could not reach met.no for %s", place.name)
            return None
        finally:
            self._last_asked = self._now()

        if response.status_code == httpx2.codes.NOT_MODIFIED and held is not None:
            #  Nothing has changed, and the response carries a fresh Expires.
            #  Not taking it would mean asking again at once, which is exactly
            #  the traffic the header exists to prevent.
            held.expires = self._expiry(response)
            return held.forecast

        if response.status_code != httpx2.codes.OK:
            #  Not cached: a refusal is not an answer, and holding one would
            #  keep a place unforecastable for half an hour over a blip.
            _logger.warning(
                "met.no answered %d for %s", response.status_code, place.name
            )
            return None

        forecast = parse_forecast(response.json())
        self._held[where] = _Held(
            forecast=forecast,
            expires=self._expiry(response),
            last_modified=response.headers.get("Last-Modified"),
        )
        return forecast

    async def _wait_our_turn(self) -> None:
        """Keep requests apart, rather than letting them bunch."""
        if self._last_asked is None:
            return
        since = (self._now() - self._last_asked).total_seconds()
        if since < MIN_INTERVAL:
            await self._sleep(MIN_INTERVAL - since)

    def _expiry(self, response: httpx2.Response) -> datetime:
        """When this answer stops being good enough to hand out again."""
        now = self._now()
        stated = response.headers.get("Expires")
        expires = now + DEFAULT_FRESHNESS
        if stated:
            try:
                expires = parsedate_to_datetime(stated).astimezone(UTC)
            except (TypeError, ValueError):
                #  A malformed date is not a reason to hammer them.
                _logger.warning("met.no sent an Expires we could not read: %r", stated)
        return max(expires, now + MIN_FRESHNESS)
