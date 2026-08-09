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

from sextile.page import Page
from weather_viewdata import build_application
from weather_viewdata.forecast.model import Forecast, Moment
from weather_viewdata.forecast.source import ForecastSource
from weather_viewdata.geonames import Place
from weather_viewdata.hours import HOURS_SHOWN
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


async def page_for(forecast: Forecast, tmp_path: Path) -> Page:
    filepath = tmp_path / "places.sqlite"
    with Index.open(filepath) as index:
        index.add_places([TRONDHEIM])
    app = build_application(source=Fixed(forecast), index_filepath=filepath)
    await app.startup()
    try:
        page = await app.ask("3213133880")
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
        assert "mm" not in shown
        assert "2.3m/s" in shown

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
        assert "loc" in shown
        assert "m/s" in shown

    async def test_the_table_starts_where_the_strip_left_off(
        self, tmp_path: Path
    ) -> None:
        #  Each says its piece once. A reader who has just seen eight hours
        #  drawn across the frame does not want them again as rows.
        page = await page_for(hourly(30), tmp_path)
        first = this_hour() + timedelta(hours=HOURS_SHOWN + 1)
        assert f"{first:%H:%M}" in text_of(page)
        skipped = this_hour() + timedelta(hours=HOURS_SHOWN)
        assert f" {skipped:%H:%M}" not in text_of(page)

    async def test_a_forecast_of_one_hour_still_draws(self, tmp_path: Path) -> None:
        #  Nothing after now, so nothing in the strip and nothing in the table.
        #  The page is the preamble and the weather now, which is all there is
        #  to say and is better than a frame of empty columns.
        page = await page_for(hourly(1), tmp_path)
        assert "NOW" in text_of(page)

    async def test_the_strip_is_on_the_first_frame_only(self, tmp_path: Path) -> None:
        page = await page_for(hourly(80), tmp_path)
        assert "m/s" not in text_of(page, 1)
