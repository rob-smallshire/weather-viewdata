"""Places, and the folded key a reader can actually type one by.

A viewdata keypad has twenty-six letters and ten digits, and on a search frame
the digits are spoken for -- they select from the suggestions beneath the field.
So a query is a run of letters, and the index it is matched against has to be
letters too.

**The fold is taken from what the screen shows.** That is the core of the
module. Sextile already reduces text
to what the G0 set can display -- it must, or a frame would carry bytes the
hardware cannot draw -- and a reader keys what they see. If the two folds were
worked out separately they would drift, and a reader would be shown a name they
could not type: this module once had a table of its own, and it already knew
four letters the framework's did not, so `Dakovo` was findable while the screen
said `?akovo`.

The fold is lossy and applies to the *key* alone. `Tromsø` is held and
forecast as `Tromsø`; the screen shows `Tromso` because that is all it can
show, and the reader finds it by keying `TROMSO`.
"""

from sextile import transliterate


def search_key(name: str) -> str:
    """The letters a reader would key to find this place.

    Everything else is closed up rather than replaced: there is no key for a
    space or a hyphen either, so `New York` is found by `NEWYORK` and
    `Stratford-upon-Avon` by `STRATFORDUPONAVON`. A reader may type the spaces
    if they like -- what they type is folded the same way.

    Digits go too. On a search frame they select from the suggestions, so a
    place whose name holds one is found by the letters around it: `Quan 1` by
    `QUAN`.

    Returns "" for a name with no keyable letters at all -- 1770 in Queensland
    is a real town -- which is a place reachable by its page number and not by
    search. An empty key must be kept out of the index rather than stored:
    every query matches the front of it.
    """
    return "".join(
        character
        for character in transliterate(name)
        if character.isascii() and character.isalpha()
    ).upper()
