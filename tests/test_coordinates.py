"""A point on the earth, as four digits and four digits.

A named place is reached by its GeoNames id, which is convenient and depends on
somebody else's database staying still. A point is reached by its coordinates,
which depends on nothing: 63.4N 10.4E will mean the same thing forever.

One decimal place is 11.1km of latitude everywhere, and 11.1km of longitude at
the equator narrowing with the cosine -- 5.0km at Trondheim, 3.9km at Tromsø.
So the scheme is sharpest exactly where this service points, which is luck
rather than design but worth writing down.

Negative numbers cannot be keyed on a viewdata keypad, so each axis is biased
into a positive range and zero-padded to a fixed width: that is what lets two
fields sit side by side in a page number with nothing between them.
"""

import pytest

from sextile import NoSuchRouteError, Page, PageAddress, PageFrame, PageRequest, Sextile
from sextile.viewdata.canvas import Canvas
from weather_viewdata.coordinates import (
    LATITUDE,
    LATITUDE_CODES,
    LONGITUDE,
    LONGITUDE_CODES,
)


class TestWritingAPosition:
    @pytest.mark.parametrize(
        ("latitude", "digits"),
        [
            (63.43049, "1534"),   # Trondheim
            (0.0, "0900"),        # the equator
            (90.0, "1800"),       # the north pole
            (-90.0, "0000"),      # the south pole
            (-33.87, "0561"),     # Sydney
        ],
    )
    def test_a_latitude(self, latitude: float, digits: str) -> None:
        assert LATITUDE.to_digits(latitude) == digits

    @pytest.mark.parametrize(
        ("longitude", "digits"),
        [
            (10.39506, "1904"),   # Trondheim
            (0.0, "1800"),        # Greenwich
            (-0.12574, "1799"),   # London, just west of it
            (151.21, "3312"),     # Sydney
            (-74.006, "1060"),    # New York
        ],
    )
    def test_a_longitude(self, longitude: float, digits: str) -> None:
        assert LONGITUDE.to_digits(longitude) == digits

    def test_a_position_is_always_four_digits(self) -> None:
        #  Which is the whole point: two fields with no separator between them
        #  can only be told apart if their widths are known in advance.
        assert LATITUDE.to_digits(-89.9) == "0001"
        assert LONGITUDE.to_digits(-179.9) == "0001"


class TestReadingAPosition:
    @pytest.mark.parametrize(
        ("digits", "latitude"),
        [("1534", 63.4), ("0900", 0.0), ("1800", 90.0), ("0000", -90.0)],
    )
    def test_a_latitude(self, digits: str, latitude: float) -> None:
        assert LATITUDE.to_value(digits) == pytest.approx(latitude)

    @pytest.mark.parametrize(
        ("digits", "longitude"),
        [("1904", 10.4), ("1800", 0.0), ("0000", -180.0), ("3599", 179.9)],
    )
    def test_a_longitude(self, digits: str, longitude: float) -> None:
        assert LONGITUDE.to_value(digits) == pytest.approx(longitude)


class TestTheEdgesOfTheEarth:
    def test_the_date_line_has_one_number_and_not_two(self) -> None:
        #  180 east and 180 west are the same meridian. Left alone they would
        #  be 3600 and 0000 -- two page numbers for one place, which is the
        #  thing the numbering rules exist to prevent.
        assert LONGITUDE.to_digits(180.0) == LONGITUDE.to_digits(-180.0) == "0000"

    def test_a_longitude_that_rounds_onto_the_date_line_wraps_too(self) -> None:
        #  179.98 rounds to 180.0, which is -180.0, which is 0000. Without the
        #  wrap this produces 3600 and is not a longitude at all.
        assert LONGITUDE.to_digits(179.98) == "0000"

    def test_a_longitude_beyond_the_earth_is_brought_back_onto_it(self) -> None:
        #  190 east is 170 west. Accepting it costs nothing and refusing it
        #  would be refusing a real position spelled unusually.
        assert LONGITUDE.to_digits(190.0) == LONGITUDE.to_digits(-170.0)

    def test_a_latitude_off_the_earth_is_refused(self) -> None:
        #  Unlike longitude, latitude does not wrap: 91 north is not a place,
        #  it is a mistake, and building a page number for it would hide one.
        with pytest.raises(NoSuchRouteError):
            LATITUDE.to_digits(91.0)

    @pytest.mark.parametrize("digits", ["1801", "9999"])
    def test_digits_past_the_pole_are_not_a_latitude(self, digits: str) -> None:
        #  The pattern cannot exclude these -- any four digits look alike -- so
        #  the converter rejects them and matching moves on to another route.
        with pytest.raises(ValueError):
            LATITUDE.to_value(digits)

    def test_every_four_digit_longitude_is_a_place(self) -> None:
        #  0000 to 3599 is the whole circle, so unlike latitude there is
        #  nothing in range to reject.
        with pytest.raises(ValueError):
            LONGITUDE.to_value("3600")


class TestRoundTripping:
    """Reading a page number and writing it again must give it back.

    Exhaustively, because there are only 1801 latitudes and 3600 longitudes and
    an off-by-one at one end of the earth is exactly the sort of thing that
    survives a handful of examples.
    """

    def test_every_latitude(self) -> None:
        for code in range(LATITUDE_CODES):
            digits = f"{code:04d}"
            assert LATITUDE.to_digits(LATITUDE.to_value(digits)) == digits

    def test_every_longitude(self) -> None:
        for code in range(LONGITUDE_CODES):
            digits = f"{code:04d}"
            assert LONGITUDE.to_digits(LONGITUDE.to_value(digits)) == digits

    def test_a_position_survives_being_written_and_read(self) -> None:
        #  The other direction, which is lossy on purpose: what comes back is
        #  the cell the point fell in, not the point.
        latitude = LATITUDE.to_value(LATITUDE.to_digits(63.43049))
        assert latitude == pytest.approx(63.4)


class TestAsAPageNumber:
    """The point of all this: two fields side by side, with nothing between.

    A page number has no separators, so the framework requires every field but
    the last to have a width known in advance. These have one, which is why
    they can be written next to each other at all.
    """

    def test_a_point_has_a_page_number(self) -> None:
        app = _app()
        assert app.address_for("point", lat=63.43049, lon=10.39506) == PageAddress(
            "415341904"
        )

    async def test_and_keying_it_gives_the_handler_degrees(self) -> None:
        #  Not a code to decode. The converter is where the arithmetic lives,
        #  so a handler that draws a forecast never sees a biased integer.
        app = _app()
        page = await app.fetch("415341904")
        assert page is not None
        assert _seen == [(63.4, 10.4)]

    async def test_a_number_past_the_pole_is_not_a_page(self) -> None:
        #  1801 is north of the north pole. The pattern admits it and the
        #  converter does not, so the router moves on and finds nothing.
        app = _app()
        assert await app.fetch("418011904") is None

    def test_a_position_that_is_not_a_number_will_not_build_one(self) -> None:
        app = _app()
        with pytest.raises(NoSuchRouteError):
            app.address_for("point", lat="north", lon=10.4)


_seen: list[tuple[float, float]] = []


def _app() -> Sextile:
    _seen.clear()
    app = Sextile(name="Weather")
    app.add_converter("latitude", LATITUDE)
    app.add_converter("longitude", LONGITUDE)

    @app.page("4{lat:latitude}{lon:longitude}", name="point")
    async def point(request: PageRequest, lat: float, lon: float) -> Page:
        _seen.append((round(lat, 1), round(lon, 1)))
        return Page(frames=(PageFrame(frame=Canvas().frame),))

    return app
