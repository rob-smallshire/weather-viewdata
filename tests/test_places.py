"""Folding a place name into something a viewdata keypad can type.

The terminal decides the alphabet here, and it decides it narrowly. Sextile's
command parser keeps only what `isalnum` admits and uppercases it, so a space,
a hyphen and an umlaut all arrive as nothing at all -- and a digit cannot arrive
as part of a name either, because on a search frame the digits select from the
suggestions beneath.

So the index is folded to the letters A-Z and nothing else. What is folded is
the *key*, never the data: Tromso finds Tromsø, and the screen still says
Tromsø.
"""

import pytest

from weather_viewdata.places import search_key


class TestFoldingToWhatCanBeKeyed:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Trondheim", "TRONDHEIM"),
            ("Oslo", "OSLO"),
        ],
    )
    def test_a_plain_name_is_merely_shouted(self, name: str, expected: str) -> None:
        assert search_key(name) == expected

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            #  The three that matter most for a Norwegian service, and the one
            #  of them that Unicode will not decompose for us.
            ("Tromsø", "TROMSO"),
            ("Bodø", "BODO"),
            ("Ålesund", "ALESUND"),
            ("Værøy", "VAEROY"),
            #  Elsewhere in Europe, where a reader keys the name they know.
            ("München", "MUNCHEN"),
            ("Köln", "KOLN"),
            ("Saint-Étienne", "SAINTETIENNE"),
            ("Reykjavík", "REYKJAVIK"),
            ("Þórshöfn", "THORSHOFN"),
            ("Gdańsk", "GDANSK"),
        ],
    )
    def test_a_letter_the_keypad_has_not_got_folds_to_one_it_has(
        self, name: str, expected: str
    ) -> None:
        assert search_key(name) == expected

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("New York", "NEWYORK"),
            ("San Francisco", "SANFRANCISCO"),
            ("Stratford-upon-Avon", "STRATFORDUPONAVON"),
            ("'s-Hertogenbosch", "SHERTOGENBOSCH"),
        ],
    )
    def test_what_cannot_be_typed_is_closed_up(self, name: str, expected: str) -> None:
        #  Closed up rather than replaced by anything, because there is no key
        #  for a separator either: a reader types the letters and no more.
        assert search_key(name) == expected

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Quận 1", "QUAN"),
            ("Township 12", "TOWNSHIP"),
            ("Sector 7", "SECTOR"),
        ],
    )
    def test_a_digit_is_dropped_rather_than_the_place(
        self, name: str, expected: str
    ) -> None:
        #  A digit pressed on a search frame selects a suggestion, so it can
        #  never be part of a query. Dropping it from the key keeps the place
        #  findable by the letters around it; dropping the place would not.
        assert search_key(name) == expected

    def test_a_name_of_nothing_but_digits_folds_to_nothing(self) -> None:
        #  1770, in Queensland, is a real town. It cannot be searched for, and
        #  saying so here is better than an index quietly holding an empty key
        #  that every query matches the front of.
        assert search_key("1770") == ""
