"""met.no's weather symbols, in words that fit a forty-column row.

There are about ninety codes and they are built by concatenation --
`lightrainshowersandthunder` -- so they are taken apart rather than listed.
A table of ninety would be ninety chances to mistype one, and it would not
cover a code added next year.
"""

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


class TestWhatWeHaveNotSeen:
    def test_an_unknown_code_is_shown_rather_than_hidden(self) -> None:
        #  A symbol we cannot name is still information. Saying nothing would
        #  read as "no weather", and met.no adds codes without asking us.
        assert in_words("meteorshower") == "meteorshower"

    def test_no_symbol_at_all_says_nothing(self) -> None:
        #  The last moment of a forecast carries no summary block.
        assert in_words(None) == ""
