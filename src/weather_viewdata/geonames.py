"""GeoNames' dump, and the little of it a weather service wants.

The `geoname` table is published as nineteen tab-separated columns with no
header, no quoting and no escaping -- so a field cannot contain a tab and the
parse is a `split`. The format is described in `readme.txt` beside the dump and
nowhere else, which is why the column numbers are named here rather than
counted at the call site.

Six of the nineteen are thrown away: the second, third and fourth
administrative divisions, the alternate country codes, and the modification
date. Nothing on a forty-column screen has room for them, and a smaller table
is a faster index.

Data from GeoNames, CC BY 4.0. https://www.geonames.org/
"""

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Final

#: The dump's columns, by the names `readme.txt` gives them.
_GEONAME_ID: Final = 0
_NAME: Final = 1
_ASCII_NAME: Final = 2
_ALTERNATE_NAMES: Final = 3
_LATITUDE: Final = 4
_LONGITUDE: Final = 5
_FEATURE_CLASS: Final = 6
_FEATURE_CODE: Final = 7
_COUNTRY: Final = 8
_ADMIN1: Final = 10
_POPULATION: Final = 14
_ELEVATION: Final = 15
_DEM: Final = 16
_TIMEZONE: Final = 17

COLUMNS: Final = 19

#: What the terrain model puts where it has no reading. Not a depth.
_NO_READING: Final = -9999


@dataclass(frozen=True)
class Place:
    """Somewhere a forecast can be asked for."""

    geoname_id: int
    """GeoNames' own identifier, which is also this place's page number.

    Nothing here allocates one, so nothing can renumber: a page number written
    down today fetches the same place in ten years.
    """

    name: str
    """As it is written locally -- Tromsø, München -- and as the screen shows it."""

    ascii_name: str
    """GeoNames' own unaccented spelling. Kept because it is sometimes a better
    fallback than folding the name ourselves, and always a cheap second key."""

    alternate_names: tuple[str, ...]
    """Every other name the place goes by, so that Munich finds München.

    From the dump's own column rather than `alternateNamesV2`, which is a
    further 193M for language tags this service has no use for.
    """

    latitude: float
    longitude: float

    feature_class: str
    """GeoNames' coarse kind: P is a populated place, T a mountain, H water."""

    feature_code: str
    """The fine kind: PPLC a capital, PPLA a first-order seat, PPL a village.
    What lets a search rank a capital above a hamlet of the same name."""

    country: str
    """ISO two-letter code."""

    admin1: str
    """The first-order division's code, which `admin1CodesASCII.txt` names."""

    population: int
    """Zero for a great many real places, so it ranks rather than filters."""

    elevation: int | None
    """Metres, for the forecast rather than for display: met.no recommends an
    altitude in hilly terrain."""

    timezone: str
    """The place's own, because a forecast is a run of hours and an hour shown
    in the wrong zone tells a reader nothing."""


def read_places(lines: Iterable[str]) -> Iterator[Place]:
    """Every place in a dump, in the order the dump gives them.

    Blank lines are passed over; a line that is not a place at all stops the
    import. A dump that has changed shape should be noticed while it is being
    read, not later as a half-filled index.
    """
    for line in lines:
        stripped = line.rstrip("\n")
        if not stripped:
            continue
        yield _place_from(stripped.split("\t"))


def _place_from(row: Sequence[str]) -> Place:
    if len(row) != COLUMNS:
        raise ValueError(
            f"a GeoNames row has {COLUMNS} columns, not {len(row)}: {row[:3]}"
        )
    return Place(
        geoname_id=int(row[_GEONAME_ID]),
        name=row[_NAME],
        ascii_name=row[_ASCII_NAME],
        alternate_names=tuple(
            name for name in row[_ALTERNATE_NAMES].split(",") if name
        ),
        latitude=float(row[_LATITUDE]),
        longitude=float(row[_LONGITUDE]),
        feature_class=row[_FEATURE_CLASS],
        feature_code=row[_FEATURE_CODE],
        country=row[_COUNTRY],
        admin1=row[_ADMIN1],
        population=int(row[_POPULATION] or 0),
        elevation=_elevation(row[_ELEVATION], row[_DEM]),
        timezone=row[_TIMEZONE],
    )


def _elevation(elevation: str, dem: str) -> int | None:
    """Metres above sea level, from whichever column has a reading.

    The surveyed column is usually empty and the 90-metre terrain model usually
    is not, so the second stands in for the first. Neither is an altitude of
    zero: the model writes -9999 where it has no reading, and passing that on
    would ask met.no for a forecast ten kilometres underground.
    """
    if elevation:
        return int(elevation)
    if dem and int(dem) != _NO_READING:
        return int(dem)
    return None
