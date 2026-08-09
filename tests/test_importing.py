"""Filling the index from a dump.

The import is the one long-running thing this service does -- two hundred
thousand places, once a week at most -- so what it reports and when it stops
matter more than they would for something a person watches.
"""

import zipfile
from pathlib import Path

import pytest

from weather_viewdata.importing import import_places
from weather_viewdata.store import Index

LINES = "\n".join(
    [
        "3133880\tTrondheim\tTrondheim\tNidaros\t63.43049\t10.39506\tP\tPPLA\tNO\t"
        "\t21\t5001\t\t\t147139\t\t14\tEurope/Oslo\t2023-03-08",
        "3161732\tBergen\tBergen\tBjørgvin\t60.39299\t5.32415\tP\tPPLA\tNO\t"
        "\t46\t4601\t\t\t213585\t\t9\tEurope/Oslo\t2023-03-08",
        "3143244\tOslo\tOslo\tChristiania\t59.91273\t10.74609\tP\tPPLC\tNO\t"
        "\t12\t0301\t\t\t580000\t\t14\tEurope/Oslo\t2023-03-08",
    ]
)


@pytest.fixture
def dump_filepath(tmp_path: Path) -> Path:
    path = tmp_path / "cities500.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("cities500.txt", LINES)
    return path


class TestImporting:
    def test_every_place_arrives(self, dump_filepath: Path) -> None:
        with Index.in_memory() as index:
            import_places(dump_filepath, index)
            assert index.held() == 3

    def test_it_says_how_many_it_took(self, dump_filepath: Path) -> None:
        with Index.in_memory() as index:
            assert import_places(dump_filepath, index) == 3

    def test_they_can_be_found_afterwards(self, dump_filepath: Path) -> None:
        with Index.in_memory() as index:
            import_places(dump_filepath, index)
            assert [found.name for found in index.matching("OSL")] == ["Oslo"]

    def test_importing_twice_leaves_one_of_each(self, dump_filepath: Path) -> None:
        with Index.in_memory() as index:
            import_places(dump_filepath, index)
            import_places(dump_filepath, index)
            assert index.held() == 3

    def test_progress_is_reported_as_it_goes(self, dump_filepath: Path) -> None:
        #  Two hundred thousand places is a minute or so, and a command that
        #  says nothing for a minute looks like one that has hung.
        seen: list[int] = []
        with Index.in_memory() as index:
            import_places(dump_filepath, index, batch=2, progress=seen.append)
        assert seen == [2, 3]

    def test_the_preferred_country_is_honoured(self, dump_filepath: Path) -> None:
        #  Set before the places arrive, the ranking being computed on the way
        #  in. An importer that set it afterwards would rank nothing.
        with Index.in_memory() as index:
            import_places(dump_filepath, index, prefer_country="NO")
            (first,) = index.matching("OSLO")
            assert first.name == "Oslo"
