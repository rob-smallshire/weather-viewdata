"""The service refusing to serve an index it would answer wrongly from.

The index is derived data and the rules that derive it live in code, so a
change to them does nothing until somebody re-imports. Until they do, the
service answers by the old rules and says nothing about it -- which is how
keying A went on offering Cairo long after alternate names had stopped being
indexed.
"""

from pathlib import Path

import pytest

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
