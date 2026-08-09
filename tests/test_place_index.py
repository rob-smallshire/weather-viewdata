"""The place index, and what it puts first.

Three suggestions is what the wire affords, which makes ranking the whole game:
with nine, a mediocre order still shows the reader what they wanted somewhere on
the list. With three it either offers the right place or it does not.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from weather_viewdata.geonames import Place
from weather_viewdata.places import search_key
from weather_viewdata.store import RULES, Index


def place(
    geoname_id: int,
    name: str,
    *,
    country: str = "NO",
    population: int = 0,
    feature_code: str = "PPL",
    alternates: tuple[str, ...] = (),
    at: tuple[float, float] = (0.0, 0.0),
) -> Place:
    return Place(
        geoname_id=geoname_id,
        name=name,
        ascii_name=name,
        alternate_names=alternates,
        latitude=at[0],
        longitude=at[1],
        feature_class="P",
        feature_code=feature_code,
        country=country,
        admin1="",
        population=population,
        elevation=None,
        timezone="Europe/Oslo",
    )


#: Real positions, so that "nearest" means something here.
TRONDHEIM = place(3133880, "Trondheim", population=147139, feature_code="PPLA",
                  at=(63.43049, 10.39506))
TROMSO = place(3133895, "Tromsø", population=64182, feature_code="PPLA",
               at=(69.6489, 18.95508))
BERGEN = place(3161732, "Bergen", population=213585, feature_code="PPLA",
               at=(60.39299, 5.32415))
BERLIN = place(2950159, "Berlin", country="DE", population=3426354,
               feature_code="PPLC", at=(52.52437, 13.41053))
MUNCHEN = place(
    2867714, "München", country="DE", population=1260391,
    feature_code="PPLA", alternates=("Munich", "Monaco di Baviera"),
    at=(48.13743, 11.57549),
)
TROY = place(5141502, "Troy", country="US", population=49928, at=(42.72842, -73.69178))
NEW_YORK = place(5128581, "New York City", country="US", population=8804190,
                 feature_code="PPLA2", at=(40.71427, -74.00597))


@pytest.fixture
def index() -> Iterator[Index]:
    with Index.in_memory() as held:
        held.add_places([TRONDHEIM, TROMSO, BERGEN, BERLIN, MUNCHEN, TROY, NEW_YORK])
        yield held


class TestFindingAPlace:
    def test_by_the_letters_of_its_own_name(self, index: Index) -> None:
        assert [found.name for found in index.matching("TRONDHEIM")] == ["Trondheim"]

    def test_by_a_prefix_of_it(self, index: Index) -> None:
        assert "Trondheim" in [found.name for found in index.matching("TROND")]

    def test_by_a_name_the_keypad_cannot_spell(self, index: Index) -> None:
        #  The whole reason the fold exists: there is no ø on a Beeb.
        assert [found.name for found in index.matching("TROMSO")] == ["Tromsø"]

    def test_but_not_by_a_name_it_only_goes_by_elsewhere(self, index: Index) -> None:
        #  Alternate names are not indexed, so this finds nothing here. It
        #  matters less than it looks: GeoNames files Munich under `Munich`,
        #  and Vienna, Prague, Rome, Moscow and Tokyo under theirs. Koln is the
        #  exception the fixture keeps, and the note in `_keys_for` says what
        #  it would take to have both.
        assert list(index.matching("MUNICH")) == []

    def test_by_its_own_spelling_too(self, index: Index) -> None:
        assert [found.name for found in index.matching("MUNCHEN")] == ["München"]

    def test_a_place_is_offered_once(self, index: Index) -> None:
        #  Its name and its ascii name usually fold to the same key. A
        #  suggestion list with the same place twice wastes a row of three.
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

    def test_a_preferred_country_breaks_a_tie(self) -> None:
        #  Between comparable places. A nudge worth a tenfold of population,
        #  not an override: this is a global service whose readers mostly
        #  happen to be in one country.
        with Index.in_memory() as index:
            index.prefer(country="GB")
            index.add_places([
                place(1, "Boston", country="GB", population=41340),
                place(2, "Bostonia", country="US", population=41000),
            ])
            assert [found.name for found in index.matching("BOSTON")][0] == "Boston"

    def test_but_does_not_overturn_a_much_larger_place(self) -> None:
        #  Boston, Lincolnshire is not what a reader keying BOSTON means, and a
        #  preference strong enough to say otherwise is too strong.
        with Index.in_memory() as index:
            index.prefer(country="GB")
            index.add_places([
                place(1, "Boston", country="GB", population=41340),
                place(2, "Boston", country="US", population=654776,
                      feature_code="PPLA2"),
            ])
            assert [found.country for found in index.matching("BOSTON")][0] == "US"

    def test_and_never_hides_anywhere_else(self) -> None:
        with Index.in_memory() as index:
            index.prefer(country="GB")
            index.add_places([BERGEN, BERLIN])
            assert {found.name for found in index.matching("BER")} == {"Bergen", "Berlin"}


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


class TestExactnessIsWorthSomethingRatherThanEverything:
    """A hamlet with a three-letter alias should not outrank a capital.

    Exactness began as an absolute tiebreak, which is right for BERGEN against
    Bergenfield and wrong for everything else: Lognes carries the alternate
    `Lon'` and beat London, and Beure carries `Ber` and beat Bergen. So it is a
    bonus added to the ranking rather than a sort before it.
    """

    def test_an_exact_match_still_wins_between_comparable_places(self) -> None:
        with Index.in_memory() as index:
            index.add_places(
                [BERGEN, place(1, "Bergenfield", country="US", population=9000000)]
            )
            assert [found.name for found in index.matching("BERGEN")][0] == "Bergen"

    def test_but_not_between_a_hamlet_and_a_city(self) -> None:
        with Index.in_memory() as index:
            index.add_places([
                place(1, "London", country="GB", population=8961989, feature_code="PPLC"),
                place(2, "Lognes", country="FR", population=15519, alternates=("Lon'",)),
            ])
            assert [found.name for found in index.matching("LON")][0] == "London"

    def test_nor_between_a_village_and_a_city(self) -> None:
        with Index.in_memory() as index:
            index.add_places([
                BERGEN,
                place(2, "Beure", country="FR", population=1430, alternates=("Ber",)),
            ])
            assert [found.name for found in index.matching("BER")][0] == "Bergen"


class TestTheNearestPlaceToAPoint:
    """A coordinate page has no name, no clock and no altitude.

    It borrows a name and a clock from whatever is nearest, because timezone
    borders follow habitation and there is no way to know one from coordinates
    alone without shipping a boundary dataset for the Arctic Ocean.
    """

    def test_a_point_in_a_town_finds_that_town(self, index: Index) -> None:
        found = index.nearest(63.43, 10.40)
        assert found is not None
        assert found.name == "Trondheim"

    def test_a_point_between_two_finds_the_closer(self) -> None:
        with Index.in_memory() as index:
            index.add_places([
                place(1, "Near", at=(60.0, 5.0)),
                place(2, "Far", at=(60.9, 5.0)),
            ])
            found = index.nearest(60.1, 5.0)
            assert found is not None
            assert found.name == "Near"

    def test_size_does_not_decide_it(self) -> None:
        #  Unlike a search. The nearest place is a question about distance, and
        #  a big city half an hour away is the wrong answer to it.
        with Index.in_memory() as index:
            index.add_places([
                place(1, "Hamlet", at=(60.0, 5.0)),
                place(2, "Metropolis", population=9_000_000, at=(60.5, 5.0)),
            ])
            found = index.nearest(60.02, 5.0)
            assert found is not None
            assert found.name == "Hamlet"

    def test_longitude_is_scaled_by_the_latitude(self) -> None:
        #  A degree of longitude is half a degree of latitude at sixty north.
        #  Unscaled, the two below are equidistant and the tie falls to
        #  whichever the table yields first; scaled, north is plainly closer.
        with Index.in_memory() as index:
            index.add_places([
                place(1, "North", at=(60.2, 5.0)),
                place(2, "East", at=(60.0, 5.2)),
            ])
            found = index.nearest(60.0, 5.0)
            assert found is not None
            assert found.name == "East"

    def test_the_middle_of_an_ocean_finds_nothing(self, index: Index) -> None:
        #  Rather than the nearest place on earth, which could be a thousand
        #  miles away and would put the wrong clock on the page.
        assert index.nearest(0.0, -140.0) is None


class TestEveryResultBeginsWithWhatWasTyped:
    """The rule the whole search rests on, and it was not always kept.

    Alternate names were indexed once. Keying `A` then offered Oslo -- one of
    its alternates is `Asloa` -- and a reader shown a place whose name does not
    begin with what they typed has no way to work out why. What they type is a
    prefix, and it is honoured as one.
    """

    @pytest.mark.parametrize("typed", ["A", "TR", "M", "B", "BER"])
    def test_whatever_is_offered_starts_with_it(self, typed: str, index: Index) -> None:
        for found in index.matching(typed, limit=9):
            assert search_key(found.name).startswith(typed), f"{found.name} for {typed}"

    def test_an_alternate_name_does_not_find_a_place(self, index: Index) -> None:
        #  Munchen goes by Monaco di Baviera. Keying MONACO must not offer it,
        #  or a reader looking for the principality is shown Germany.
        assert "München" not in [found.name for found in index.matching("MONACO")]

    def test_the_place_is_still_found_by_its_own_name(self, index: Index) -> None:
        assert [found.name for found in index.matching("MUNCHEN")] == ["München"]

    def test_and_by_the_start_of_it(self, index: Index) -> None:
        assert "New York City" in [
            found.name for found in index.matching("NEWYORK")
        ]


class TestAnIndexBuiltByOlderRules:
    """The index is derived data, and the rules that derive it live in code.

    So changing them does nothing until somebody re-imports, and until they do
    the service goes on answering by the old rules with nothing to say it is.
    That is exactly what happened when alternate names stopped being indexed:
    the code was right, the database was not, and keying A went on offering
    Cairo.
    """

    def test_a_fresh_index_is_not_stale(self, index: Index) -> None:
        assert not index.stale

    def test_nor_is_an_empty_one(self, tmp_path: Path) -> None:
        #  Nothing has been built by any rules, so no rules are out of date.
        with Index.open(tmp_path / "places.sqlite") as empty:
            assert not empty.stale

    def test_one_built_by_older_rules_says_so(self, tmp_path: Path) -> None:
        filepath = tmp_path / "places.sqlite"
        with Index.open(filepath) as index:
            index.add_places([TRONDHEIM])
            index.stamp(RULES - 1)
        with Index.open(filepath) as reopened:
            assert reopened.stale

    def test_and_importing_again_brings_it_up_to_date(self, tmp_path: Path) -> None:
        filepath = tmp_path / "places.sqlite"
        with Index.open(filepath) as index:
            index.add_places([TRONDHEIM])
            index.stamp(RULES - 1)
        with Index.open(filepath) as reopened:
            reopened.add_places([TRONDHEIM])
            assert not reopened.stale
