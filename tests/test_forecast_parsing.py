"""Turning met.no's JSON into something a page can be drawn from.

Exercised against a real captured response rather than a made-up one, because
the shape has details no reasonable invention would have: the series changes
resolution part way through, and the blocks describing what the weather will
*do* are attached to the hour they begin rather than the hour they cover.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from weather_viewdata.forecast import Forecast
from weather_viewdata.forecast.met import parse_forecast

FIXTURES = Path(__file__).parent / "data"
TRONDHEIM = json.loads((FIXTURES / "trondheim-compact.json").read_text())


@pytest.fixture
def forecast() -> Forecast:
    return parse_forecast(TRONDHEIM)


class TestWhatWasRead:
    def test_it_says_when_it_was_made(self, forecast: Forecast) -> None:
        assert forecast.updated_at == datetime(2026, 8, 9, 5, 29, 9, tzinfo=UTC)

    def test_every_moment_is_read(self, forecast: Forecast) -> None:
        assert len(forecast.moments) == 86

    def test_they_are_in_order(self, forecast: Forecast) -> None:
        times = [moment.at for moment in forecast.moments]
        assert times == sorted(times)

    def test_they_are_timezone_aware_and_in_utc(self, forecast: Forecast) -> None:
        #  met.no answers in Zulu; the place's own zone is applied when a page
        #  is drawn, not here, because a forecast is not about one reader.
        assert forecast.moments[0].at == datetime(2026, 8, 9, 5, 0, tzinfo=UTC)

    def test_it_reaches_ten_days_ahead(self, forecast: Forecast) -> None:
        span = forecast.moments[-1].at - forecast.moments[0].at
        assert timedelta(days=9) < span < timedelta(days=11)


class TestOneMoment:
    def test_the_temperature(self, forecast: Forecast) -> None:
        assert forecast.moments[0].temperature == 13.2

    def test_the_wind(self, forecast: Forecast) -> None:
        first = forecast.moments[0]
        assert (first.wind_speed, first.wind_from) == (2.2, 206.0)

    def test_the_sky(self, forecast: Forecast) -> None:
        assert forecast.moments[0].cloud_cover == 99.9

    def test_the_rest_of_the_instant(self, forecast: Forecast) -> None:
        first = forecast.moments[0]
        assert (first.humidity, first.pressure) == (89.0, 1004.7)


class TestWhatItWillDo:
    """The symbol and the rainfall come from a block covering a period.

    Three are offered -- the next hour, the next six, the next twelve -- and
    which are present changes as the series coarsens. Taking the shortest
    available keeps the answer as specific as the data allows.
    """

    def test_the_symbol_for_the_hour_ahead(self, forecast: Forecast) -> None:
        assert forecast.moments[0].symbol == "cloudy"

    def test_how_much_rain_in_that_hour(self, forecast: Forecast) -> None:
        assert forecast.moments[0].precipitation == 0.0

    def test_what_period_that_describes(self, forecast: Forecast) -> None:
        #  Worth carrying: 1.7mm over six hours and 1.7mm in one are different
        #  weather, and a page saying only "1.7mm" would not distinguish them.
        assert forecast.moments[0].covers == timedelta(hours=1)

    def test_the_six_hour_block_is_used_once_the_hourly_one_stops(self, forecast: Forecast) -> None:
        #  The series turns from hourly to six-hourly part way along, which is
        #  the detail a made-up fixture would not have.
        coarse = [m for m in forecast.moments if m.covers == timedelta(hours=6)]
        assert coarse, "the captured response does coarsen"
        assert coarse[0].at > forecast.moments[0].at

    def test_the_last_moment_has_nothing_after_it_to_describe(self, forecast: Forecast) -> None:
        #  The final entry carries an instant and no block at all: there is no
        #  next hour inside the forecast to summarise.
        last = forecast.moments[-1]
        assert last.temperature is not None
        assert last.symbol is None
        assert last.covers is None


class TestAThinResponse:
    def test_a_missing_reading_is_absent_rather_than_zero(self) -> None:
        #  Nought degrees and no reading are different, and on a weather page
        #  the difference matters more than almost anywhere else.
        thin = {
            "properties": {
                "meta": {"updated_at": "2026-08-09T05:29:09Z"},
                "timeseries": [
                    {"time": "2026-08-09T05:00:00Z", "data": {"instant": {"details": {}}}}
                ],
            }
        }
        (moment,) = parse_forecast(thin).moments
        assert moment.temperature is None
        assert moment.wind_speed is None

    def test_a_response_with_no_moments_at_all_is_still_a_forecast(self) -> None:
        empty = {
            "properties": {
                "meta": {"updated_at": "2026-08-09T05:29:09Z"},
                "timeseries": [],
            }
        }
        assert parse_forecast(empty).moments == ()
