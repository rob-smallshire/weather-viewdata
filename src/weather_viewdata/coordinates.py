"""A point on the earth, written as eight digits of a page number.

Two ways to reach a forecast, and they fail differently, which is why the
service offers both. A named place is `3` and its GeoNames id: convenient,
carrying a name, a timezone and an altitude, and dependent on somebody else's
database continuing to hold that record. A point is `4` and its coordinates:
plainer, and stable by construction, because 63.4N 10.4E will mean the same
thing for as long as there is an earth.

**One decimal place**, which is 11.1km of latitude everywhere and 11.1km of
longitude at the equator, narrowing with the cosine: 5.0km at Trondheim, 3.9km
at Tromsø, 2.3km at Longyearbyen. The scheme is therefore sharpest where this
service points, which is luck rather than design.

That resolution decides what the page can honestly be. Measured against the
real index, 67% of places share a cell with another and one cell in Hong Kong
holds 182 of them -- so a coordinate page cannot name a town, and should not
pretend to. It is the weather *about here*.

**Both axes are biased into a positive range and zero-padded to four digits.**
There is no minus key on a viewdata keypad, and there is no separator in a page
number either -- so two fields can only sit side by side if each is a fixed
width known in advance. That is exactly the case the framework's `int(n)`
exists for, and these converters are the same idea with the arithmetic folded
in, so that a handler is given degrees rather than a code to decode.
"""

from typing import Final

from sextile.routing import Converter

#: Tenths of a degree per whole degree. The resolution, in one place.
_TENTHS: Final = 10

_LATITUDE_BIAS: Final = 90
_LONGITUDE_BIAS: Final = 180

#: 0000 (the south pole) to 1800 (the north pole).
LATITUDE_CODES: Final = 2 * _LATITUDE_BIAS * _TENTHS + 1

#: 0000 to 3599. One fewer than the latitudes' arrangement would suggest,
#: because the circle joins up: 180 east and 180 west are one meridian, and
#: giving it two page numbers would give one place two numbers.
LONGITUDE_CODES: Final = 2 * _LONGITUDE_BIAS * _TENTHS

_FOUR_DIGITS: Final = r"[0-9]{4}"
_WIDTH: Final = 4


def _degrees(value: object) -> float:
    """A number of degrees, from whatever a caller passed.

    Anything else raises `ValueError`, which the router turns into a refusal to
    build the address -- so `address_for("point", lat="north")` fails where it
    is written rather than producing a page number that names nothing.
    """
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{value!r} is not a number of degrees")
    return float(value)


def _to_latitude(digits: str) -> float:
    """Degrees north, from four digits."""
    code = int(digits)
    if code >= LATITUDE_CODES:
        #  Past the pole. The pattern cannot exclude it -- any four digits look
        #  alike -- so it is refused here, and matching moves on to whatever
        #  other route might want these digits.
        raise ValueError(f"{digits} is north of the north pole")
    return code / _TENTHS - _LATITUDE_BIAS


def _from_latitude(value: object) -> str:
    """Four digits, from degrees north.

    Latitude does not wrap: 91 north is not a position spelled unusually, it is
    a mistake, and building a page number for it would hide one.
    """
    degrees = _degrees(value)
    if not -_LATITUDE_BIAS <= degrees <= _LATITUDE_BIAS:
        raise ValueError(f"{degrees} is not a latitude")
    return f"{round((degrees + _LATITUDE_BIAS) * _TENTHS):04d}"


def _to_longitude(digits: str) -> float:
    """Degrees east, from four digits."""
    code = int(digits)
    if code >= LONGITUDE_CODES:
        raise ValueError(f"{digits} is not a longitude")
    return code / _TENTHS - _LONGITUDE_BIAS


def _from_longitude(value: object) -> str:
    """Four digits, from degrees east.

    Longitude *does* wrap, so 190 east is quietly taken as 170 west rather than
    refused: it is a real position spelled unusually, and there is nothing to
    be gained by being strict about which way round somebody went.

    The modulo after rounding is not redundant. A longitude of 179.98 is inside
    the range and rounds to 180.0, which is the date line, which is -180.0 --
    so without the wrap it produces 3600, and 3600 is not a longitude.
    """
    turned = (_degrees(value) + _LONGITUDE_BIAS) % (2 * _LONGITUDE_BIAS)
    return f"{round(turned * _TENTHS) % LONGITUDE_CODES:04d}"


#: Degrees north, as four digits: 0000 is the south pole, 1800 the north.
LATITUDE: Final = Converter(
    field_pattern=_FOUR_DIGITS,
    width=_WIDTH,
    parse=_to_latitude,
    format=_from_latitude,
)

#: Degrees east, as four digits: 0000 is the date line, 1800 Greenwich.
LONGITUDE: Final = Converter(
    field_pattern=_FOUR_DIGITS,
    width=_WIDTH,
    parse=_to_longitude,
    format=_from_longitude,
)
