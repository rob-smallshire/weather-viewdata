"""met.no's weather symbols, in words that fit a forty-column row.

There are about ninety codes and they are built by concatenation --
`lightrainshowersandthunder` -- so they are taken apart rather than listed.
A table of ninety would be ninety chances to mistype one, and it would not
cover a code added next year.
"""

import csv
from pathlib import Path

import pytest

from weather_viewdata.symbols import in_words


class TestTheSimpleOnes:
    @pytest.mark.parametrize(
        ("code", "words"),
        [
            ("clearsky", "clear"),
            ("cloudy", "cloudy"),
            ("fair", "fair"),
            ("fog", "fog"),
            ("partlycloudy", "part cloudy"),
            ("rain", "rain"),
            ("sleet", "sleet"),
            ("snow", "snow"),
        ],
    )
    def test_a_bare_code(self, code: str, words: str) -> None:
        assert in_words(code) == words


class TestTimeOfDay:
    @pytest.mark.parametrize(
        "code", ["clearsky_day", "clearsky_night", "clearsky_polartwilight"]
    )
    def test_it_is_dropped(self, code: str) -> None:
        #  The reader can see the time in the same row, and on forty columns
        #  "clear (night)" costs eight cells to say what the clock says.
        assert in_words(code) == "clear"

    def test_polar_twilight_is_a_real_suffix_and_not_a_typo(self) -> None:
        #  It exists because the sun does not rise in Tromsø in December, and
        #  a service pointed north will meet it.
        assert in_words("partlycloudy_polartwilight") == "part cloudy"


class TestTheBuiltUpOnes:
    @pytest.mark.parametrize(
        ("code", "words"),
        [
            ("lightrain", "light rain"),
            ("heavyrain", "heavy rain"),
            ("rainshowers", "rain shwrs"),
            ("lightsnowshowers", "light snow shwrs"),
            ("rainandthunder", "rain+thunder"),
            ("heavysleetshowers", "heavy sleet shwrs"),
        ],
    )
    def test_a_code_is_taken_apart(self, code: str, words: str) -> None:
        assert in_words(code) == words

    def test_the_longest_code_there_is(self) -> None:
        #  Which is what decides how wide the column has to be, and it does not
        #  fit -- so the drawing shortens it. Worth knowing the worst case
        #  rather than discovering it on a thundery day in December.
        assert in_words("heavysleetshowersandthunder") == "heavy sleet shwrs+thunder"


class TestTheTwoCodesWithATypoInThem:
    """`lightssleetshowersandthunder`, with two esses.

    Not a transcription slip of ours. It is spelled that way in met.no's own
    `legend.csv` and in NRK's symbol set, for codes 26 and 28, and has been for
    years -- so it is what arrives on the wire and it is what we have to read.

    Taken apart, `lights` is not an intensity and `sleet` never gets found, so
    before this the whole code came back raw: twenty-eight characters of
    `lightssleetshowersandthunder` trimmed to nonsense in a sixteen-cell column,
    on exactly the sort of afternoon a reader would want to know about.
    """

    @pytest.mark.parametrize(
        ("code", "words"),
        [
            ("lightssleetshowersandthunder", "light sleet shwrs+thunder"),
            ("lightssnowshowersandthunder", "light snow shwrs+thunder"),
            ("lightssleetshowersandthunder_day", "light sleet shwrs+thunder"),
        ],
    )
    def test_it_is_read_as_the_code_it_was_meant_to_be(
        self, code: str, words: str
    ) -> None:
        assert in_words(code) == words


class TestEveryCodeThereIs:
    """The whole published list, taken apart.

    `tests/data/met-symbols.csv` is met.no's own `legend.csv`, captured from
    `metno/weathericons`: **41 symbol ids, 21 of which have `_day`, `_night`
    and `_polartwilight` variants, so 83 codes in all.** Which is the answer to
    whether a table would have been the easier thing: it would have been
    eighty-three rows, and this is the test that says it is not needed.

    It is also the test that would have caught the two misspelled codes, and
    the one that will notice when met.no adds a family we cannot name.
    """

    #: Every word `in_words` is allowed to produce. A code taken apart into
    #: anything else has not been taken apart.
    VOCABULARY = frozenset(
        {"clear", "fair", "part", "cloudy", "fog"}
        | {"rain", "sleet", "snow"}
        | {"light", "heavy", "shwrs", "thunder"}
    )

    def test_all_of_them_are_read_as_words_we_know(self) -> None:
        for code in codes():
            said = in_words(code).replace("+", " ")
            assert said, code
            assert set(said.split()) <= self.VOCABULARY, code

    def test_the_variants_too(self) -> None:
        for code in codes():
            for when in ("_day", "_night", "_polartwilight"):
                assert in_words(code + when) == in_words(code)

    def test_and_none_of_them_is_longer_than_the_longest(self) -> None:
        #  Which is what decides how wide a column has to be. Measured over the
        #  published list rather than over the ones we happened to think of.
        assert max(len(in_words(code)) for code in codes()) == len(
            "heavy sleet shwrs+thunder"
        )


def codes() -> list[str]:
    """Every symbol id met.no publishes."""
    filepath = Path(__file__).parent / "data" / "met-symbols.csv"
    with filepath.open(encoding="utf-8", newline="") as opened:
        return [row["Symbol ID"].strip() for row in csv.DictReader(opened)]


class TestWhatWeHaveNotSeen:
    def test_an_unknown_code_is_shown_rather_than_hidden(self) -> None:
        #  A symbol we cannot name is still information. Saying nothing would
        #  read as "no weather", and met.no adds codes without asking us.
        assert in_words("meteorshower") == "meteorshower"

    def test_no_symbol_at_all_says_nothing(self) -> None:
        #  The last moment of a forecast carries no summary block.
        assert in_words(None) == ""
