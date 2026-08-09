"""The weather as a picture, and the grammar that assembles one.

Eighty-three codes and about a dozen drawings. What is tested here is the
grammar rather than the art: which piece goes in which band, what colour it is
drawn in, and that every published code comes out as something. The art itself
is a matter for the eye and for a real screen.
"""

import csv
from pathlib import Path

import pytest

from sextile.viewdata.controls import Colour
from sextile.viewdata.wrapping import wrap_text
from weather_viewdata import build_application
from weather_viewdata.application import _WORD_CELLS
from weather_viewdata.forecast.model import Forecast
from weather_viewdata.forecast.source import ForecastSource
from weather_viewdata.geonames import Place
from weather_viewdata.icons import (
    BANDS,
    BOLT,
    CLOUD,
    CLOUD_SMALL,
    CLOUD_TOP,
    COLUMN_CELLS,
    EMPTY,
    FOG_FIGURE,
    MOON,
    MOON_FIGURE,
    SUN,
    SUN_FIGURE,
    SUN_LOW,
    SUN_SMALL,
    TWILIGHT_FIGURE,
    WeatherIcon,
    icon_for,
)
from weather_viewdata.store import Index
from weather_viewdata.symbols import PUBLISHED, in_words


def drawn(code: str) -> WeatherIcon:
    found = icon_for(code)
    assert found is not None, code
    return found


def lit(icon: WeatherIcon) -> int:
    """Blocks turned on, over the whole picture."""
    return sum(pattern.bit_count() for band in icon.bands for pattern in band.cells)


def codes() -> list[str]:
    filepath = Path(__file__).parent / "data" / "met-symbols.csv"
    with filepath.open(encoding="utf-8", newline="") as opened:
        return [row["Symbol ID"].strip() for row in csv.DictReader(opened)]


class TestEveryPublishedCodeHasAPicture:
    def test_all_of_them(self) -> None:
        for code in codes():
            assert icon_for(code) is not None, code

    def test_and_all_their_variants(self) -> None:
        for code in codes():
            for when in ("_day", "_night", "_polartwilight"):
                assert icon_for(code + when) is not None, code + when

    def test_each_is_three_bands_of_four_cells(self) -> None:
        #  Four cells to a band, attributes included, whether it spends them on
        #  three cells of picture in one colour or on two in two colours. A
        #  band that spent three or five would put the hour beneath it out of
        #  line with the picture above it.
        for code in codes():
            icon = drawn(code)
            assert len(icon.bands) == BANDS
            for band in icon.bands:
                assert sum(patch.width for patch in band.patches) == COLUMN_CELLS

    def test_a_code_we_cannot_read_has_no_picture_rather_than_a_guess(self) -> None:
        #  The words beside it still say what it is. Drawing the nearest
        #  weather we happen to know would be wrong with every appearance of
        #  confidence.
        assert icon_for("meteorshower") is None
        assert icon_for(None) is None


class TestTheSkyOnTop:
    """The top band says what is above the weather.

    Sun, moon, or the top of a cloud where there is no sky to be seen -- which
    is met.no's own distinction and not ours. They give `_day` and `_night`
    variants to exactly 21 ids, and those are exactly the ids with sky in them:
    the three states with nothing falling, and everything that falls in showers.
    """

    @pytest.mark.parametrize("code", ["fair_day", "partlycloudy_day"])
    def test_a_sky_that_is_mostly_sky_gets_a_sun_that_looks_like_one(
        self, code: str
    ) -> None:
        assert drawn(code).bands[0].cells == SUN

    @pytest.mark.parametrize(
        "code", ["rainshowers_day", "lightsnowshowers_day", "sleetshowers_day"]
    )
    def test_and_a_sun_over_falling_weather_is_a_smaller_one(self, code: str) -> None:
        #  A shower has a sun *between* the clouds rather than blazing over
        #  them, and the full-size disc over rain says the hour is mostly about
        #  the sun when it is mostly about the rain.
        assert drawn(code).bands[0].cells == SUN_SMALL

    @pytest.mark.parametrize("code", ["snowshowers_night", "partlycloudy_night"])
    def test_and_the_moon_at_night(self, code: str) -> None:
        assert drawn(code).bands[0].cells == MOON

    @pytest.mark.parametrize(
        "code", ["rainshowers_polartwilight", "partlycloudy_polartwilight"]
    )
    def test_polar_twilight_is_a_sun_that_has_not_got_up(self, code: str) -> None:
        #  Neither of the other two: the sun is below the horizon all day and
        #  the sky is lit anyway. A moon would be the wrong half of the year,
        #  and an ordinary sun would say nothing about where the reader is.
        #
        #  The same low sun whatever the weather -- where the sun does not get
        #  up, how high it is says more about the hour than the rain does.
        assert drawn(code).bands[0].cells == SUN_LOW

    def test_and_a_clear_one_sits_on_the_horizon(self) -> None:
        assert [band.cells for band in drawn("clearsky_polartwilight").bands] == list(
            TWILIGHT_FIGURE
        )

    @pytest.mark.parametrize("code", ["rain", "heavysnow", "cloudy", "sleetandthunder"])
    def test_continuous_weather_has_cloud_all_the_way_up(self, code: str) -> None:
        assert drawn(code).bands[0].cells == CLOUD_TOP

    def test_a_clear_sky_is_a_sun_and_nothing_else(self) -> None:
        #  Nothing to stack, so nothing is stacked: one picture across all nine
        #  cells. Small, a clear sky is a mark among marks; large, it is the one
        #  hour in a strip of ten that a reader picks out without reading.
        assert [band.cells for band in drawn("clearsky_day").bands] == list(SUN_FIGURE)
        assert drawn("clearsky_day").bands[0].colour == Colour.YELLOW

    def test_and_by_night_a_moon(self) -> None:
        assert [band.cells for band in drawn("clearsky_night").bands] == list(
            MOON_FIGURE
        )


class TestTheCloudInTheMiddle:
    @pytest.mark.parametrize(
        "code", ["partlycloudy_day", "cloudy", "rain", "heavysnow", "sleetshowers_day"]
    )
    def test_the_cloud_is_always_on_the_same_row(self, code: str) -> None:
        #  Which is why a dry hour leaves the bottom band empty instead of
        #  sitting lower: in a strip of hours side by side, a cloud line that
        #  moved up and down would read as weather changing when it is not.
        assert drawn(code).bands[1].cells == CLOUD

    def test_and_fair_weather_gets_less_of_one(self) -> None:
        #  A sky that is mostly not cloud, which is what the word means.
        assert drawn("fair_day").bands[1].cells == CLOUD_SMALL


class TestWhatIsFalling:
    @pytest.mark.parametrize(
        ("code", "colour"),
        [("rain", Colour.BLUE), ("snow", Colour.WHITE)],
    )
    def test_each_kind_has_its_own_colour(self, code: str, colour: Colour) -> None:
        assert drawn(code).bands[2].colour == colour

    def test_sleet_is_drawn_as_the_two_things_it_is(self) -> None:
        #  Sleet *is* snow and rain at once, and in one colour it could only be
        #  a compromise between them. It was cyan, which is the cloud's colour,
        #  so it said "cloud" more than it said "sleet". Now it is white beside
        #  blue, which is what it is.
        snow, rain = drawn("sleet").bands[2].patches
        assert (snow.colour, rain.colour) == (Colour.WHITE, Colour.BLUE)

    def test_and_nothing_that_falls_shares_a_colour_with_the_cloud(self) -> None:
        for code in ("rain", "snow", "sleet", "heavysleet"):
            for patch in drawn(code).bands[2].patches:
                assert patch.colour != drawn(code).bands[1].colour, code

    @pytest.mark.parametrize("kind", ["rain", "sleet", "snow"])
    def test_harder_weather_is_more_of_it(self, kind: str) -> None:
        #  The one rule a reader can learn without being told: more blocks means
        #  more weather. It holds for all three kinds and both steps.
        light = lit(drawn(f"light{kind}"))
        middling = lit(drawn(kind))
        heavy = lit(drawn(f"heavy{kind}"))
        assert light < middling < heavy

    def test_a_dry_hour_leaves_the_bottom_band_empty(self) -> None:
        for code in ("fair_day", "partlycloudy_day", "cloudy"):
            assert drawn(code).bands[2].cells == EMPTY

    def test_fog_is_drawn_through_all_three(self) -> None:
        #  The one weather that is not above the reader but around them, so it
        #  does not hang from a cloud. Drawn whole, so its bars are evenly
        #  spaced: three bands of one piece would put two of them side by side.
        assert [band.cells for band in drawn("fog").bands] == list(FOG_FIGURE)


class TestThunder:
    @pytest.mark.parametrize(
        "code", ["rainandthunder", "heavysnowshowersandthunder_day", "sleetandthunder"]
    )
    def test_the_bolt_sits_beside_the_fall_in_its_own_colour(self, code: str) -> None:
        #  The one row in an icon that spends a cell on a second colour, and
        #  the reason the cost is worth paying: six of the 41 symbols carry
        #  thunder, and drawn in the fall's colour they would differ from the
        #  plain ones by nothing at all.
        fall, bolt = drawn(code).bands[2].patches
        assert bolt.cells == BOLT
        assert bolt.colour == Colour.YELLOW
        assert fall.colour != Colour.YELLOW

    def test_and_it_still_costs_the_band_no_more_than_four_cells(self) -> None:
        #  Bought out of the picture rather than out of the column. The strip
        #  underneath keeps its pitch whatever the weather does.
        band = drawn("rainandthunder").bands[2]
        assert sum(patch.width for patch in band.patches) == COLUMN_CELLS
        assert len(band.cells) == 2

    @pytest.mark.parametrize("kind", ["rain", "sleet", "snow"])
    def test_harder_thunder_weather_is_still_more_of_it(self, kind: str) -> None:
        light = lit(drawn(f"light{kind}andthunder"))
        middling = lit(drawn(f"{kind}andthunder"))
        heavy = lit(drawn(f"heavy{kind}andthunder"))
        assert light < middling < heavy

    def test_the_cloud_above_it_is_unchanged(self) -> None:
        assert drawn("rainandthunder").bands[:2] == drawn("rain").bands[:2]


class TestTheLegendPage:
    """`*95#`, which is the whole set on four frames.

    The only way to judge a set of small pictures: one at a time they all look
    plausible, and side by side the two that cannot be told apart show up at
    once. It is also what a reader needs, since the table beside it says
    `sleet shwrs` and gives no other clue what the picture over it means.
    """

    async def test_every_published_symbol_is_on_it(self, tmp_path: Path) -> None:
        shown = await _legend(tmp_path)
        for code in PUBLISHED:
            #  The first line of the words, because the long ones wrap over two
            #  rows and would not be found whole.
            first = wrap_text(in_words(code), _WORD_CELLS)[0]
            assert first in shown, code

    async def test_and_the_four_sky_variants_after_them(self, tmp_path: Path) -> None:
        #  Shown rather than described. The words said what the time of day
        #  changes and a reader could not judge a picture from them.
        shown = await _legend(tmp_path)
        for said in ("clear at night", "clear in polar", "rain shwrs at"):
            assert said in shown, said

    async def test_and_no_name_is_cut_short(self, tmp_path: Path) -> None:
        #  A legend that truncated its own names would be unreadable exactly
        #  where it is most needed: `heavy sleet shwrs+thunder` is the longest
        #  thing met.no says and the one nobody could guess.
        shown = await _legend(tmp_path)
        assert "shwrs+thunder" in shown


async def _legend(tmp_path: Path) -> str:
    filepath = tmp_path / "places.sqlite"
    with Index.open(filepath) as index:
        index.add_places([])
    app = build_application(source=_NoForecasts(), index_filepath=filepath)
    await app.startup()
    try:
        page = await app.ask("95")
    finally:
        await app.shutdown()
    assert page is not None
    return "\n".join(
        line for frame in page.frames for line in frame.frame.to_grid()[0]
    )


class _NoForecasts(ForecastSource):
    async def forecast_for(self, place: Place) -> Forecast | None:
        del place
        return None
