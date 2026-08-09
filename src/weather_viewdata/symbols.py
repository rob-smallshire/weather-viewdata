"""met.no's weather symbols, in words a forty-column row can hold.

There are about ninety codes, and they are built by concatenation rather than
enumerated: `light` + `rain` + `showers` + `andthunder`. So they are taken
apart here rather than tabulated. A table of ninety entries would be ninety
chances to mistype one, and it would say nothing about a code added next year.

The words are short because the column is sixteen cells wide and the row also
has to carry two clocks, a temperature and a wind. `showers` becomes `shwrs`
for that reason alone; everything else is spelled out.
"""

from typing import Final

#: The core states, longest first so that `partlycloudy` is not read as `cloudy`
#: with `partly` left over.
_CORES: Final = (
    ("partlycloudy", "part cloudy"),
    ("clearsky", "clear"),
    ("cloudy", "cloudy"),
    ("sleet", "sleet"),
    ("rain", "rain"),
    ("snow", "snow"),
    ("fair", "fair"),
    ("fog", "fog"),
)

#: How hard it is coming down. Prefixes on the core.
_INTENSITIES: Final = (("light", "light"), ("heavy", "heavy"))

#: What the sky is doing besides. Suffixes, innermost last.
_SHOWERS: Final = "showers"
_THUNDER: Final = "andthunder"

#: Two codes are misspelled at the source, and have been for years: `lights`
#: with two esses, in met.no's own `legend.csv` and in NRK's symbol set, for
#: codes 26 and 28. Taken apart, `lights` is not an intensity and the core is
#: never found, so the whole code came back raw and unreadable. Corrected on
#: the way in rather than worked around further down, because everything after
#: this point is entitled to assume the codes are built the way they are said
#: to be.
_MISSPELLED: Final = {
    "lightssleetshowersandthunder": "lightsleetshowersandthunder",
    "lightssnowshowersandthunder": "lightsnowshowersandthunder",
}

#: Dropped: the reader can see the hour in the same row, and saying "(night)"
#: costs cells to repeat what the clock already says. `polartwilight` is not a
#: typo -- the sun does not rise in Tromsø in December.
_WHEN: Final = ("_day", "_night", "_polartwilight")


def in_words(symbol: str | None) -> str:
    """A symbol code, said in as few words as will do.

    An unrecognised code is handed back as it arrived rather than dropped: a
    symbol we cannot name is still information, saying nothing would read as
    "no weather", and met.no adds codes without consulting us.
    """
    if not symbol:
        return ""
    code = symbol
    for suffix in _WHEN:
        code = code.removesuffix(suffix)
    code = _MISSPELLED.get(code, code)

    thunder = code.endswith(_THUNDER)
    code = code.removesuffix(_THUNDER)
    showers = code.endswith(_SHOWERS)
    code = code.removesuffix(_SHOWERS)

    intensity = ""
    for prefix, said in _INTENSITIES:
        if code.startswith(prefix):
            intensity, code = said, code.removeprefix(prefix)
            break

    core = next((said for spelled, said in _CORES if code == spelled), None)
    if core is None:
        #  Not a shape we know. Hand back what we were given, whole.
        return symbol

    words = f"{intensity} {core}".strip()
    if showers:
        words += " shwrs"
    if thunder:
        #  No space before the plus: this is the longest thing the column ever
        #  has to hold and it does not fit as it is.
        words += "+thunder"
    return words
