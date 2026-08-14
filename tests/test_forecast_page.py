"""The weather a reader is standing in, at the top of the forecast page.

A forecast page is mostly about later. What a reader wants first is now, and
before this it was the first row of a table of eighty-six, indistinguishable
from the hour after it.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from sextile import Page, PageAddress, PageRequest
from sextile.layout import DEFAULT_FURNITURE, content_rows
from sextile.viewdata.charset import encode_g0
from sextile.viewdata.frame import COLUMNS
from weather_viewdata import build_application
from weather_viewdata.forecast.model import Forecast, Moment
from weather_viewdata.forecast.source import ForecastSource
from weather_viewdata.forecast_page import FIND_KEY
from weather_viewdata.geonames import Place
from weather_viewdata.hours import HOURS_SHOWN
from weather_viewdata.icons import COLUMN_CELLS
from weather_viewdata.store import Index

OSLO = ZoneInfo("Europe/Oslo")

TRONDHEIM = Place(
    geoname_id=3133880,
    name="Trondheim",
    ascii_name="Trondheim",
    alternate_names=(),
    latitude=63.43049,
    longitude=10.39506,
    feature_class="P",
    feature_code="PPL",
    country="NO",
    admin1="21",
    population=147139,
    elevation=18,
    timezone="Europe/Oslo",
)

NOON = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def this_hour() -> datetime:
    """The hour the test is being run in.

    The page asks the clock what now is, so a fixture pinned to a date would
    pass or fail according to the time of day. Anchoring the forecast to the
    real hour makes its first moment the current one whenever it runs.
    """
    return datetime.now(UTC).replace(minute=0, second=0, microsecond=0)


def hourly(count: int, *, start: datetime | None = None, **first: Any) -> Forecast:
    """A run of hours, the first of which may be given readings of its own."""
    begins = this_hour() if start is None else start
    moments = [
        Moment(
            at=begins + timedelta(hours=hour),
            temperature=12.4 + hour,
            wind_speed=2.3,
            wind_from=225.0,
            precipitation=0.4,
            covers=timedelta(hours=1),
            symbol="lightrain",
        )
        for hour in range(count)
    ]
    if first:
        moments[0] = replace(moments[0], **first)
    return Forecast(updated_at=begins - timedelta(minutes=31), moments=tuple(moments))


class Fixed(ForecastSource):
    def __init__(self, forecast: Forecast) -> None:
        self.forecast = forecast

    async def forecast_for(self, place: Place) -> Forecast | None:
        del place
        return self.forecast


async def page_for(
    forecast: Forecast, tmp_path: Path, history: tuple[PageAddress, ...] = ()
) -> Page:
    filepath = tmp_path / "places.sqlite"
    with Index.open(filepath) as index:
        index.add_places([TRONDHEIM])
    app = build_application(
        source=Fixed(forecast),
        index_filepath=filepath,
        visits_filepath=tmp_path / "visits.sqlite",
    )
    await app.startup()
    try:
        page = await app.respond(
            PageRequest(
                address=PageAddress("3213133880"),
                params={"geoname_id": TRONDHEIM.geoname_id},
                history=history,
                application=app,
                service=app.service,
            )
        )
    finally:
        await app.shutdown()
    assert page is not None
    return page


def text_of(page: Page, index: int = 0) -> str:
    found = page.frame(index)
    assert found is not None
    characters, _ = found.frame.to_grid()
    return "\n".join(characters)


class TestWhichMomentIsNow:
    def test_the_one_the_reader_is_standing_in(self) -> None:
        forecast = hourly(6, start=NOON)
        found = forecast.current(NOON + timedelta(minutes=47))
        assert found is not None
        assert found.at == NOON

    def test_and_not_the_one_after_it(self) -> None:
        #  12:59 is still the noon hour. Rounding to the nearest would show a
        #  reader weather that has not happened yet.
        forecast = hourly(6, start=NOON)
        found = forecast.current(NOON + timedelta(minutes=59))
        assert found is not None
        assert found.at == NOON

    def test_a_forecast_that_begins_later_starts_where_it_begins(self) -> None:
        #  met.no's answer can start after the hour it was asked in. The first
        #  moment is then the nearest thing to now there is, and showing
        #  nothing would read as a fault.
        forecast = hourly(6, start=NOON + timedelta(hours=2))
        found = forecast.current(NOON)
        assert found is not None
        assert found.at == NOON + timedelta(hours=2)

    def test_and_one_with_no_moments_has_no_now(self) -> None:
        assert Forecast(updated_at=NOON).current(NOON) is None


class TestTheBlockAtTheTop:
    async def test_it_says_the_weather_now(self, tmp_path: Path) -> None:
        page = await page_for(hourly(6, symbol="heavyrain"), tmp_path)
        assert "NOW" in text_of(page)
        assert "heavy rain" in text_of(page)

    async def test_it_gives_the_temperature_the_wind_and_the_rain(
        self, tmp_path: Path
    ) -> None:
        page = await page_for(hourly(6), tmp_path)
        shown = text_of(page)
        assert "12.4C" in shown
        assert "SW 2.3m/s" in shown
        assert "0.4mm/h" in shown

    async def test_a_reading_over_six_hours_says_so(self, tmp_path: Path) -> None:
        #  1.7mm in an hour and 1.7mm over six are different weather, and the
        #  figure alone cannot tell them apart.
        page = await page_for(
            hourly(6, precipitation=1.7, covers=timedelta(hours=6)), tmp_path
        )
        assert "1.7mm/6h" in text_of(page)

    async def test_a_missing_reading_is_left_out_rather_than_called_nought(
        self, tmp_path: Path
    ) -> None:
        page = await page_for(hourly(6, precipitation=None, wind_from=None), tmp_path)
        shown = text_of(page)
        assert "mm/h" not in shown
        assert "2.3m/s" in shown

    async def test_both_clocks_are_on_one_row_and_say_which_they_are(
        self, tmp_path: Path
    ) -> None:
        #  They were on two rows -- `Times UTC and CEST (UTC+2)` above
        #  `NOW 16:00 18:00` -- and putting the labels beside the times saves
        #  the row and the repetition both.
        shown = text_of(await page_for(hourly(6), tmp_path))
        assert "UTC" in shown
        assert "CEST" in shown
        assert "Times UTC and" not in shown

    async def test_the_weather_now_is_drawn_as_well_as_said(
        self, tmp_path: Path
    ) -> None:
        #  The picture sits at the end of the two rows and of the blank above
        #  them, which is three rows and exactly what a picture is tall.
        page = await page_for(hourly(6), tmp_path)
        found = page.frame(0)
        assert found is not None
        first = content_rows(DEFAULT_FURNITURE).start
        for row in (first + 2, first + 3, first + 4):
            assert found.frame.is_attribute(row, COLUMNS - COLUMN_CELLS), row

    async def test_it_is_on_the_first_frame_only(self, tmp_path: Path) -> None:
        #  A lead-in, like the position above it. A reader on frame c is
        #  reading later hours and has already been told about now.
        page = await page_for(hourly(80), tmp_path)
        assert "NOW" not in text_of(page, 1)

    @pytest.mark.parametrize("count", [1, 2, 3])
    async def test_a_forecast_of_almost_nothing_still_draws(
        self, count: int, tmp_path: Path
    ) -> None:
        page = await page_for(hourly(count), tmp_path)
        assert "NOW" in text_of(page)


class TestTheHourByHourStrip:
    """The forecast read across instead of down.

    A table of hours is exact and has to be read a row at a time; a strip of
    them is a shape, and a reader takes in "clear this afternoon, rain by six"
    without reading anything at all.
    """

    async def test_it_shows_the_next_eight_hours(self, tmp_path: Path) -> None:
        page = await page_for(hourly(30), tmp_path)
        shown = text_of(page)
        start = this_hour()
        for ahead in range(1, HOURS_SHOWN + 1):
            hour = f"{(start + timedelta(hours=ahead)).astimezone(OSLO):%H}"
            assert hour in shown, hour

    async def test_and_says_which_row_is_which(self, tmp_path: Path) -> None:
        #  Four cells of the forty go on saying so, which is what takes the
        #  strip from ten hours to eight. Two unlabelled rows of figures on a
        #  page a reader sees once is a page that has to be explained.
        shown = text_of(await page_for(hourly(30), tmp_path))
        assert "CEST" in shown
        assert "m/s" in shown

    async def test_the_days_follow_on_the_next_frame(self, tmp_path: Path) -> None:
        #  Two answers to two questions: the strip says what this afternoon
        #  will do, the days which day to go out on.
        page = await page_for(hourly(30), tmp_path)
        assert "Today" in text_of(page, 1)

    async def test_a_forecast_of_one_hour_still_draws(self, tmp_path: Path) -> None:
        #  Nothing after now, so nothing in the strip and nothing in the table.
        #  The page is the preamble and the weather now, which is all there is
        #  to say and is better than a frame of empty columns.
        page = await page_for(hourly(1), tmp_path)
        assert "NOW" in text_of(page)

    async def test_the_strip_is_on_the_first_frame_only(self, tmp_path: Path) -> None:
        page = await page_for(hourly(80), tmp_path)
        assert "dir" not in text_of(page, 1)


class TestSayingTheHourAsAnHour:
    """`NOW 16:00` under `Issued 16:29` read as a contradiction.

    It was not one. met.no's series begins at the hour containing the model
    run -- measured against a real response, `updated_at` 15:29 with a first
    moment of 15:00 -- so a forecast issued at half past can perfectly well
    tell you about the hour that began at the top of it.

    What was wrong was the word `NOW` beside a single time, which promises an
    instant when the readings are an hour's.
    """

    async def test_the_hour_is_shown_as_a_range(self, tmp_path: Path) -> None:
        page = await page_for(hourly(6), tmp_path)
        start = this_hour()
        ends = start + timedelta(hours=1)
        assert f"{start:%H}―{ends:%H} UTC" in text_of(page)

    async def test_and_so_is_the_local_one(self, tmp_path: Path) -> None:
        page = await page_for(hourly(6), tmp_path)
        start = this_hour().astimezone(OSLO)
        ends = start + timedelta(hours=1)
        assert f"{start:%H}―{ends:%H} CEST" in text_of(page)

    async def test_a_moment_covering_six_hours_says_six(self, tmp_path: Path) -> None:
        #  The far end of a forecast is six-hourly, and a range that said one
        #  hour there would be inventing five.
        page = await page_for(
            hourly(6, covers=timedelta(hours=6)), tmp_path
        )
        start = this_hour()
        ends = start + timedelta(hours=6)
        assert f"{start:%H}―{ends:%H} UTC" in text_of(page)

    async def test_the_two_ends_are_joined_by_a_long_dash(self, tmp_path: Path) -> None:
        #  G0 has both, and a range wants the bar that fills the cell: 0x60,
        #  where ASCII keeps its backtick. Read out of Beebium's font. It is
        #  not the underscore, whatever a teletext editor's keyboard suggests
        #  -- 0x5F is the hash, the viewdata command key.
        page = await page_for(hourly(6), tmp_path)
        found = page.frame(0)
        assert found is not None
        assert 0x60 in found.frame.to_bytes()
        assert encode_g0("―") == 0x60
        assert encode_g0("#") == 0x5F


class TestGettingBackToTheSearch:
    """`F`, because `S` pages down and `0` is the index.

    A reader who has just found a place usually wants the next place, and the
    way back was otherwise `*0#` -- or a page number they would have to
    remember.
    """

    async def test_the_forecast_offers_a_way_back(self, tmp_path: Path) -> None:
        page = await page_for(hourly(6), tmp_path)
        found = page.frame(0)
        assert found is not None
        assert found.destination(FIND_KEY) == PageAddress("3")

    async def test_on_every_frame_of_it(self, tmp_path: Path) -> None:
        #  The reader may be four frames into the table when they decide.
        page = await page_for(hourly(80), tmp_path)
        for index in range(len(page.frames)):
            found = page.frame(index)
            assert found is not None
            assert found.destination(FIND_KEY) is not None, index

    async def test_and_the_footer_says_so(self, tmp_path: Path) -> None:
        #  A page that offered a key without naming it would be a page whose
        #  keys can only be found by trying them.
        assert "F find" in text_of(await page_for(hourly(6), tmp_path))

    async def test_it_goes_back_to_the_search_actually_used(
        self, tmp_path: Path
    ) -> None:
        #  Both searches lead here. A reader who came through the position form
        #  is offered the position form, not the one they did not use.
        page = await page_for(
            hourly(6), tmp_path, history=(PageAddress("1"), PageAddress("4"))
        )
        found = page.frame(0)
        assert found is not None
        assert found.destination(FIND_KEY) == PageAddress("4")

    async def test_and_to_the_likelier_one_where_neither_was(
        self, tmp_path: Path
    ) -> None:
        #  Keyed by number, or reached by a keyword: no search was used, and a
        #  name is how nearly everybody looks for weather.
        page = await page_for(hourly(6), tmp_path, history=(PageAddress("1"),))
        found = page.frame(0)
        assert found is not None
        assert found.destination(FIND_KEY) == PageAddress("3")
