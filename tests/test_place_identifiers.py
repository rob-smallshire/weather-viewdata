"""What we are taking on trust from GeoNames, written down as tests.

A page number here is `3` and a place's GeoNames id, so a number written on a
beermat keeps working for exactly as long as that id means what it means now.
GeoNames promises nothing: the readme calls `geonameid` an "integer id of
record in geonames database" and stops there. What it does publish is a daily
`deletes-<date>.txt`, and the one for 8 August 2026 held a single line
worldwide -- a Norwegian bog merged into another record, with the surviving id
named in the comment. So the churn is real, small, and followable.

**These tests do not watch the live source.** They pin what a captured slice of
`cities500` said on 8 August 2026, so that refreshing the fixture surfaces a
change as a failure rather than as a page number that quietly stops working.
That is the same arrangement `stardot-viewdata` uses for its feed, and it works
the same way: re-capture, run the tests, read what moved.

The likelier way a page number dies has nothing to do with ids. `cities500`
means *population over 500, or an administrative seat*, so a village revised
from 520 to 480 leaves our extract while its id stays perfectly valid. The id
did not move; our window onto the ids did.
"""

from pathlib import Path

import pytest

from weather_viewdata.dump import places_in
from weather_viewdata.geonames import Place

FIXTURE = Path(__file__).parent / "data" / "known-places.txt"

#: Captured from `cities500` on 8 August 2026.
HELD: dict[int, Place] = {place.geoname_id: place for place in places_in(FIXTURE)}


class TestTheNumbersWeAdvertise:
    """If one of these moves, page numbers in the wild stop working."""

    @pytest.mark.parametrize(
        ("geoname_id", "name", "country"),
        [
            (3133880, "Trondheim", "NO"),
            (3133895, "Tromsø", "NO"),
            (3143244, "Oslo", "NO"),
            (3161732, "Bergen", "NO"),
            (3160881, "Bodø", "NO"),
            (3163392, "Ålesund", "NO"),
            (2729907, "Longyearbyen", "SJ"),
            (2643743, "London", "GB"),
            (2950159, "Berlin", "DE"),
            (5128581, "New York City", "US"),
        ],
    )
    def test_a_place_is_still_the_number_we_gave_out(
        self, geoname_id: int, name: str, country: str
    ) -> None:
        held = HELD[geoname_id]
        assert (held.name, held.country) == (name, country)


class TestWhatTheDumpCallsThings:
    def test_munich_is_filed_under_its_english_name(self) -> None:
        #  Not München. GeoNames' primary name is not always the local one, so
        #  a heading drawn from `name` says Munich to a Norwegian reader. The
        #  fold indexes both, so it is found either way -- but what is *shown*
        #  comes from here.
        assert HELD[2867714].name == "Munich"

    def test_trondheim_is_not_marked_as_an_administrative_seat(self) -> None:
        #  It is the seat of Trøndelag, and the dump files it as a plain PPL.
        #  That costs it a point of ranking against places that are marked, so
        #  it is worth knowing rather than assuming the codes are complete.
        assert HELD[3133880].feature_code == "PPL"


class TestWhatIsNotKnown:
    def test_tromso_has_no_elevation_at_all(self) -> None:
        #  Both columns empty and the terrain model at -9999, in one of the
        #  more prominent places this service will be asked about. met.no is
        #  therefore asked without an altitude and uses its own topography,
        #  which is the right answer and not an obvious one.
        assert HELD[3133895].elevation is None

    def test_and_that_is_not_the_same_as_being_at_sea_level(self) -> None:
        assert HELD[2729907].elevation == 1
        assert HELD[3133895].elevation is not HELD[2729907].elevation


class TestWhereThingsAre:
    @pytest.mark.parametrize(
        ("geoname_id", "latitude", "longitude"),
        [
            (3133880, 63.4, 10.4),
            (3143244, 59.9, 10.7),
            (2643743, 51.5, -0.1),
            (2729907, 78.2, 15.6),
        ],
    )
    def test_a_place_is_where_it_was(
        self, geoname_id: int, latitude: float, longitude: float
    ) -> None:
        #  To a tenth of a degree, which is the resolution a coordinate page
        #  number carries. A revision finer than that changes no page number.
        held = HELD[geoname_id]
        assert (round(held.latitude, 1), round(held.longitude, 1)) == (
            latitude,
            longitude,
        )

    def test_every_held_place_keeps_its_own_clock(self) -> None:
        #  A forecast is a run of hours, and an hour in the wrong zone says
        #  nothing. Svalbard has one of its own, which is the case that would
        #  break a service that assumed a country had a single timezone.
        assert HELD[2729907].timezone == "Arctic/Longyearbyen"
        assert HELD[3133880].timezone == "Europe/Oslo"
