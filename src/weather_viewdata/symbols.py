"""met.no's weather symbols, taken apart.

**41 symbol ids, 21 of which have `_day`, `_night` and `_polartwilight`
variants: 83 codes in all**, and they are built by concatenation rather than
enumerated -- `light` + `sleet` + `showers` + `andthunder`. So they are taken
apart here rather than tabulated. A table of eighty-three entries would be
eighty-three chances to mistype one, and it would say nothing about a code added
next year. The published list is in `tests/data/met-symbols.csv` and every code
in it is taken apart in a test.

**One decomposition, two renderings.** `taken_apart` is the whole of the
knowledge of how a code is spelled; `in_words` says it in words, and `icons.py`
draws the same parts as a picture. The alternative -- a second reading of the
codes for the pictures -- is the mistake the place index already made once, with
two folds of a name that drifted apart.

The words are short because the column is sixteen cells wide and the row also
has to carry two clocks, a temperature and a wind. `showers` becomes `shwrs`
for that reason alone; everything else is spelled out.
"""

from dataclasses import dataclass
from typing import Final

#: The core states, longest first so that `partlycloudy` is not read as `cloudy`
#: with `partly` left over.
_CORES: Final = (
    "partlycloudy",
    "clearsky",
    "cloudy",
    "sleet",
    "rain",
    "snow",
    "fair",
    "fog",
)

#: What each is called on screen. Only two are not simply themselves.
_SAID: Final = {"clearsky": "clear", "partlycloudy": "part cloudy"}

#: How hard it is coming down. Prefixes on the core.
_INTENSITIES: Final = ("light", "heavy")

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

#: When it is, which met.no says only where it makes a difference to the
#: picture. `polartwilight` is not a typo -- the sun does not rise in Tromsø in
#: December.
DAY: Final = "day"
NIGHT: Final = "night"
TWILIGHT: Final = "polartwilight"

_WHEN: Final = (DAY, NIGHT, TWILIGHT)


#: Every symbol id met.no publishes, in their order. A legend has to enumerate
#: -- that is what a legend is -- and this is the only place in the service that
#: does. It is pinned to the published list in a test, so a family added next
#: year shows up as a failure here rather than as a gap on the page.
#:
#: Bare, without `_day`: 21 of them have `_day`, `_night` and `_polartwilight`
#: variants and the difference is one piece of the picture, which the legend
#: says in a line instead of in another forty drawings.
PUBLISHED: Final = (
    "clearsky", "fair", "partlycloudy", "cloudy", "lightrainshowers",
    "rainshowers", "heavyrainshowers", "lightrainshowersandthunder",
    "rainshowersandthunder", "heavyrainshowersandthunder", "lightsleetshowers",
    "sleetshowers", "heavysleetshowers", "lightssleetshowersandthunder",
    "sleetshowersandthunder", "heavysleetshowersandthunder",
    "lightsnowshowers", "snowshowers", "heavysnowshowers",
    "lightssnowshowersandthunder", "snowshowersandthunder",
    "heavysnowshowersandthunder", "lightrain", "rain", "heavyrain",
    "lightrainandthunder", "rainandthunder", "heavyrainandthunder",
    "lightsleet", "sleet", "heavysleet", "lightsleetandthunder",
    "sleetandthunder", "heavysleetandthunder", "lightsnow", "snow",
    "heavysnow", "lightsnowandthunder", "snowandthunder",
    "heavysnowandthunder", "fog",
)


@dataclass(frozen=True)
class Weather:
    """One symbol code, in its parts.

    Which parts there are is met.no's choosing, not ours: a code is an optional
    intensity, a core state, and then whether it comes in showers, whether there
    is thunder with it, and what time of day it is.
    """

    core: str
    """One of `_CORES`, spelled as met.no spells it."""

    intensity: str = ""
    """`light`, `heavy`, or nothing at all for the middle of the three."""

    showers: bool = False
    """Whether it comes and goes. Which is why only these codes have a time of
    day: the sun is visible between the showers and has to be drawn."""

    thunder: bool = False

    when: str = ""
    """`day`, `night`, `polartwilight`, or nothing where it makes no difference
    -- overcast is overcast at midnight."""

    @property
    def falling(self) -> bool:
        """Whether anything is coming out of the sky."""
        return self.core in {"rain", "sleet", "snow"}


def taken_apart(symbol: str | None) -> Weather | None:
    """A symbol code in its parts, or None if it is not one we can read.

    None rather than a guess. met.no adds codes without consulting us, and a
    code read as the nearest thing we know would draw the wrong weather with
    every appearance of confidence.
    """
    if not symbol:
        return None
    code, when = symbol, ""
    for suffix in _WHEN:
        if code.endswith(f"_{suffix}"):
            code, when = code.removesuffix(f"_{suffix}"), suffix
            break
    code = _MISSPELLED.get(code, code)

    thunder = code.endswith(_THUNDER)
    code = code.removesuffix(_THUNDER)
    showers = code.endswith(_SHOWERS)
    code = code.removesuffix(_SHOWERS)

    intensity = ""
    for prefix in _INTENSITIES:
        if code.startswith(prefix):
            intensity, code = prefix, code.removeprefix(prefix)
            break

    if code not in _CORES:
        return None
    return Weather(
        core=code,
        intensity=intensity,
        showers=showers,
        thunder=thunder,
        when=when,
    )


def in_words(symbol: str | None) -> str:
    """A symbol code, said in as few words as will do.

    An unrecognised code is handed back as it arrived rather than dropped: a
    symbol we cannot name is still information, saying nothing would read as
    "no weather", and met.no adds codes without consulting us.

    The time of day is dropped: the reader can see the hour in the same row, and
    saying "(night)" costs eight cells to repeat what the clock already says.
    """
    if not symbol:
        return ""
    weather = taken_apart(symbol)
    if weather is None:
        #  Not a shape we know. Hand back what we were given, whole.
        return symbol
    core = _SAID.get(weather.core, weather.core)
    words = f"{weather.intensity} {core}".strip()
    if weather.showers:
        words += " shwrs"
    if weather.thunder:
        #  No space before the plus: this is the longest thing the column ever
        #  has to hold and it does not fit as it is.
        words += "+thunder"
    return words
