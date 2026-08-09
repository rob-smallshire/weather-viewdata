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
    CELLS_ACROSS,
    CLOUD,
    CLOUD_SMALL,
    CLOUD_TOP,
    EMPTY,
    FOG,
    MOON,
    SUN,
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

    def test_each_is_three_bands_of_three_cells(self) -> None:
        #  Which is what the four-cell hour column affords: an attribute and
        #  three cells of picture, on each of three rows.
        for code in codes():
            icon = drawn(code)
            assert len(icon.bands) == BANDS
            for band in icon.bands:
                assert len(band.cells) == CELLS_ACROSS

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

    @pytest.mark.parametrize(
        "code", ["clearsky_day", "fair_day", "partlycloudy_day", "rainshowers_day"]
    )
    def test_the_sun_shows_where_there_are_breaks_in_the_weather(
        self, code: str
    ) -> None:
        icon = drawn(code)
        assert SUN in (icon.bands[0].cells, icon.bands[1].cells)

    @pytest.mark.parametrize("code", ["clearsky_night", "snowshowers_night"])
    def test_and_the_moon_at_night(self, code: str) -> None:
        icon = drawn(code)
        assert MOON in (icon.bands[0].cells, icon.bands[1].cells)

    def test_polar_twilight_keeps_the_sun(self) -> None:
        #  The sun is up in some sense or met.no would have said night. Drawing
        #  a moon in Tromsø in November would be the wrong half of the year.
        assert drawn("rainshowers_polartwilight").bands[0].cells == SUN

    @pytest.mark.parametrize("code", ["rain", "heavysnow", "cloudy", "sleetandthunder"])
    def test_continuous_weather_has_cloud_all_the_way_up(self, code: str) -> None:
        assert drawn(code).bands[0].cells == CLOUD_TOP

    def test_a_clear_sky_puts_the_sun_in_the_middle(self) -> None:
        #  There is nothing else in the picture, so it sits square in the
        #  column rather than perched at the top of it.
        icon = drawn("clearsky_day")
        assert icon.bands[0].cells == EMPTY
        assert icon.bands[1].cells == SUN


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
        [
            ("rain", Colour.BLUE),
            ("sleet", Colour.CYAN),
            ("snow", Colour.WHITE),
        ],
    )
    def test_each_kind_has_its_own_colour(self, code: str, colour: Colour) -> None:
        assert drawn(code).bands[2].colour == colour

    @pytest.mark.parametrize("kind", ["rain", "sleet", "snow"])
    def test_harder_weather_is_more_of_it(self, kind: str) -> None:
        #  The one rule a reader can learn without being told: more blocks means
        #  more weather. It holds for all three kinds and both steps.
        light = lit(drawn(f"light{kind}"))
        middling = lit(drawn(kind))
        heavy = lit(drawn(f"heavy{kind}"))
        assert light < middling < heavy

    def test_a_dry_hour_leaves_the_bottom_band_empty(self) -> None:
        for code in ("clearsky_day", "fair_day", "partlycloudy_day", "cloudy"):
            assert drawn(code).bands[2].cells == EMPTY

    def test_fog_is_drawn_through_all_three(self) -> None:
        #  The one weather that is not above the reader but around them, so it
        #  does not hang from a cloud.
        assert [band.cells for band in drawn("fog").bands] == [FOG] * BANDS


class TestThunder:
    @pytest.mark.parametrize(
        "code", ["rainandthunder", "heavysnowshowersandthunder_day", "sleetandthunder"]
    )
    def test_it_takes_the_bottom_band_and_turns_it_yellow(self, code: str) -> None:
        #  There is no room for a bolt beside the rain and no second colour to
        #  draw it in if there were: one colour to a row is what an attribute
        #  costing a cell leaves us with. So thunder replaces the fall, and the
        #  band changing colour is what says so at a glance.
        icon = drawn(code)
        assert icon.bands[2].cells == BOLT
        assert icon.bands[2].colour == Colour.YELLOW

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
