"""Places, and the folded key a reader can actually type one by.

A viewdata keypad has twenty-six letters and ten digits, and on a search frame
the digits are spoken for -- they select from the suggestions beneath the field.
So a query is a run of letters, and the index it is matched against has to be
letters too.

The fold is deliberately lossy and applies to the *key* alone. `Tromsø` is held,
displayed and forecast as `Tromsø`; it is merely *found* by keying `TROMSO`.
Nothing here ever touches the name a reader sees.
"""

import unicodedata
from typing import Final

#: Letters Unicode will not take apart for us. Decomposition handles the ones
#: built from a letter and a mark -- Ä is A plus a diaeresis, Å is A plus a
#: ring -- but a stroked or ligatured letter is a character in its own right
#: with no decomposition at all, and Norwegian is largely made of those.
_UNDECOMPOSABLE: Final = {
    "Ø": "O",
    "Æ": "AE",
    "Đ": "D",
    "Ð": "D",
    "Þ": "TH",
    "ß": "SS",
    "Ł": "L",
    "Ħ": "H",
    "Ŋ": "NG",
    "Œ": "OE",
    "Ĳ": "IJ",
}


def search_key(name: str) -> str:
    """The letters a reader would key to find this place.

    Everything else is closed up rather than replaced: there is no key for a
    space or a hyphen either, so `New York` is found by `NEWYORK` and
    `Stratford-upon-Avon` by `STRATFORDUPONAVON`.

    Returns "" for a name with no keyable letters at all -- 1770 in Queensland
    is a real town -- which is a place reachable by its page number and not by
    search. An empty key must be kept out of the index rather than stored: every
    query matches the front of it.
    """
    folded = "".join(_UNDECOMPOSABLE.get(character, character) for character in name.upper())
    #  Decompose, then drop the combining marks: Ä becomes A followed by a
    #  diaeresis, and the diaeresis is a mark that no key sends.
    decomposed = unicodedata.normalize("NFKD", folded)
    return "".join(
        character
        for character in decomposed
        if character.isascii() and character.isalpha()
    ).upper()
