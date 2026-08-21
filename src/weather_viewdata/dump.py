"""Getting GeoNames' dump, and reading places out of it.

GeoNames publishes its database under CC BY and asks nothing in return but
attribution. It is still somebody's bandwidth, so the fetch is conditional and
identifies itself, and thirteen megabytes is streamed to disk rather than
gathered in memory.

The file we already have is the condition. Its modification time is set to
the server's `Last-Modified` on the way in, and offered back as
`If-Modified-Since` next time. A note kept beside the file could disagree with
the file; the file cannot disagree with itself.

Data from GeoNames, CC BY 4.0. https://www.geonames.org/
"""

from __future__ import annotations

import os
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from typing import Final

import httpx2
from sextile import __version__

from weather_viewdata.geonames import Place, read_places

_BASE_URL: Final = "https://download.geonames.org/export/dump/"

#: Every place with five hundred inhabitants or more, plus the seats of
#: administration whatever their size. Thirteen megabytes, against four hundred
#: for the whole database -- which is mostly lakes, ridges and spot heights that
#: nobody asks the forecast for.
CITIES_500: Final = _BASE_URL + "cities500.zip"

USER_AGENT: Final = f"Sextile/{__version__} (+viewdata weather service)"

#: A chunk of the download, held in memory only until it is written.
_CHUNK: Final = 64 * 1024


def download_dump(
    url: str, into_filepath: Path, *, client: httpx2.Client | None = None
) -> bool:
    """Fetch the dump unless the copy on disk is already current.

    Returns whether anything was written, so that an importer can skip the
    import as well as the download.

    A failed request raises rather than leaving a short or empty file behind: an
    empty dump imports as an empty index, which on a service whose whole point
    is searching places looks exactly like a service with no places in it.
    """
    owned = client is None
    client = client or httpx2.Client(follow_redirects=True)
    try:
        headers = {"User-Agent": USER_AGENT}
        if into_filepath.exists():
            since = datetime.fromtimestamp(into_filepath.stat().st_mtime, UTC)
            headers["If-Modified-Since"] = format_datetime(since, usegmt=True)

        with client.stream("GET", url, headers=headers) as response:
            if response.status_code == httpx2.codes.NOT_MODIFIED:
                return False
            response.raise_for_status()
            into_filepath.parent.mkdir(parents=True, exist_ok=True)
            #  Written beside the target and moved into place, so that an
            #  interrupted download cannot be imported as though it were whole.
            partial = into_filepath.with_suffix(into_filepath.suffix + ".part")
            with partial.open("wb") as sink:
                for chunk in response.iter_bytes(_CHUNK):
                    sink.write(chunk)
            partial.replace(into_filepath)
            _stamp(into_filepath, response.headers.get("Last-Modified"))
        return True
    finally:
        if owned:
            client.close()


def _stamp(filepath: Path, last_modified: str | None) -> None:
    """Give the file the server's own timestamp, for next time's condition."""
    if not last_modified:
        return
    when = parsedate_to_datetime(last_modified).timestamp()
    os.utime(filepath, (when, when))


def places_in(dump_filepath: Path) -> Iterator[Place]:
    """Every place in a dump, whether zipped or laid out plainly.

    The plain case is there because the first thing anyone does while working on
    an importer is cut a hundred lines out with `head`, and having to zip them
    again to try it would be a small daily annoyance.
    """
    if zipfile.is_zipfile(dump_filepath):
        yield from _places_in_zip(dump_filepath)
        return
    with dump_filepath.open(encoding="utf-8") as lines:
        yield from read_places(lines)


def _places_in_zip(dump_filepath: Path) -> Iterator[Place]:
    with zipfile.ZipFile(dump_filepath) as archive:
        member = archive.open(_data_member(archive))
        with member:
            #  Decoded a line at a time rather than read whole: the full dump
            #  is a hundred and fifty megabytes unzipped, and there is no
            #  reason for any of it to be resident twice, let alone three
            #  times.
            yield from read_places(line.decode("utf-8") for line in member)


def _data_member(archive: zipfile.ZipFile) -> str:
    """The one member that holds places.

    Every dump on the site carries a `readme.txt` beside the data, and it is
    prose rather than columns -- so it is named out rather than parsed and
    hoped over.
    """
    members = [
        name
        for name in archive.namelist()
        if name.endswith(".txt") and Path(name).name.lower() != "readme.txt"
    ]
    if len(members) != 1:
        raise ValueError(
            f"expected one data member in {archive.filename}, found {members}"
        )
    return members[0]
