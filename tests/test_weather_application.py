"""The service refusing to serve an index it would answer wrongly from.

The index is derived data and the rules that derive it live in code, so a
change to them does nothing until somebody re-imports. Until they do, the
service answers by the old rules and says nothing about it -- which is how
keying A went on offering Cairo long after alternate names had stopped being
indexed.
"""

from pathlib import Path

import pytest

from sextile import PageAddress
from sextile.session.session import Session
from weather_viewdata import build_application
from weather_viewdata.application import StaleIndexError
from weather_viewdata.forecast.model import Forecast
from weather_viewdata.forecast.source import ForecastSource
from weather_viewdata.geonames import Place
from weather_viewdata.store import RULES, Index

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


class NoForecasts(ForecastSource):
    async def forecast_for(self, place: Place) -> Forecast | None:
        return None


class TestRefusingAStaleIndex:
    async def test_a_current_index_serves(self, tmp_path: Path) -> None:
        filepath = tmp_path / "places.sqlite"
        with Index.open(filepath) as index:
            index.add_places([TRONDHEIM])
        app = build_application(source=NoForecasts(), index_filepath=filepath)
        await app.startup()
        assert await app.ask("1") is not None
        await app.shutdown()

    async def test_one_built_by_older_rules_does_not(self, tmp_path: Path) -> None:
        filepath = tmp_path / "places.sqlite"
        with Index.open(filepath) as index:
            index.add_places([TRONDHEIM])
            index.stamp(RULES - 1)
        app = build_application(source=NoForecasts(), index_filepath=filepath)
        with pytest.raises(StaleIndexError):
            await app.startup()

    async def test_and_says_what_to_run(self, tmp_path: Path) -> None:
        #  A refusal that does not say how to fix it is only half a refusal.
        filepath = tmp_path / "places.sqlite"
        with Index.open(filepath) as index:
            index.add_places([TRONDHEIM])
            index.stamp(RULES - 1)
        app = build_application(source=NoForecasts(), index_filepath=filepath)
        with pytest.raises(StaleIndexError, match="import-places"):
            await app.startup()

    async def test_an_index_that_was_never_built_is_not_stale(
        self, tmp_path: Path
    ) -> None:
        #  A first run has an empty file and nothing to be out of date about.
        #  It will say it holds no places, which is true and is a different
        #  complaint.
        app = build_application(
            source=NoForecasts(), index_filepath=tmp_path / "places.sqlite"
        )
        await app.startup()
        await app.shutdown()


class TestHowAForecastIsDrawnIsPartOfItsNumber:
    """The third digit, and why it is the third.

    The same weather can be a table or a graph, and neither is the poor
    relation, so the presentation is in the address rather than a mode the
    reader has to get the frame into: a number written down fetches back what
    was written down.

    It sits before the subject because a geoname id has no fixed width, and a
    digit after one could not be told from the id itself.
    """

    def test_a_place_is_numbered_by_its_presentation_then_its_id(self) -> None:
        app = build_application(source=NoForecasts())
        assert app.address_for("place", geoname_id=3133880) == PageAddress(
            "321" + "3133880"
        )

    def test_a_point_likewise_and_then_its_position(self) -> None:
        app = build_application(source=NoForecasts())
        assert app.address_for("point", lat=63.43049, lon=10.39506) == PageAddress(
            "421" + "1534" + "1904"
        )


class TestBothWaysOfWritingACoordinate:
    """The signs are undocumented rather than unsupported.

    A field's advice sits under it on every frame, so it is read far more often
    than it is needed and had better be short. It shows the hemispheric
    spelling only -- which teaches the reader who does not know -- while the
    signed one goes on working for the reader who does.

    Here so that nobody tidies the parser to match the hint.
    """

    @pytest.mark.parametrize(
        ("latitude", "longitude"),
        [
            ("54.0N", "1.1W"),  # as the hint shows it
            ("54.0", "-1.1"),  # and as it does not
            ("54.0N", "-1.1"),  # and one of each
        ],
    )
    async def test_either_spelling_reaches_the_same_point(
        self, latitude: str, longitude: str, tmp_path: Path
    ) -> None:
        filepath = tmp_path / "places.sqlite"
        with Index.open(filepath) as index:
            index.add_places([TRONDHEIM])
        app = build_application(source=NoForecasts(), index_filepath=filepath)
        await app.startup()
        session = Session(app, start=PageAddress("4"))
        await session.greeting()
        await session.receive(latitude.encode())
        await session.receive(b"\x09")
        await session.receive(longitude.encode())
        await session.receive(b"\x5f")
        assert session.address == PageAddress("42114401789")
        await app.shutdown()
