"""Fetching GeoNames' dump, and reading it out of the zip.

The dump is thirteen megabytes and changes once a day. Downloading it again
when it has not changed is rude to somebody who gives their data away for
nothing, so the fetch is conditional -- and the condition is the file we already
have, rather than a note kept beside it that could disagree with it.
"""

import zipfile
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path

import httpx2
import pytest

from weather_viewdata.dump import CITIES_500, download_dump, places_in

LINES = (
    "3133880\tTrondheim\tTrondheim\tNidaros,Trondhjem\t63.43049\t10.39506\tP\tPPLA\tNO\t"
    "\t21\t5001\t\t\t147139\t\t14\tEurope/Oslo\t2023-03-08\n"
    "3161732\tBergen\tBergen\tBjørgvin\t60.39299\t5.32415\tP\tPPLA\tNO\t"
    "\t46\t4601\t\t\t213585\t\t9\tEurope/Oslo\t2023-03-08\n"
)


@pytest.fixture
def dump_filepath(tmp_path: Path) -> Path:
    """A dump shaped like the real one: a zip holding one text member."""
    path = tmp_path / "cities500.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("cities500.txt", LINES)
        #  The real zips carry this alongside, and it is not a place.
        archive.writestr("readme.txt", "GeoNames, CC BY 4.0")
    return path


class TestReadingTheZip:
    def test_the_places_come_out_of_it(self, dump_filepath: Path) -> None:
        assert [place.name for place in places_in(dump_filepath)] == [
            "Trondheim",
            "Bergen",
        ]

    def test_the_readme_beside_them_is_not_read_as_places(
        self, dump_filepath: Path
    ) -> None:
        #  Every zip on the site carries one, and it is not tab-separated.
        assert len(list(places_in(dump_filepath))) == 2

    def test_a_plain_text_dump_is_read_too(self, tmp_path: Path) -> None:
        #  So that a subset can be cut out with `head` and imported, which is
        #  what anyone will do while working on the importer.
        path = tmp_path / "some.txt"
        path.write_text(LINES, encoding="utf-8")
        assert [place.name for place in places_in(path)] == ["Trondheim", "Bergen"]

    def test_it_is_read_as_utf_8(self, dump_filepath: Path) -> None:
        #  GeoNames publishes UTF-8 and the platform default is not always it.
        (_, bergen) = places_in(dump_filepath)
        assert "Bjørgvin" in bergen.alternate_names


class TestFetchingItPolitely:
    def test_it_is_downloaded_when_we_have_none(self, tmp_path: Path) -> None:
        into = tmp_path / "cities500.zip"

        def respond(request: httpx2.Request) -> httpx2.Response:
            assert "If-Modified-Since" not in request.headers
            return httpx2.Response(200, content=b"a zip, notionally")

        with httpx2.Client(transport=httpx2.MockTransport(respond)) as client:
            assert download_dump(CITIES_500, into, client=client) is True
        assert into.read_bytes() == b"a zip, notionally"

    def test_we_say_who_we_are(self, tmp_path: Path) -> None:
        #  Not asked for here as met.no asks for it, but a download of this size
        #  from somebody giving it away should be attributable to a person.
        seen: list[str] = []

        def respond(request: httpx2.Request) -> httpx2.Response:
            seen.append(request.headers["User-Agent"])
            return httpx2.Response(200, content=b"")

        with httpx2.Client(transport=httpx2.MockTransport(respond)) as client:
            download_dump(CITIES_500, tmp_path / "d.zip", client=client)
        assert "Sextile" in seen[0]

    def test_the_one_we_have_is_offered_as_the_condition(self, tmp_path: Path) -> None:
        into = tmp_path / "cities500.zip"
        into.write_bytes(b"what we already have")
        seen: list[str] = []

        def respond(request: httpx2.Request) -> httpx2.Response:
            seen.append(request.headers["If-Modified-Since"])
            return httpx2.Response(304)

        with httpx2.Client(transport=httpx2.MockTransport(respond)) as client:
            assert download_dump(CITIES_500, into, client=client) is False
        assert seen and "GMT" in seen[0]

    def test_an_unchanged_dump_is_left_where_it_is(self, tmp_path: Path) -> None:
        into = tmp_path / "cities500.zip"
        into.write_bytes(b"what we already have")

        with httpx2.Client(
            transport=httpx2.MockTransport(lambda request: httpx2.Response(304))
        ) as client:
            download_dump(CITIES_500, into, client=client)
        assert into.read_bytes() == b"what we already have"

    def test_a_changed_dump_replaces_it(self, tmp_path: Path) -> None:
        into = tmp_path / "cities500.zip"
        into.write_bytes(b"stale")

        def respond(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(200, content=b"fresh")

        with httpx2.Client(transport=httpx2.MockTransport(respond)) as client:
            assert download_dump(CITIES_500, into, client=client) is True
        assert into.read_bytes() == b"fresh"

    def test_the_modification_time_follows_the_server(self, tmp_path: Path) -> None:
        #  Which is what makes the next conditional request mean anything: the
        #  file's own timestamp is the note, so there is nothing to fall out of
        #  step with it.
        into = tmp_path / "cities500.zip"
        when = "Sat, 08 Aug 2026 03:14:00 GMT"

        def respond(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(200, content=b"x", headers={"Last-Modified": when})

        with httpx2.Client(transport=httpx2.MockTransport(respond)) as client:
            download_dump(CITIES_500, into, client=client)

        stamped = datetime.fromtimestamp(into.stat().st_mtime, UTC)
        assert format_datetime(stamped, usegmt=True) == when

    def test_a_refusal_is_not_swallowed(self, tmp_path: Path) -> None:
        #  A 404 leaving an empty file behind would be imported as an empty
        #  index, which looks exactly like a service with no places in it.
        with (
            httpx2.Client(
                transport=httpx2.MockTransport(lambda request: httpx2.Response(404))
            ) as client,
            pytest.raises(httpx2.HTTPStatusError),
        ):
            download_dump(CITIES_500, tmp_path / "d.zip", client=client)
        assert not (tmp_path / "d.zip").exists()
