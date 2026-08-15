"""The two ways a reader names a forecast: a placename, or a position.

The forms themselves, and the reading of what is typed into them. The pages
that carry the forms are in `pages`; what the forms lead to is resolved by the
router, through `address_for`, so the numbering is spelled once.
"""

import asyncio
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Final

from sextile import PageAddress, Sextile, TypeAhead, keyed
from sextile.formatting import Entry, MenuItem
from sextile.forms import SUGGESTIONS, Field, FieldSet
from sextile.layout import CHOICES_PER_FRAME
from sextile.viewdata.encoding import fitted
from sextile.viewdata.footer import FooterItem, Priority
from sextile.viewdata.frame import COLUMNS
from weather_viewdata.forecast_page import landmark
from weather_viewdata.geonames import Place
from weather_viewdata.store import Index

#: Where the field and its suggestions sit on the search page.
#: Where a form's own rows begin, counted from wherever the layout puts
#: it rather than from the top of a frame.
FIELD_ROW: Final = 0
FIRST_SUGGESTION_ROW: Final = FIELD_ROW + 2

#: How many suggestions the list shows, and the most it will ever show. Three
#: is the measured number -- a fourth row costs a keystroke more than it is
#: worth on a 1200 baud line -- and is right for the ordinary case, where the
#: three are three different places and the reader is choosing between them.
#:
#: It is wrong for one case. Search for Wellington and the three are all called
#: Wellington, and there is nothing to say whether there are four of them or
#: nine, nor any way to reach the rest. So where the likeliest name is shared
#: by more than three places, the list grows to what a single keypress can
#: choose from.
MANY_SUGGESTIONS: Final = CHOICES_PER_FRAME
_SHARING_A_NAME: Final = 3

#: Where the position form's own rows sit. Each field has its advice on the
#: row beneath it and a blank row after that: two labelled fields set solid
#: read as a block of text rather than as two places to type, and a screen of
#: twenty content rows has the room to spare.
LATITUDE_ROW: Final = 0
LONGITUDE_ROW: Final = LATITUDE_ROW + 3

#: Where it says what is nearest to what has been keyed.
NOTE_ROW: Final = LONGITUDE_ROW + 3

#: Cells a coordinate may take, and the width of the bar that says so. Six is
#: the longest there is: `-179.9` signed, `179.9W` with the hemisphere. A
#: seventh would be a cell of blue promising room that nothing could go in.
_POSITION_CELLS: Final = 6


def suggest_field(app: Sextile, places: Index) -> TypeAhead:
    """The search field, told where to look and where its digits lead."""

    async def lookup(typed: str) -> Sequence[Entry]:
        #  Asked for the long list every time and cut to the short one, which
        #  costs nothing worth counting -- a range scan already ordered, nine
        #  rows instead of three -- and is what lets the count of homographs be
        #  known before the list is drawn.
        found = await asyncio.to_thread(places.matching, typed, MANY_SUGGESTIONS)
        shown = found[: _how_many(found)]
        return [
            MenuItem(
                text=place.name,
                detail=detail,
                destination=app.address_for("place", geoname_id=place.geoname_id),
            )
            for place, detail in zip(shown, _details(shown), strict=True)
        ]

    return TypeAhead(
        lookup=lookup,
        field_row=FIELD_ROW,
        suggestions_row=FIRST_SUGGESTION_ROW,
        label="PLACE:",
        limit=MANY_SUGGESTIONS,
        no_match="No place of that name is held.",
    )


def _details(found: Sequence[Place]) -> list[str]:
    """What goes beside each name: the country, and where that is not enough.

    Five of the nine Wellingtons are in the United States, so a column of `US`
    tells a reader which four to rule out and nothing about the other five. The
    division within the country is what separates them, and GeoNames has it:
    `admin1` is the state code in the US and the home nation in the United
    Kingdom -- `FL`, `KS`, `CO`, `OH`, `TX`, `ENG` -- which are the letters
    somebody looking for Wellington, Ohio already has in mind.

    **Only where it is needed.** A column that appeared on every row would be a
    column of numbers in most countries, `admin1` being a code rather than a
    name outside the few that use letters; and the room it takes is room the
    name has. So it is added to the entries that would otherwise read alike and
    to no others, which leaves the ordinary list exactly as it was.
    """
    alike = Counter((place.name, place.country) for place in found)
    return [
        f"{place.country} {place.admin1}".rstrip()
        if alike[(place.name, place.country)] > 1
        else place.country
        for place in found
    ]


def _how_many(found: Sequence[Place]) -> int:
    """How many suggestions to offer: three, or as many as a digit can choose.

    Three is right when the three are three different places. It is wrong when
    they are three Wellingtons, because then it says nothing about whether
    there is a fourth and offers no way to reach one. So the list grows when
    the likeliest name is shared -- by the top one and more than two besides.

    Counted over what came back rather than asked of the index, since the
    ranking has already put the places of that name together at the top: they
    match the query exactly and nothing else can outrank all of them.
    """
    if not found:
        return SUGGESTIONS
    sharing = sum(1 for place in found if place.name == found[0].name)
    return MANY_SUGGESTIONS if sharing > _SHARING_A_NAME else SUGGESTIONS


def position_fields(app: Sextile, places: Index) -> FieldSet:
    """The two coordinate fields, and what they add up to."""

    async def nearest(values: Mapping[str, str]) -> str:
        where = _position(values)
        if where is None:
            return ""
        found = await asyncio.to_thread(places.nearest, *where)
        if found is None:
            #  Somewhere with nothing within a degree, which is most of the
            #  earth's surface. Said rather than left blank: a reader who has
            #  keyed a valid position should not wonder whether it took.
            return "Nowhere within 111km."
        return fitted(landmark(found), COLUMNS - 1)

    def complete(values: Mapping[str, str]) -> PageAddress | None:
        where = _position(values)
        if where is None:
            return None
        return app.address_for("point", lat=where[0], lon=where[1])

    return FieldSet(
        fields=[
            Field(
                name="latitude",
                label="LATITUDE",
                row=LATITUDE_ROW,
                takes=_takes("NS"),
                width=_POSITION_CELLS,
                hint=" north or south: 54.0N or 54.0S",
                hint_row=LATITUDE_ROW + 1,
            ),
            Field(
                name="longitude",
                label="LONGITUDE",
                row=LONGITUDE_ROW,
                takes=_takes("EW"),
                width=_POSITION_CELLS,
                hint=" east or west: 17.2E or 17.2W",
                hint_row=LONGITUDE_ROW + 1,
            ),
        ],
        complete=complete,
        note=nearest,
        note_row=NOTE_ROW,
        sends="forecast",
        #  This page cannot offer `0` for the index: a nought keyed into a
        #  coordinate is a nought, and the field takes it. So it says how to
        #  leave by keying a number instead.
        advice=(FooterItem(keyed(app.index), "menu", Priority.ESSENTIAL),),
    )


def _takes(hemispheres: str) -> Callable[[str], bool]:
    """What belongs in a coordinate field.

    Both spellings are taken, because both are in use and a reader arriving
    with one should not have to discover that this service wanted the other.

    **Only the hemispheric one is advertised.** A field's advice sits under it
    on every frame, so it is read far more often than it is needed, and one
    that showed all four spellings shouted louder than the field it was
    explaining. Showing one way of writing a coordinate teaches the reader who
    does not know; taking both serves the reader who does.

    So the signs are deliberately undocumented rather than unsupported, and
    nothing above should be tidied to match the hint.
    """

    def takes(key: str) -> bool:
        return key.isdigit() or key in {".", "+", "-", *hemispheres}

    return takes


def _degrees_from(written: str, hemispheres: str) -> float | None:
    """One coordinate, written either way round, or None if it is not one."""
    said = written.strip().upper()
    if not said:
        return None
    negative = said.startswith("-") or said.endswith(hemispheres[1])
    figures = said.lstrip("+-").rstrip(hemispheres)
    try:
        degrees = float(figures)
    except ValueError:
        return None
    return -degrees if negative else degrees


def _position(values: Mapping[str, str]) -> tuple[float, float] | None:
    """Both fields as degrees, or None while either is not a coordinate."""
    latitude = _degrees_from(values.get("latitude", ""), "NS")
    longitude = _degrees_from(values.get("longitude", ""), "EW")
    if latitude is None or longitude is None:
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return latitude, longitude
