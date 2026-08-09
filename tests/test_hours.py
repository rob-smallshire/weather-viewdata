"""The charts under the hour strip.

What is worth testing is the scaling rather than the drawing: where freezing
lands, what a millimetre of rain looks like, and that a still day is not drawn
as a gale. The shapes themselves are a matter for the eye and a real screen.
"""

import pytest

from weather_viewdata.hours import rain_level, warmth_scale


class TestWhereFreezingGoes:
    """One colour to a row, so nought degrees can only be at a row boundary.

    That is the whole of the temperature scale: fixing freezing at a third or
    two thirds of the height fixes everything else, and the choice between the
    two is whichever leaves less of the chart empty.
    """

    def test_a_series_all_above_freezing_is_warm_throughout(self) -> None:
        low, high, warm = warmth_scale(13, 20)
        assert (low, high) == (13, 20)
        assert warm == 3

    def test_and_one_all_below_it_is_cold_throughout(self) -> None:
        low, high, warm = warmth_scale(-10, -2)
        assert (low, high) == (-10, -2)
        assert warm == 0

    def test_a_series_that_crosses_puts_freezing_on_a_boundary(self) -> None:
        #  -3 to 6 is three below and six above: freezing a third of the way
        #  up, which is where a third of nine blocks falls exactly.
        low, high, warm = warmth_scale(-3, 6)
        assert low == pytest.approx(-3)
        assert high == pytest.approx(6)
        assert warm == 2

    def test_and_the_other_boundary_where_that_fits_better(self) -> None:
        low, high, warm = warmth_scale(-6, 3)
        assert low == pytest.approx(-6)
        assert high == pytest.approx(3)
        assert warm == 1

    @pytest.mark.parametrize(
        ("coldest", "warmest"), [(-9, 1), (-1, 9), (-2, 7), (-7, 2), (-5, 5)]
    )
    def test_the_axis_always_holds_the_data(
        self, coldest: float, warmest: float
    ) -> None:
        low, high, _ = warmth_scale(coldest, warmest)
        assert low <= coldest
        assert high >= warmest

    @pytest.mark.parametrize(
        ("coldest", "warmest"), [(-9, 1), (-1, 9), (-2, 7), (-7, 2), (-3, 6)]
    )
    def test_and_freezing_lands_exactly_on_a_row(
        self, coldest: float, warmest: float
    ) -> None:
        #  Not near a row: on one. A block either side of the line would be
        #  drawn in the wrong colour, and the wrong colour here says the wrong
        #  thing about ice.
        low, high, warm = warmth_scale(coldest, warmest)
        assert (0 - low) / (high - low) == pytest.approx((3 - warm) / 3)

    def test_a_tie_goes_to_the_lower_boundary(self) -> None:
        #  A series as far below freezing as above fits either way and wastes
        #  the same either way. Deciding it deliberately is worth more than
        #  which way it is decided.
        low, high, warm = warmth_scale(-3, 3)
        assert low == pytest.approx(-3)
        assert high == pytest.approx(6)
        assert warm == 2

    def test_a_day_that_never_moves_is_not_drawn_on_the_floor(self) -> None:
        #  A flat line along the bottom reads as cold rather than as steady.
        low, high, _ = warmth_scale(2, 2)
        assert high - low >= 2


class TestHowMuchRain:
    """Four levels, and they are millimetres rather than fractions.

    Scaled to the series, one wet hour among seven dry ones is drawn full
    height whether it held a drizzle or a downpour. Fixed, the same bar is the
    same rain on every page a reader ever fetches.
    """

    @pytest.mark.parametrize(
        ("millimetres", "level"),
        [(0.0, 0), (0.05, 0), (0.1, 1), (0.9, 1), (1.0, 2), (3.9, 2), (4.0, 3), (20.0, 3)],
    )
    def test_the_thresholds(self, millimetres: float, level: int) -> None:
        assert rain_level(millimetres) == level

    def test_no_reading_is_not_a_dry_hour(self) -> None:
        #  As everywhere else: nought millimetres is weather and no reading is
        #  not, and a bar of nothing would say the first.
        assert rain_level(None) is None
