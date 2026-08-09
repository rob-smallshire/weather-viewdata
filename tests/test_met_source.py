"""Asking met.no for a forecast, on their terms.

The terms are specific and the penalty for ignoring them is being blocked
without warning, so they are enforced here rather than remembered in a comment:
identify yourself, honour `Expires`, ask conditionally with the exact
`Last-Modified` you were given, cache, and spread requests out.

Two of those were measured against the live service and found *not* to be
enforced at their end -- a request with no User-Agent was answered, and so was
one with ten decimal places of latitude. That is not a reason to stop doing
either. It is a reason to write down that we comply because we said we would.
"""

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest

from weather_viewdata.forecast.met import MetNoSource
from weather_viewdata.forecast.source import AnonymousError
from weather_viewdata.geonames import Place

FIXTURES = Path(__file__).parent / "data"
RESPONSE = (FIXTURES / "trondheim-compact.json").read_text()

WHEN = datetime(2026, 8, 9, 6, 0, tzinfo=UTC)
EXPIRES = "Sun, 09 Aug 2026 06:17:24 GMT"
LAST_MODIFIED = "Sun, 09 Aug 2026 05:47:10 GMT"

TRONDHEIM = Place(
    geoname_id=3133880,
    name="Trondheim",
    ascii_name="Trondheim",
    alternate_names=(),
    latitude=63.43049,
    longitude=10.39506,
    feature_class="P",
    feature_code="PPLA",
    country="NO",
    admin1="21",
    population=147139,
    elevation=14,
    timezone="Europe/Oslo",
)

BERGEN = Place(**{**TRONDHEIM.__dict__, "geoname_id": 3161732, "name": "Bergen",
                  "latitude": 60.39299, "longitude": 5.32415})


class FakeClock:
    """A clock that moves only when something sleeps, or is pushed."""

    def __init__(self) -> None:
        self.now = WHEN
        self.slept: list[float] = []

    def time(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += timedelta(seconds=seconds)


class Server:
    """A stand-in met.no that records what it was asked.

    Its `Expires` moves with the clock, as the real one's does: a fixed one
    would be in the past by the second request and would say nothing about
    whether the header is being honoured.
    """

    def __init__(self, clock: "FakeClock", *, status: int = 200) -> None:
        self.requests: list[httpx.Request] = []
        self.status = status
        self._clock = clock
        #: Overridden by the test that asks what we do with a stale one.
        self.expires: str | None = None

    def _expires(self) -> str:
        if self.expires is not None:
            return self.expires
        return format_datetime(self._clock.now + timedelta(minutes=30), usegmt=True)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status == 304:
            return httpx.Response(304, headers={"Expires": self._expires()})
        return httpx.Response(
            self.status,
            text=RESPONSE if self.status == 200 else "",
            headers={"Expires": self._expires(), "Last-Modified": LAST_MODIFIED},
        )


def source_for(server: Server, clock: FakeClock) -> MetNoSource:
    return MetNoSource(
        client=httpx.AsyncClient(transport=httpx.MockTransport(server)),
        now=clock.time,
        sleep=clock.sleep,
    )


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


class TestSayingWhoWeAre:
    async def test_every_request_carries_a_user_agent(self, clock: FakeClock) -> None:
        server = Server(clock)
        async with source_for(server, clock) as source:
            await source.forecast_for(TRONDHEIM)
        assert "Sextile" in server.requests[0].headers["User-Agent"]

    async def test_it_carries_somewhere_to_complain_to(self, clock: FakeClock) -> None:
        #  A company email or a website, which is what the terms ask for. A
        #  User-Agent naming only the software tells them nothing about who to
        #  ask to stop.
        server = Server(clock)
        async with source_for(server, clock) as source:
            await source.forecast_for(TRONDHEIM)
        assert "https://" in server.requests[0].headers["User-Agent"]

    async def test_an_anonymous_one_is_refused_here_rather_than_there(self) -> None:
        #  Their side answered a request with no User-Agent when it was tried,
        #  so nothing but this stops us making one.
        with pytest.raises(AnonymousError):
            MetNoSource(user_agent="")


class TestAskingOnlyWhenWeShould:
    async def test_the_first_ask_fetches(self, clock: FakeClock) -> None:
        server = Server(clock)
        async with source_for(server, clock) as source:
            forecast = await source.forecast_for(TRONDHEIM)
        assert forecast is not None
        assert len(server.requests) == 1

    async def test_a_second_ask_before_it_expires_does_not(
        self, clock: FakeClock
    ) -> None:
        #  The whole point of the Expires header, and the difference between a
        #  board that four people can dial and one that gets blocked.
        server = Server(clock)
        async with source_for(server, clock) as source:
            await source.forecast_for(TRONDHEIM)
            clock.now += timedelta(minutes=10)
            again = await source.forecast_for(TRONDHEIM)
        assert len(server.requests) == 1
        assert again is not None

    async def test_asking_again_after_it_expires_does(self, clock: FakeClock) -> None:
        server = Server(clock)
        async with source_for(server, clock) as source:
            await source.forecast_for(TRONDHEIM)
            clock.now += timedelta(hours=1)
            await source.forecast_for(TRONDHEIM)
        assert len(server.requests) == 2

    async def test_another_place_is_a_request_of_its_own(
        self, clock: FakeClock
    ) -> None:
        server = Server(clock)
        async with source_for(server, clock) as source:
            await source.forecast_for(TRONDHEIM)
            await source.forecast_for(BERGEN)
        assert len(server.requests) == 2


class TestAskingConditionally:
    async def test_the_second_request_quotes_what_we_were_given(
        self, clock: FakeClock
    ) -> None:
        #  The terms say to send back the exact Last-Modified value, not a
        #  reformatting of it. So it is kept as the string it arrived as.
        server = Server(clock)
        async with source_for(server, clock) as source:
            await source.forecast_for(TRONDHEIM)
            clock.now += timedelta(hours=1)
            await source.forecast_for(TRONDHEIM)
        assert server.requests[1].headers["If-Modified-Since"] == LAST_MODIFIED

    async def test_a_not_modified_keeps_what_we_had(self, clock: FakeClock) -> None:
        server = Server(clock)
        async with source_for(server, clock) as source:
            first = await source.forecast_for(TRONDHEIM)
            clock.now += timedelta(hours=1)
            server.status = 304
            second = await source.forecast_for(TRONDHEIM)
        assert second == first

    async def test_and_puts_off_the_next_ask(self, clock: FakeClock) -> None:
        #  A 304 carries a fresh Expires. Not taking it would mean asking again
        #  immediately, which is the traffic the header exists to prevent.
        server = Server(clock)
        async with source_for(server, clock) as source:
            await source.forecast_for(TRONDHEIM)
            clock.now += timedelta(hours=1)
            server.status = 304
            await source.forecast_for(TRONDHEIM)
            await source.forecast_for(TRONDHEIM)
        assert len(server.requests) == 2


class TestSpreadingRequestsOut:
    async def test_two_places_in_a_row_are_not_asked_at_once(
        self, clock: FakeClock
    ) -> None:
        #  Twenty a second is the ceiling; the terms also ask for requests to
        #  be spread evenly rather than bunched. A viewdata board has all the
        #  time in the world.
        server = Server(clock)
        async with source_for(server, clock) as source:
            await source.forecast_for(TRONDHEIM)
            await source.forecast_for(BERGEN)
        assert clock.slept, "the second request waited its turn"

    async def test_a_request_after_a_long_gap_waits_for_nothing(
        self, clock: FakeClock
    ) -> None:
        server = Server(clock)
        async with source_for(server, clock) as source:
            await source.forecast_for(TRONDHEIM)
            clock.now += timedelta(hours=1)
            await source.forecast_for(BERGEN)
        assert clock.slept == []


class TestWhatIsAsked:
    async def test_the_place_is_asked_for_by_position(self, clock: FakeClock) -> None:
        server = Server(clock)
        async with source_for(server, clock) as source:
            await source.forecast_for(TRONDHEIM)
        asked = server.requests[0].url
        assert asked.params["lat"] == "63.4305"
        assert asked.params["lon"] == "10.3951"

    async def test_the_altitude_goes_too(self, clock: FakeClock) -> None:
        #  Recommended in hilly terrain, and Norway is nothing else.
        server = Server(clock)
        async with source_for(server, clock) as source:
            await source.forecast_for(TRONDHEIM)
        assert server.requests[0].url.params["altitude"] == "14"

    async def test_a_place_of_unknown_height_asks_without_one(
        self, clock: FakeClock
    ) -> None:
        #  Rather than sending nought, which is a claim about sea level.
        server = Server(clock)
        nowhere = Place(**{**TRONDHEIM.__dict__, "elevation": None})
        async with source_for(server, clock) as source:
            await source.forecast_for(nowhere)
        assert "altitude" not in server.requests[0].url.params

    async def test_coordinates_are_rounded(self, clock: FakeClock) -> None:
        #  Not because they refuse more -- they were tried with ten decimals
        #  and answered -- but because two readers asking for the same town
        #  should be one request, and four decimals is about eleven metres.
        server = Server(clock)
        async with source_for(server, clock) as source:
            await source.forecast_for(TRONDHEIM)
        assert "63.43049" not in str(server.requests[0].url)


class TestWhenItGoesWrong:
    async def test_a_refusal_is_not_a_forecast(self, clock: FakeClock) -> None:
        #  None, so that a page can say the forecast is not available rather
        #  than drawing an empty one, which looks like calm weather.
        server = Server(clock, status=503)
        async with source_for(server, clock) as source:
            assert await source.forecast_for(TRONDHEIM) is None

    async def test_a_refusal_is_not_cached_as_an_answer(
        self, clock: FakeClock
    ) -> None:
        server = Server(clock, status=503)
        async with source_for(server, clock) as source:
            await source.forecast_for(TRONDHEIM)
            server.status = 200
            clock.now += timedelta(minutes=1)
            assert await source.forecast_for(TRONDHEIM) is not None


class TestNotBeingMisledIntoHammering:
    async def test_an_expires_already_past_still_holds_the_answer_a_while(
        self, clock: FakeClock
    ) -> None:
        """A stale Expires would mean re-fetching on every single request.

        Which is the traffic the header exists to prevent, and it would be us
        doing it -- so there is a floor under how often we will ask, whatever
        we are told.
        """
        server = Server(clock)
        server.expires = "Sun, 09 Aug 2026 00:00:00 GMT"  # long past
        async with source_for(server, clock) as source:
            await source.forecast_for(TRONDHEIM)
            await source.forecast_for(TRONDHEIM)
            await source.forecast_for(TRONDHEIM)
        assert len(server.requests) == 1
