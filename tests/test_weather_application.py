"""The service refusing to serve an index it would answer wrongly from.

The index is derived data and the rules that derive it live in code, so a
change to them does nothing until somebody re-imports. Until they do, the
service answers by the old rules and says nothing about it -- which is how
keying A went on offering Cairo long after alternate names had stopped being
indexed.
"""

import sqlite3
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import pytest

from sextile import Page, PageAddress, Sextile, UnknownPageError
from sextile.testing import Caller, calling
from sextile.visits import SqliteVisits
from weather_viewdata import build_application
from weather_viewdata.application import StaleIndexError
from weather_viewdata.forecast.model import Forecast
from weather_viewdata.forecast.source import ForecastSource
from weather_viewdata.geonames import Place
from weather_viewdata.handlers import VISITS
from weather_viewdata.store import RULES, Index

TRONDHEIM = Place(
    geoname_id=3133880,
    name="Trondheim",
    ascii_name="Trondheim",
    alternate_names=(),
    latitude=63.43049,
    longitude=10.39506,
    feature_class="P",
    feature_code="PPL",
    country="NO",
    admin1="21",
    population=147139,
    elevation=18,
    timezone="Europe/Oslo",
)


class NoForecasts(ForecastSource):
    async def forecast_for(self, place: Place) -> Forecast | None:
        return None


class TestRefusingAStaleIndex:
    async def test_a_current_index_serves(self, tmp_path: Path) -> None:
        filepath = tmp_path / "places.sqlite"
        with Index.open(filepath) as index:
            index.add_places([TRONDHEIM])
        app = build_application(
            source=NoForecasts(),
            index_filepath=filepath,
            visits_filepath=tmp_path / "visits.sqlite",
        )
        await app.startup()
        assert await app.ask("1") is not None
        await app.shutdown()

    async def test_one_built_by_older_rules_does_not(self, tmp_path: Path) -> None:
        filepath = tmp_path / "places.sqlite"
        with Index.open(filepath) as index:
            index.add_places([TRONDHEIM])
            index.stamp(RULES - 1)
        app = build_application(
            source=NoForecasts(),
            index_filepath=filepath,
            visits_filepath=tmp_path / "visits.sqlite",
        )
        with pytest.raises(StaleIndexError):
            await app.startup()

    async def test_and_says_what_to_run(self, tmp_path: Path) -> None:
        #  A refusal that does not say how to fix it is only half a refusal.
        filepath = tmp_path / "places.sqlite"
        with Index.open(filepath) as index:
            index.add_places([TRONDHEIM])
            index.stamp(RULES - 1)
        app = build_application(
            source=NoForecasts(),
            index_filepath=filepath,
            visits_filepath=tmp_path / "visits.sqlite",
        )
        with pytest.raises(StaleIndexError, match="import-places"):
            await app.startup()

    async def test_an_index_that_was_never_built_is_not_stale(
        self, tmp_path: Path
    ) -> None:
        #  A first run has an empty file and nothing to be out of date about.
        #  It will say it holds no places, which is true and is a different
        #  complaint.
        app = build_application(
            source=NoForecasts(),
            index_filepath=tmp_path / "places.sqlite",
            visits_filepath=tmp_path / "visits.sqlite",
        )
        await app.startup()
        await app.shutdown()


class TestHowAForecastIsDrawnIsPartOfItsNumber:
    """The third digit, and why it is the third.

    The same weather can be a table or a graph, and neither is the poor
    relation, so the presentation is in the address rather than a mode the
    reader has to get the frame into: a number written down fetches back what
    was written down.

    It sits before the subject because a geoname id has no fixed width, and a
    digit after one could not be told from the id itself.
    """

    def test_a_place_is_numbered_by_its_presentation_then_its_id(self) -> None:
        app = build_application(source=NoForecasts())
        assert app.address_for("place", geoname_id=3133880) == PageAddress(
            "321" + "3133880"
        )

    def test_a_point_likewise_and_then_its_position(self) -> None:
        app = build_application(source=NoForecasts())
        assert app.address_for("point", lat=63.43049, lon=10.39506) == PageAddress(
            "421" + "1534" + "1904"
        )


class TestBothWaysOfWritingACoordinate:
    """The signs are undocumented rather than unsupported.

    A field's advice sits under it on every frame, so it is read far more often
    than it is needed and had better be short. It shows the hemispheric
    spelling only -- which teaches the reader who does not know -- while the
    signed one goes on working for the reader who does.

    Here so that nobody tidies the parser to match the hint.
    """

    @pytest.mark.parametrize(
        ("latitude", "longitude"),
        [
            ("54.0N", "1.1W"),  # as the hint shows it
            ("54.0", "-1.1"),  # and as it does not
            ("54.0N", "-1.1"),  # and one of each
        ],
    )
    async def test_either_spelling_reaches_the_same_point(
        self, latitude: str, longitude: str, tmp_path: Path
    ) -> None:
        filepath = tmp_path / "places.sqlite"
        with Index.open(filepath) as index:
            index.add_places([TRONDHEIM])
        app = build_application(
            source=NoForecasts(),
            index_filepath=filepath,
            visits_filepath=tmp_path / "visits.sqlite",
        )
        async with calling(app, start="4") as caller:
            await caller.key(latitude)
            await caller.key(b"\x09")
            await caller.key(longitude)
            await caller.key(b"\x5f")
            assert caller.address == PageAddress("42114401789")


class TestTheSearchForgetsWhatWasTyped:
    """`*3#` gives an empty field, every time.

    It used to keep the word in the session and hand it back, on the argument
    that a reader looking at one of three candidates would want it there to
    refine. Used, it turns out the other way round: a reader who has just read
    a forecast is looking for somewhere *else*, and the kept word costs them a
    press of the rub-out key for every letter of it -- each one a round trip
    and a redraw at 1200 baud.
    """

    async def test_typing_still_works(self, tmp_path: Path) -> None:
        #  The half that had to keep working. Typing does not fetch the page
        #  again -- a form answers a keypress by redrawing -- so forgetting on
        #  arrival costs the letters nothing.
        async with _typing(tmp_path) as caller:
            for letter in "TROND":
                await caller.key(letter)
            assert "TROND" in caller.shown
            assert "Trondheim" in caller.shown

    async def test_but_leaving_and_coming_back_gives_an_empty_field(
        self, tmp_path: Path
    ) -> None:
        async with _typing(tmp_path) as caller:
            await caller.key("TROND")
            assert "TROND" in caller.shown
            #  Away to the forecast and back to the search.
            await caller.key("1")
            await caller.key("F")
            assert "TROND" not in caller.shown
            assert "Trondheim" not in caller.shown


@asynccontextmanager
async def _typing(tmp_path: Path, start: str = "3") -> AsyncIterator[Caller]:
    filepath = tmp_path / "places.sqlite"
    with Index.open(filepath) as index:
        index.add_places([TRONDHEIM])
    app = build_application(
        source=NoForecasts(),
        index_filepath=filepath,
        visits_filepath=tmp_path / "visits.sqlite",
    )
    async with calling(app, start=start) as caller:
        yield caller


class TestThePositionFormForgetsToo:
    """Both fields empty every time, as the search field is.

    This one looked like the exception -- two figures are more trouble to type
    than a name, and a reader nudging a latitude would want the old one there.
    It is not: a reader comes back to look at somewhere *else*, and a
    remembered position costs twelve presses of the rub-out key across two
    fields.
    """

    async def test_typing_a_position_still_works(self, tmp_path: Path) -> None:
        async with _typing(tmp_path, start="4") as caller:
            await caller.key("54.0N")
            await caller.key(b"\x09")
            await caller.key("1.1W")
            await caller.key(b"\x5f")
            assert caller.address == PageAddress("42114401789")

    async def test_but_coming_back_gives_two_empty_fields(
        self, tmp_path: Path
    ) -> None:
        #  Not 54.0N, which is the sample in the field's own advice: the test
        #  would then find the hint and call it the field.
        async with _typing(tmp_path, start="4") as caller:
            await caller.key("63.4N")
            assert "63.4N" in caller.shown
            #  Away to the menu and back to the position form.
            await caller.key("*1#")
            await caller.key("*4#")
            assert "63.4N" not in caller.shown


class TestAWordBetweenTheStarAndTheHashIsAPage:
    """`*YORK#` was a search and is not any more.

    Two reasons, both worth keeping. It shared a namespace it could not share:
    `*HISTORY#` is a page and `*YORK#` was a place, and nothing about either
    said which a word would turn out to be. And it answered with one answer
    where there are many -- there are dozens of Yorks, and the index picked the
    likeliest and said nothing about the rest.
    """

    async def test_a_place_name_is_not_a_page(self, tmp_path: Path) -> None:
        async with _held(tmp_path) as app:
            with pytest.raises(UnknownPageError):
                app.resolve("TRONDHEIM")

    async def test_and_the_service_own_words_still_are(self, tmp_path: Path) -> None:
        #  Which is the point: a word between the star and the hash now means
        #  one thing, and a reader knows which before they key it.
        async with _held(tmp_path) as app:
            assert app.resolve("HISTORY") == PageAddress("92")
            assert app.resolve("SEARCH") == PageAddress("3")


@asynccontextmanager
async def _held(
    tmp_path: Path, places: Iterable[Place] = (TRONDHEIM,)
) -> AsyncIterator[Sextile]:
    filepath = tmp_path / "places.sqlite"
    with Index.open(filepath) as index:
        index.add_places(list(places))
    app = build_application(
        source=NoForecasts(),
        index_filepath=filepath,
        visits_filepath=tmp_path / "visits.sqlite",
    )
    await app.startup()
    try:
        yield app
    finally:
        await app.shutdown()


class TestHowLongTheSuggestionListIs:
    """Three, unless the likeliest name is shared.

    Three is right when the three are three different places. It is wrong when
    they are three Wellingtons: nothing then says whether there is a fourth,
    and there is no way to reach one.
    """

    async def test_three_where_the_names_differ(self, tmp_path: Path) -> None:
        async with _held(tmp_path, [_somewhere(n) for n in range(9)]) as app:
            assert await _suggestions(app, "PLACE") == 3

    async def test_and_nine_where_the_likeliest_is_shared(
        self, tmp_path: Path
    ) -> None:
        async with _held(tmp_path, [_wellington(n) for n in range(9)]) as app:
            assert await _suggestions(app, "WELLINGTON") == 9

    async def test_three_still_where_only_three_share_it(self, tmp_path: Path) -> None:
        #  The top one and two besides is the ordinary case of a name a couple
        #  of places happen to have, and three rows show all of them.
        held = [*(_wellington(n) for n in range(3)), *(_somewhere(n) for n in range(6))]
        async with _held(tmp_path, held) as app:
            assert await _suggestions(app, "WELLINGTON") == 3

    async def test_and_nine_is_the_most_a_keypress_can_choose_from(
        self, tmp_path: Path
    ) -> None:
        #  470 names in the real index are shared by more than nine places --
        #  Santa Cruz by sixty-nine. Past nine there is no digit left to choose
        #  with, so the tenth is not offered. Recorded rather than solved.
        async with _held(tmp_path, [_wellington(n) for n in range(20)]) as app:
            assert await _suggestions(app, "WELLINGTON") == 9


async def _offered(app: Sextile, typed: str) -> list[tuple[str, str]]:
    page = await app.ask("3")
    assert page is not None
    form = page.frames[0].form
    assert form is not None
    for letter in typed:
        await form.typed(letter)
    return [(entry.text, entry.detail) for entry in form.found]  # type: ignore[attr-defined]


async def _suggestions(app: Sextile, typed: str) -> int:
    page = await app.ask("3")
    assert page is not None
    form = page.frames[0].form
    assert form is not None
    for letter in typed:
        await form.typed(letter)
    return len(form.found)  # type: ignore[attr-defined]


def _wellington(number: int, country: str = "NZ", admin1: str = "") -> Place:
    return replace(TRONDHEIM, geoname_id=9000 + number, name="Wellington",
                   ascii_name="Wellington", population=1000 - number,
                   country=country, admin1=admin1)


def _somewhere(number: int) -> Place:
    return replace(TRONDHEIM, geoname_id=8000 + number, name=f"Placeb{'x' * number}",
                   ascii_name=f"Placeb{'x' * number}", population=1000 - number)


class TestTellingTwoOfTheSameNameApart:
    """Five of the nine Wellingtons are in the United States.

    A column of `US` says which four to rule out and nothing about the other
    five. What separates them is the division within the country, and GeoNames
    has it: `admin1` is the state code in the US and the home nation in the
    United Kingdom.
    """

    async def test_the_country_alone_where_it_is_enough(self, tmp_path: Path) -> None:
        held = [_wellington(0, "NZ"), _wellington(1, "GB"), _wellington(2, "ZA")]
        async with _held(tmp_path, held) as app:
            assert await _offered(app, "WELLINGTON") == [
                ("Wellington", "NZ"),
                ("Wellington", "GB"),
                ("Wellington", "ZA"),
            ]

    async def test_and_the_division_within_it_where_it_is_not(
        self, tmp_path: Path
    ) -> None:
        held = [
            _wellington(0, "US", "FL"),
            _wellington(1, "US", "KS"),
            _wellington(2, "NZ", "G2"),
        ]
        async with _held(tmp_path, held) as app:
            offered = dict(await _offered(app, "WELLINGTON"))
            assert set(offered) == {"Wellington"}

    async def test_only_the_entries_that_would_have_read_alike(
        self, tmp_path: Path
    ) -> None:
        #  The column is not added to the whole list. Outside the countries
        #  that use letters `admin1` is a number, and the room it takes is room
        #  the name has -- so the ordinary row is left exactly as it was.
        held = [
            _wellington(0, "US", "FL"),
            _wellington(1, "US", "KS"),
            _wellington(2, "NZ", "G2"),
        ]
        async with _held(tmp_path, held) as app:
            details = [detail for _, detail in await _offered(app, "WELLINGTON")]
            assert sorted(details) == ["NZ", "US FL", "US KS"]

    async def test_a_place_with_no_division_recorded_says_the_country(
        self, tmp_path: Path
    ) -> None:
        #  GeoNames leaves the field empty often enough to matter, and a
        #  trailing space would be a column that says nothing at all.
        held = [_wellington(0, "US", ""), _wellington(1, "US", "")]
        async with _held(tmp_path, held) as app:
            assert [detail for _, detail in await _offered(app, "WELLINGTON")] == [
                "US",
                "US",
            ]


class TestThePlacesLatelyLookedUp:
    """`*2#`, which is the weather's own and not the framework's.

    The framework has a page of what has been read lately, and it is a list of
    *pages*: `One place`, nine times over, because a page number is all a
    framework can know. This one asks the index what the numbers meant.
    """

    async def test_it_names_the_places_rather_than_the_pages(
        self, tmp_path: Path
    ) -> None:
        async with _held(tmp_path) as app:
            await _looked_at(app, "3213133880")
            page = await app.ask("2")
            assert page is not None
            assert "Trondheim" in _text(page)

    async def test_and_going_there_is_going_to_the_forecast(
        self, tmp_path: Path
    ) -> None:
        async with _held(tmp_path) as app:
            await _looked_at(app, "3213133880")
            page = await app.ask("2")
            assert page is not None
            assert page.frames[0].destination("1") == PageAddress("3213133880")

    async def test_a_place_no_longer_held_is_left_off(self, tmp_path: Path) -> None:
        #  GeoNames drops a village from `cities500` and the number in the log
        #  stops naming anything. A row that cannot be named is a row nobody
        #  can use.
        async with _held(tmp_path) as app:
            await _looked_at(app, "3219999999")
            page = await app.ask("2")
            assert page is not None
            assert "Nobody has looked anything up yet." in _text(page)

    async def test_and_so_are_positions(self, tmp_path: Path) -> None:
        #  A position is a page and not a place. Nobody looking at a list of
        #  somewhere-elses wants `59.7N 10.0E`.
        async with _held(tmp_path) as app:
            await _looked_at(app, "42114971900")
            page = await app.ask("2")
            assert page is not None
            assert "Nobody has looked anything up yet." in _text(page)

    async def test_a_service_keeping_no_log_says_so(self, tmp_path: Path) -> None:
        #  Rather than an empty menu, which reads as "nobody has been here".
        #  Not started, so the lifespan has opened nothing.
        app = build_application(
            source=NoForecasts(), index_filepath=tmp_path / "places.sqlite"
        )
        page = await app.ask("2")
        assert page is not None
        assert "not keeping a log" in _text(page)


async def _looked_at(app: Sextile, page: str) -> None:
    from sextile.middleware import CALLER

    visits = app.state[VISITS]
    assert isinstance(visits, SqliteVisits)
    await visits.record(PageAddress(page), caller=CALLER, found=True)


def _text(page: Page) -> str:
    characters, _ = page.frames[0].frame.to_grid()
    return "\n".join(characters)


class TestHowManyHaveCalled:
    async def test_the_page_counts_distinct_callers(self, tmp_path: Path) -> None:
        async with _held(tmp_path) as app:
            visits = app.state[VISITS]
            assert isinstance(visits, SqliteVisits)
            for caller in ("a", "b", "a"):
                await visits.record(PageAddress("1"), caller=caller, found=True)
            page = await app.ask("98")
            assert page is not None
            shown = _text(page)
            assert "Last 24 hours" in shown
            assert "2" in shown

    async def test_and_a_service_keeping_no_log_says_so(self, tmp_path: Path) -> None:
        app = build_application(
            source=NoForecasts(), index_filepath=tmp_path / "places.sqlite"
        )
        page = await app.ask("98")
        assert page is not None
        assert "No log" in _text(page)


class TestTheLifespanClosesWhatItOpens:
    """The log and the index are files, and files are handed back.

    The lifespan opens three things and must close all three however far it
    got: a log left open holds its file, and an index left open by a startup
    that failed halfway holds its file against the rebuild the failure told
    somebody to run.
    """

    async def test_the_visits_log_is_closed_at_shutdown(
        self, tmp_path: Path
    ) -> None:
        filepath = tmp_path / "places.sqlite"
        with Index.open(filepath) as index:
            index.add_places([TRONDHEIM])
        app = build_application(
            source=NoForecasts(),
            index_filepath=filepath,
            visits_filepath=tmp_path / "visits.sqlite",
        )
        await app.startup()
        visits = app.state[VISITS]
        assert isinstance(visits, SqliteVisits)
        await app.shutdown()
        with pytest.raises(sqlite3.ProgrammingError):
            await visits.recent(1)

    async def test_the_index_is_closed_when_the_log_cannot_be_opened(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        filepath = tmp_path / "places.sqlite"
        with Index.open(filepath) as index:
            index.add_places([TRONDHEIM])
        opened: list[Index] = []
        real_open = Index.open

        def capturing(index_filepath: Path | str) -> Index:
            found = real_open(index_filepath)
            opened.append(found)
            return found

        monkeypatch.setattr(Index, "open", capturing)
        app = build_application(
            source=NoForecasts(),
            index_filepath=filepath,
            #  A directory, which sqlite cannot open as a database file.
            visits_filepath=tmp_path,
        )
        with pytest.raises(sqlite3.OperationalError):
            await app.startup()
        (index,) = opened
        with pytest.raises(sqlite3.ProgrammingError):
            index.held()
