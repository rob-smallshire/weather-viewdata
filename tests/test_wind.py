"""A bearing, said in the letters a weather forecast says it in."""

import pytest

from weather_viewdata.wind import from_the


class TestSayingWhereTheWindIsFrom:
    @pytest.mark.parametrize(
        ("degrees", "expected"),
        [
            (0.0, "N"),
            (90.0, "E"),
            (180.0, "S"),
            (270.0, "W"),
            (45.0, "NE"),
            (225.0, "SW"),
            (22.5, "NNE"),
            (247.5, "WSW"),
        ],
    )
    def test_a_bearing_becomes_a_point_of_the_compass(
        self, degrees: float, expected: str
    ) -> None:
        assert from_the(degrees) == expected

    @pytest.mark.parametrize(
        ("degrees", "expected"),
        [
            (11.0, "N"),  # nearer north than north-north-east
            (12.0, "NNE"),  # and now the other way
            (350.0, "N"),
            (359.9, "N"),
        ],
    )
    def test_and_the_nearest_one_wins(self, degrees: float, expected: str) -> None:
        assert from_the(degrees) == expected

    @pytest.mark.parametrize("degrees", [360.0, 720.0, -90.0])
    def test_a_bearing_outside_the_circle_is_brought_back_into_it(
        self, degrees: float
    ) -> None:
        #  met.no sends 0 to 360, but a bearing is an angle and 360 is north.
        #  Refusing it would lose a reading over an arithmetic convention.
        assert from_the(degrees) in {"N", "W"}

    def test_no_reading_is_said_as_nothing_at_all(self) -> None:
        #  Not "N". A wind whose direction we do not know is not a north wind,
        #  and the row simply says less.
        assert from_the(None) == ""
