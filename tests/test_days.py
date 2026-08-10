"""A forecast gathered into days and periods.

The scaling and the gathering are what is worth testing; the drawing is a
matter for the eye. What matters most here is the clock: met.no's six-hour
blocks are on the meridian and the reader's periods are not.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from weather_viewdata.days import PERIODS, days_of
from weather_viewdata.forecast.model import Moment

OSLO = ZoneInfo("Europe/Oslo")  # +2 in August
KARACHI = ZoneInfo("Asia/Karachi")  # +5, all year
DENVER = ZoneInfo("America/Denver")  # -6 in August

MIDNIGHT = datetime(2026, 8, 10, 0, 0, tzinfo=UTC)


def blocks(count: int = 4, **readings: float) -> list[Moment]:
    """met.no's far end: six-hour blocks on the meridian, 00/06/12/18 UTC."""
    return [
        Moment(
            at=MIDNIGHT + timedelta(hours=6 * step),
            covers=timedelta(hours=6),
            symbol="cloudy",
            **readings,
        )
        for step in range(count)
    ]


class TestWhichPeriodABlockBelongsTo:
    """met.no's blocks are on the meridian and the periods are not.

    Six hours from *local* midnight is what `night` and `afternoon` mean to
    somebody looking out of a window, and a block from 06:00 UTC is a morning
    in Oslo, an afternoon in Karachi and a night in Denver.
    """

    def test_at_greenwich_the_blocks_are_the_periods(self) -> None:
        gathered = days_of(blocks(), ZoneInfo("Etc/UTC"))
        assert len(gathered) == 1
        assert all(symbol == "cloudy" for symbol in gathered[0].periods)

    @pytest.mark.parametrize("zone", [OSLO, KARACHI, DENVER])
    def test_and_elsewhere_there_is_still_one_to_a_period(self, zone: ZoneInfo) -> None:
        #  The blocks are six hours apart and the periods six hours wide, so
        #  one lands in each however far round the world the place is. What
        #  changes is *which*, and that is what the middle rule settles.
        held = [day.periods for day in days_of(blocks(8), zone)]
        assert sum(1 for periods in held for symbol in periods if symbol) == 8

    def test_a_block_goes_where_its_middle_falls_and_not_its_start(self) -> None:
        #  Karachi is five ahead: the 06:00 UTC block is 11:00 to 17:00 there,
        #  one hour of morning and five of afternoon. By its start it would be
        #  a morning; it is an afternoon.
        morning = Moment(
            at=MIDNIGHT + timedelta(hours=6),
            covers=timedelta(hours=6),
            symbol="rain",
        )
        day = days_of([morning], KARACHI)[0]
        assert day.periods[PERIODS.index("aft")] == "rain"
        assert day.periods[PERIODS.index("mrn")] is None

    def test_and_the_same_block_is_a_night_further_west(self) -> None:
        #  Denver is six behind: 00:00 to 06:00 there, which is a night.
        morning = Moment(
            at=MIDNIGHT + timedelta(hours=6),
            covers=timedelta(hours=6),
            symbol="rain",
        )
        day = days_of([morning], DENVER)[0]
        assert day.periods[PERIODS.index("ngt")] == "rain"


class TestWhichSymbolStandsForAPeriod:
    def test_a_block_covering_the_period_is_met_nos_own_summary(self) -> None:
        #  Better than anything we could work out from the readings.
        block = Moment(at=MIDNIGHT, covers=timedelta(hours=6), symbol="fair_day")
        hour = Moment(at=MIDNIGHT, covers=timedelta(hours=1), symbol="heavyrain")
        day = days_of([hour, block], ZoneInfo("Etc/UTC"))[0]
        assert day.periods[0] == "fair_day"

    def test_and_where_there_is_none_the_worst_hour_wins(self) -> None:
        #  A reader asking what the morning will be like is asking whether they
        #  will get wet. An average of six hours answers a question nobody
        #  asked.
        hours = [
            Moment(
                at=MIDNIGHT + timedelta(hours=hour),
                covers=timedelta(hours=1),
                symbol="clearsky_day" if hour else "heavysleet",
            )
            for hour in range(6)
        ]
        day = days_of(hours, ZoneInfo("Etc/UTC"))[0]
        assert day.periods[0] == "heavysleet"


class TestTheDaysFigures:
    def test_the_high_the_low_the_rain_and_the_strongest_wind(self) -> None:
        moments = [
            Moment(
                at=MIDNIGHT + timedelta(hours=6 * step),
                covers=timedelta(hours=6),
                temperature=temperature,
                precipitation=1.5,
                wind_speed=wind,
                symbol="cloudy",
            )
            for step, (temperature, wind) in enumerate(
                [(11.0, 2.0), (18.0, 9.0), (16.0, 4.0), (12.0, 3.0)]
            )
        ]
        day = days_of(moments, ZoneInfo("Etc/UTC"))[0]
        assert (day.warmest, day.coldest) == (18.0, 11.0)
        assert day.rain == pytest.approx(6.0)
        assert day.wind == 9.0

    def test_a_day_with_no_readings_says_so_rather_than_nought(self) -> None:
        day = days_of(blocks(1), ZoneInfo("Etc/UTC"))[0]
        assert day.warmest is None
        assert day.rain is None


class TestWhichDaysAreShown:
    def test_today_comes_first_however_little_of_it_is_left(self) -> None:
        evening = [
            Moment(at=MIDNIGHT + timedelta(hours=hours), covers=timedelta(hours=1))
            for hours in (22, 23)
        ]
        gathered = days_of(evening, ZoneInfo("Etc/UTC"), from_day=date(2026, 8, 10))
        assert [day.on for day in gathered] == [date(2026, 8, 10)]

    def test_and_a_day_that_is_over_is_not_shown_at_all(self) -> None:
        #  A forecast held over the turn of a day would otherwise open on an
        #  afternoon that has been and gone.
        held = blocks(8)
        gathered = days_of(held, ZoneInfo("Etc/UTC"), from_day=date(2026, 8, 11))
        assert [day.on for day in gathered] == [date(2026, 8, 11)]
