"""Filling the place index from a dump.

The one long-running thing this service does: two hundred thousand places, and
once a week at most. Everything here is about that shape -- committed in
batches so an interrupted import leaves a usable index rather than a locked
one, and reporting as it goes, because a command that says nothing for a minute
looks like a command that has hung.
"""

from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Final

from weather_viewdata.dump import places_in
from weather_viewdata.store import Index

#: Places written per transaction. Large enough that the per-commit cost
#: disappears, small enough that an interrupted import has left most of its
#: work behind.
DEFAULT_BATCH: Final = 5000


def import_places(
    dump_filepath: Path,
    index: Index,
    *,
    prefer_country: str | None = None,
    batch: int = DEFAULT_BATCH,
    progress: Callable[[int], None] | None = None,
) -> int:
    """Read a dump into the index, and say how many places it held.

    The preference is set before anything is read, because the ranking is
    computed on the way in: an importer that set it afterwards would rank
    nothing at all.
    """
    if prefer_country is not None:
        index.prefer(country=prefer_country)
    taken = 0
    for group in _batched(places_in(dump_filepath), batch):
        index.add_places(group)
        taken += len(group)
        if progress is not None:
            progress(taken)
    return taken


def _batched[T](items: Iterable[T], size: int) -> Iterator[list[T]]:
    """Whole batches, then whatever is left over.

    `itertools.batched` does this, and is not used: it yields tuples, and the
    caller wants a list it can measure and pass on without converting twice.
    """
    group: list[T] = []
    for item in items:
        group.append(item)
        if len(group) == size:
            yield group
            group = []
    if group:
        yield group
