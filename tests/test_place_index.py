"""The place index, and what it puts first.

Three suggestions is what the wire affords, which makes ranking the whole game:
with nine, a mediocre order still shows the reader what they wanted somewhere on
the list. With three it either offers the right place or it does not.
"""

from collections.abc import Iterator

import pytest

from weather_viewdata.geonames import Place
from weather_viewdata.store import Index


def place(
    geoname_id: int,
    name: str,
    *,
    country: str = "NO",
    population: int = 0,
    feature_code: str = "PPL",
    alternates: tuple[str, ...] = (),
) -> Place:
    return Place(
        geoname_id=geoname_id,
        name=name,
        ascii_name=name,
        alternate_names=alternates,
        latitude=0.0,
        longitude=0.0,
        feature_class="P",
        feature_code=feature_code,
        country=country,
        admin1="",
        population=population,
        elevation=None,
        timezone="Europe/Oslo",
    )


TRONDHEIM = place(3133880, "Trondheim", population=147139, feature_code="PPLA")
TROMSO = place(3133895, "Tromsø", population=64182, feature_code="PPLA")
BERGEN = place(3161732, "Bergen", population=213585, feature_code="PPLA")
BERLIN = place(2950159, "Berlin", country="DE", population=3426354, feature_code="PPLC")
MUNCHEN = place(
    2867714, "München", country="DE", population=1260391,
    feature_code="PPLA", alternates=("Munich", "Monaco di Baviera"),
)
TROY = place(5141502, "Troy", country="US", population=49928)


@pytest.fixture
def index() -> Iterator[Index]:
    with Index.in_memory() as held:
        held.add_places([TRONDHEIM, TROMSO, BERGEN, BERLIN, MUNCHEN, TROY])
        yield held


class TestFindingAPlace:
    def test_by_the_letters_of_its_own_name(self, index: Index) -> None:
        assert [found.name for found in index.matching("TRONDHEIM")] == ["Trondheim"]

    def test_by_a_prefix_of_it(self, index: Index) -> None:
        assert "Trondheim" in [found.name for found in index.matching("TROND")]

    def test_by_a_name_the_keypad_cannot_spell(self, index: Index) -> None:
        #  The whole reason the fold exists: there is no ø on a Beeb.
        assert [found.name for found in index.matching("TROMSO")] == ["Tromsø"]

    def test_by_a_name_it_goes_by_elsewhere(self, index: Index) -> None:
        #  A reader who knows it as Munich should not have to know it is not.
        assert [found.name for found in index.matching("MUNICH")] == ["München"]

    def test_by_its_own_spelling_too(self, index: Index) -> None:
        assert [found.name for found in index.matching("MUNCHEN")] == ["München"]

    def test_a_place_is_offered_once_however_many_names_match(
        self, index: Index
    ) -> None:
        #  München answers to Munich, Monaco di Baviera and its own name. A
        #  suggestion list with the same place three times wastes two of three
        #  rows a reader has.
        assert [found.name for found in index.matching("M")].count("München") == 1

    def test_a_query_matching_nothing_finds_nothing(self, index: Index) -> None:
        assert list(index.matching("ZZZZ")) == []

    def test_an_empty_query_finds_nothing(self, index: Index) -> None:
        #  Rather than the whole world in population order, which is not a
        #  search result but a distraction on a page that has three rows.
        assert list(index.matching("")) == []


class TestWhatComesFirst:
    def test_the_bigger_place_of_two(self, index: Index) -> None:
        assert [found.name for found in index.matching("TRO")][0] == "Trondheim"

    def test_only_as_many_as_the_frame_can_hold(self, index: Index) -> None:
        assert len(list(index.matching("TRO", limit=3))) <= 3

    def test_an_exact_name_beats_a_longer_one_that_starts_with_it(self) -> None:
        #  Somebody keying BERGEN wants Bergen, even though Bergensbanen or a
        #  larger Bergenfield would sort above it on population alone.
        with Index.in_memory() as index:
            index.add_places(
                [BERGEN, place(1, "Bergenfield", country="US", population=9000000)]
            )
            assert [found.name for found in index.matching("BERGEN")][0] == "Bergen"

    def test_a_capital_outranks_a_village_of_the_same_size(self) -> None:
        with Index.in_memory() as index:
            index.add_places([
                place(1, "Aville", population=50000, feature_code="PPL"),
                place(2, "Acity", population=50000, feature_code="PPLC"),
            ])
            assert [found.name for found in index.matching("A")][0] == "Acity"


class TestPreferringSomewhere:
    """Whose weather this service is mostly about.

    Left as a setting rather than baked in: BER finds Berlin before Bergen on
    population alone, and whether that is right depends on who is dialling.
    """

    def test_by_default_size_decides(self, index: Index) -> None:
        assert [found.name for found in index.matching("BER")][0] == "Berlin"

    def test_a_preferred_country_comes_up_first(self) -> None:
        with Index.in_memory() as index:
            index.prefer(country="NO")
            index.add_places([BERGEN, BERLIN])
            assert [found.name for found in index.matching("BER")][0] == "Bergen"

    def test_but_it_does_not_hide_anywhere_else(self) -> None:
        with Index.in_memory() as index:
            index.prefer(country="NO")
            index.add_places([BERGEN, BERLIN])
            assert "Berlin" in [found.name for found in index.matching("BER")]


class TestKeepingThePlacesThemselves:
    def test_a_place_is_fetched_by_its_geonames_number(self, index: Index) -> None:
        found = index.place(3133880)
        assert found is not None
        assert found.name == "Trondheim"

    def test_a_number_the_index_has_not_got_fetches_nothing(self, index: Index) -> None:
        assert index.place(999999) is None

    def test_what_was_stored_comes_back_whole(self) -> None:
        with Index.in_memory() as index:
            index.add_places([MUNCHEN])
            assert index.place(2867714) == MUNCHEN

    def test_importing_the_same_place_twice_holds_it_once(self, index: Index) -> None:
        #  A re-import of a fresh dump should replace rather than double.
        index.add_places([TRONDHEIM])
        assert len(list(index.matching("TRONDHEIM"))) == 1

    def test_a_place_with_no_keyable_name_is_left_out_of_the_index(self) -> None:
        #  1770, in Queensland. It has a page number and no way to be typed,
        #  and an empty key in the index is one every query matches.
        with Index.in_memory() as index:
            index.add_places([place(1, "1770", country="AU")])
            assert list(index.matching("A")) == []
            assert index.place(1) is not None
