"""Reading GeoNames' dump.

The format is nineteen tab-separated columns with no header, no quoting and no
escaping, described only in `readme.txt`. Most of it a weather service does not
want; what it does want is written up in `geonames.py`.

The lines here are real ones from `cities500`, kept verbatim. A made-up line
agrees with whatever the parser does, which is the one thing a fixture must not
do.
"""

import pytest

from weather_viewdata.geonames import read_places

#: Trondheim. Note the empty elevation column and the populated dem beside it,
#: which is the usual case rather than the exception.
TRONDHEIM = (
    "3133880\tTrondheim\tTrondheim\t"
    "Drontheim,Nidaros,Trondhjem,Trondheim,Trondkheim,Тронхейм,トロンハイム,特隆赫姆\t"
    "63.43049\t10.39506\tP\tPPLA\tNO\t\t21\t5001\t\t\t147139\t\t14\tEurope/Oslo\t2023-03-08"
)

#: Tromsø, whose name is the reason the fold exists.
TROMSO = (
    "3133895\tTromsø\tTromso\tTromsdalen,Tromso,Tromsoe,Tromsø,Тромсё\t"
    "69.6489\t18.95508\tP\tPPLA\tNO\t\t54\t5401\t\t\t64182\t\t28\tEurope/Oslo\t2023-03-08"
)

#: Bergen, which shares its first three letters with somewhere far larger.
BERGEN = (
    "3161732\tBergen\tBergen\tBergen,Bjørgvin,Берген\t"
    "60.39299\t5.32415\tP\tPPLA\tNO\t\t46\t4601\t\t\t213585\t\t9\tEurope/Oslo\t2023-03-08"
)


class TestReadingADumpLine:
    def test_a_place_carries_the_identifier_geonames_gave_it(self) -> None:
        #  Which is also its page number here. Nothing in this service
        #  allocates one, so nothing can renumber.
        (place,) = read_places([TRONDHEIM])
        assert place.geoname_id == 3133880

    def test_the_name_is_kept_as_it_is_written(self) -> None:
        (place,) = read_places([TROMSO])
        assert place.name == "Tromsø"

    def test_where_it_is(self) -> None:
        (place,) = read_places([TRONDHEIM])
        assert (place.latitude, place.longitude) == (63.43049, 10.39506)

    def test_what_kind_of_place_it_is(self) -> None:
        (place,) = read_places([TRONDHEIM])
        assert (place.feature_class, place.feature_code) == ("P", "PPLA")

    def test_where_it_is_administered_from(self) -> None:
        (place,) = read_places([TRONDHEIM])
        assert (place.country, place.admin1) == ("NO", "21")

    def test_how_many_live_there(self) -> None:
        (place,) = read_places([BERGEN])
        assert place.population == 213585

    def test_which_clock_it_keeps(self) -> None:
        #  A forecast is a run of hours, and an hour has to be shown in the
        #  place's own time or it says nothing useful to a reader.
        (place,) = read_places([TRONDHEIM])
        assert place.timezone == "Europe/Oslo"


class TestTheNamesAPlaceGoesBy:
    def test_the_alternate_names_are_split(self) -> None:
        (place,) = read_places([TRONDHEIM])
        assert "Nidaros" in place.alternate_names
        assert "Trondhjem" in place.alternate_names

    def test_a_place_with_none_has_none(self) -> None:
        line = TRONDHEIM.split("\t")
        line[3] = ""
        (place,) = read_places(["\t".join(line)])
        assert place.alternate_names == ()


class TestHowHighItIs:
    """met.no takes an altitude and recommends one in hilly terrain.

    GeoNames offers two columns for it and usually fills only the second.
    """

    def test_the_elevation_column_is_preferred(self) -> None:
        line = TRONDHEIM.split("\t")
        line[15] = "50"
        (place,) = read_places(["\t".join(line)])
        assert place.elevation == 50

    def test_the_terrain_model_stands_in_when_it_is_empty(self) -> None:
        (place,) = read_places([TRONDHEIM])
        assert place.elevation == 14

    def test_neither_is_not_an_altitude_of_zero(self) -> None:
        #  -9999 is how the terrain model says it does not know, and sending it
        #  as an altitude would ask for a forecast ten kilometres underground.
        line = TRONDHEIM.split("\t")
        line[15], line[16] = "", "-9999"
        (place,) = read_places(["\t".join(line)])
        assert place.elevation is None


class TestLinesThatAreNotPlaces:
    def test_a_blank_line_is_passed_over(self) -> None:
        assert list(read_places(["", TRONDHEIM, ""])) == list(read_places([TRONDHEIM]))

    def test_a_line_with_too_few_columns_is_refused(self) -> None:
        #  Loudly. A dump that has changed shape should stop an import rather
        #  than quietly filling an index with half the world.
        with pytest.raises(ValueError, match="19 columns"):
            list(read_places(["3133880\tTrondheim\tTrondheim"]))

    def test_a_line_whose_numbers_are_not_numbers_is_refused(self) -> None:
        line = TRONDHEIM.split("\t")
        line[14] = "lots"
        with pytest.raises(ValueError):
            list(read_places(["\t".join(line)]))


class TestReadingTheWholeDump:
    def test_every_line_becomes_a_place(self) -> None:
        places = list(read_places([TRONDHEIM, TROMSO, BERGEN]))
        assert [place.name for place in places] == ["Trondheim", "Tromsø", "Bergen"]
