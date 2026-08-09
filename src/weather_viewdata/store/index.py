"""The place index: what a reader's letters are matched against.

Deliberately synchronous, as Stardot's archive is, and for the same reason: the
queries are small and indexed, and an async facade over SQLite buys indirection
and nothing else. A caller on the event loop reaches this through
`asyncio.to_thread`, which keeps the blocking explicit and in one place.

**The ranking is computed on the way in, never at query time.** A search frame
repaints while the reader is still typing, so the query a keystroke costs has to
be an indexed range scan and an ORDER BY on a stored column. Anything cleverer
-- a score computed per row, a join to work out importance -- would be paid for
on every letter of every search by every caller.

Three suggestions is what the wire affords at 1200 baud, and that makes the
order the whole game: with nine, a mediocre ranking still shows the reader what
they wanted somewhere on the list, and with three it either offers the right
place or it does not.
"""

from __future__ import annotations

import math
import sqlite3
import threading
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType
from typing import Final, Self

from weather_viewdata.geonames import Place
from weather_viewdata.places import search_key

_SCHEMA_FILEPATH: Final = Path(__file__).with_name("schema.sql")

#: Which version of the folding and ranking rules built an index.
#:
#: **Raise this whenever `_keys_for`, `search_key` or `_rank_of` changes.** The
#: index is derived data and the rules that derive it live in code, so a change
#: to them does nothing at all until somebody re-imports -- and until they do,
#: the service goes on answering by the old rules with nothing whatever to say
#: that it is. That is not hypothetical: alternate names stopped being indexed,
#: the code was right, the database was not, and keying A went on offering
#: Cairo for the alternate name Al Qahirah.
#:
#: 1  the original: name, ascii name and filtered alternate names
#: 2  the place's own name only, folded through the framework's transliteration
RULES: Final = 2

#: As many as a frame can repaint while a reader is still typing. Measured, not
#: chosen: nine rows is 2.9 seconds at 1200 baud and three is 0.8.
SUGGESTIONS: Final = 3

#: What kind of place counts for, over and above how many live there. GeoNames'
#: feature codes, coarsest first. A capital and a hamlet of equal population are
#: not equally likely to be the one somebody meant.
_IMPORTANCE: Final = {
    "PPLC": 1.5,   # a national capital
    "PPLA": 1.0,   # a first-order administrative seat
    "PPLA2": 0.8,
    "PPLA3": 0.6,
    "PPLA4": 0.4,
    "PPLA5": 0.3,
    "PPL": 0.2,    # a populated place with no particular standing
}

#: What matching a name exactly is worth, on the same scale as everything else:
#: a hundredfold of population. Enough to lift a place above a namesake ten
#: times its size, and not enough to lift a hamlet above a capital.
EXACTNESS: Final = 2.0

#: What being in the preferred country is worth by default, on the same scale
#: as everything else: a tenfold of population.
#:
#: A nudge and not an override, which is the whole difficulty. This is a global
#: service whose readers happen to mostly be in one country, so home should
#: break a tie between comparable places and should not put Boston in
#: Lincolnshire above Boston in Massachusetts. A bonus of 3.0 -- a thousandfold
#: -- did exactly that.
HOME_BONUS: Final = 1.0

#: How far from a point we will look for somewhere to borrow a name and a
#: clock from. A degree of latitude is 111km; beyond that "near" is a stretch.
_NEARBY: Final = 1.0

_PLACE_COLUMNS: Final = (
    "geoname_id, name, ascii_name, alternate_names, latitude, longitude, "
    "feature_class, feature_code, country, admin1, population, elevation, timezone"
)


class Index:
    """Places, and every string that finds one."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._preferred_country: str | None = None
        self._home_bonus = HOME_BONUS
        with self._lock:
            self._connection.executescript(_SCHEMA_FILEPATH.read_text())
            (built_by,) = self._connection.execute("PRAGMA user_version").fetchone()
        self._built_by = int(built_by)

    @classmethod
    def open(cls, database_filepath: Path | str) -> Self:
        path = Path(database_filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        return cls(sqlite3.connect(path, check_same_thread=False))

    @classmethod
    def in_memory(cls) -> Self:
        """A throwaway index, for tests."""
        return cls(sqlite3.connect(":memory:", check_same_thread=False))

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @contextmanager
    def _writing(self) -> Iterator[sqlite3.Connection]:
        with self._lock, self._connection:
            yield self._connection

    # -- filling it ---------------------------------------------------------

    def prefer(self, *, country: str, worth: float = HOME_BONUS) -> None:
        """Say whose weather this service is mostly about.

        Affects places added *after* it is set, the ranking being computed on
        the way in. An importer says this before it reads the dump; there is no
        reason for it to change afterwards, and re-ranking a million rows to
        honour a late change would be a great deal of work for nobody.
        """
        self._preferred_country = country
        self._home_bonus = worth

    def add_places(self, places: Iterable[Place]) -> None:
        """Put places in the index, replacing any already held under the same id.

        Replacing rather than adding, so that re-importing a fresh dump over an
        old one leaves one of each rather than two.
        """
        with self._writing() as connection:
            for place in places:
                connection.execute(
                    f"INSERT OR REPLACE INTO places ({_PLACE_COLUMNS}, rank) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        place.geoname_id,
                        place.name,
                        place.ascii_name,
                        ",".join(place.alternate_names),
                        place.latitude,
                        place.longitude,
                        place.feature_class,
                        place.feature_code,
                        place.country,
                        place.admin1,
                        place.population,
                        place.elevation,
                        place.timezone,
                        self._rank_of(place),
                    ),
                )
                connection.execute(
                    "DELETE FROM place_keys WHERE geoname_id = ?", (place.geoname_id,)
                )
                connection.executemany(
                    "INSERT OR IGNORE INTO place_keys (key, geoname_id) VALUES (?, ?)",
                    [(key, place.geoname_id) for key in _keys_for(place)],
                )
        #  Whatever is here was put here by the rules in force now.
        self.stamp()

    def _rank_of(self, place: Place) -> float:
        """How likely this is to be the place somebody meant.

        Population on a log scale, because the difference between a village and
        a town matters far more than the difference between two capitals; plus
        what kind of place it is; plus whether it is where this service is
        pointed. Summed rather than multiplied so that a zero population -- of
        which GeoNames has a great many -- does not annihilate the rest.
        """
        score = math.log10(place.population + 1)
        score += _IMPORTANCE.get(place.feature_code, 0.0)
        if self._preferred_country is not None and place.country == self._preferred_country:
            score += self._home_bonus
        return score

    # -- reading it ---------------------------------------------------------

    def matching(self, typed: str, limit: int = SUGGESTIONS) -> Sequence[Place]:
        """The best few places whose names begin with what has been typed.

        An empty query finds nothing rather than the whole world in population
        order: a reader who has typed nothing has asked nothing, and three rows
        of the largest cities on earth is a distraction rather than a result.
        """
        query = search_key(typed)
        if not query:
            return []
        with self._lock:
            rows = self._connection.execute(
                f"SELECT p.{', p.'.join(_PLACE_COLUMNS.split(', '))}, "
                "       MAX(k.key = :query) AS exact "
                "FROM place_keys k JOIN places p ON p.geoname_id = k.geoname_id "
                #  A range scan rather than LIKE: the bound is explicit, it
                #  cannot be defeated by a collation, and the key is the leading
                #  column of the table's own primary key.
                "WHERE k.key >= :low AND k.key < :high "
                "GROUP BY p.geoname_id "
                #  Exactness is added to the ranking rather than sorted before
                #  it. Sorted before it, somebody keying BERGEN gets Bergen
                #  ahead of a larger Bergenfield -- which is right -- but LON
                #  gets Lognes ahead of London, on the strength of an alternate
                #  name reading `Lon'`, and BER gets a French hamlet called
                #  Beure ahead of Bergen. A short alias is worth something and
                #  it is not worth more than being a city.
                "ORDER BY p.rank + :exactness * MAX(k.key = :query) DESC, "
                "         p.geoname_id "
                "LIMIT :limit",
                {
                    "query": query,
                    "low": query,
                    "high": _after(query),
                    "exactness": EXACTNESS,
                    "limit": limit,
                },
            ).fetchall()
        return [_place_from(row) for row in rows]

    def place(self, geoname_id: int) -> Place | None:
        """One place, by the number GeoNames gave it and this service uses."""
        with self._lock:
            row = self._connection.execute(
                f"SELECT {_PLACE_COLUMNS} FROM places WHERE geoname_id = ?",
                (geoname_id,),
            ).fetchone()
        return _place_from(row) if row is not None else None

    def nearest(self, latitude: float, longitude: float) -> Place | None:
        """The closest place to a point, or None if nothing is close.

        For a coordinate page, which has no name and no timezone of its own and
        must borrow both. Unlike a search this is purely about distance: a big
        city an hour away is the wrong answer to "what is near here".

        Bounded to a degree in each direction, so the middle of the Pacific
        finds nothing rather than somewhere a thousand miles off with the wrong
        clock on it. Within that box the earth is flat enough for Pythagoras,
        with longitude scaled by the cosine of the latitude -- a degree of
        longitude is half a degree of latitude at sixty north, and unscaled
        distances would lean east-west everywhere but the equator.
        """
        scale = math.cos(math.radians(latitude))
        with self._lock:
            row = self._connection.execute(
                f"SELECT {_PLACE_COLUMNS} FROM places "
                "WHERE latitude BETWEEN :low AND :high "
                "  AND longitude BETWEEN :west AND :east "
                "ORDER BY (latitude - :lat) * (latitude - :lat) "
                "       + (longitude - :lon) * (longitude - :lon) * :scale * :scale "
                "LIMIT 1",
                {
                    "lat": latitude,
                    "lon": longitude,
                    "low": latitude - _NEARBY,
                    "high": latitude + _NEARBY,
                    #  Not wrapped across the date line. A point at 179.5E will
                    #  miss a town at 179.5W, which is a strip of the Pacific
                    #  with almost nothing in it -- and the page still works,
                    #  it merely shows times in UTC.
                    "west": longitude - _NEARBY,
                    "east": longitude + _NEARBY,
                    "scale": scale,
                },
            ).fetchone()
        return _place_from(row) if row is not None else None

    @property
    def stale(self) -> bool:
        """Whether this index was built by rules the code no longer uses.

        An empty index is never stale: nothing has been built by any rules, so
        none of them are out of date.
        """
        return self._built_by != RULES and self.held() > 0

    def stamp(self, rules: int = RULES) -> None:
        """Record which rules built what is here.

        SQLite's own `user_version`, which costs no table and no migration and
        is exactly what it is for.
        """
        with self._writing() as connection:
            #  Not a parameter: PRAGMA will not take one.
            connection.execute(f"PRAGMA user_version = {int(rules)}")
        self._built_by = int(rules)

    def held(self) -> int:
        """How many places the index holds, for a page that says so."""
        with self._lock:
            (count,) = self._connection.execute("SELECT COUNT(*) FROM places").fetchone()
        return int(count)


def _keys_for(place: Place) -> set[str]:
    """Every folded string that should find this place: its own name.

    **Not its alternate names.** They were indexed once and it was a mistake
    that took three rounds of filtering to stop being obviously wrong and never
    stopped being wrong: keying `A` offered Oslo, because one of its alternates
    is `Asloa`. A reader cannot be shown a place whose name does not begin with
    what they typed and be expected to work out why.

    What was lost is smaller than it looks. GeoNames' own `name` is already the
    name an English reader knows -- Munich, Vienna, Prague, Rome, Moscow,
    Tokyo, Beijing are all filed under exactly those -- so the alternates were
    buying the occasional Koln-for-Cologne and paying for it with airport
    codes, romanisations from other scripts, and a Cyrillic Madrid with a Latin
    `a` typed into the middle of it.

    Doing it properly needs the alternates to say which language they are in,
    which the main dump's column does not and `alternateNamesV2` does. Until
    then a reader keys what the screen shows them.

    A set, because a place whose ascii name equals its name -- most of them --
    would otherwise be indexed twice under one key. Empty keys are dropped
    rather than stored: `1770` in Queensland folds to nothing, and a key of ""
    is one that every query in the world matches the front of.
    """
    return {key for key in map(search_key, (place.name, place.ascii_name)) if key}






def _after(prefix: str) -> str:
    """The first string that is not under this prefix, for a range scan.

    Keys hold nothing but A-Z, so stepping the last letter on is enough; there
    is no character between Z and the next code point to be missed.
    """
    return prefix[:-1] + chr(ord(prefix[-1]) + 1)


def _place_from(row: sqlite3.Row) -> Place:
    return Place(
        geoname_id=row["geoname_id"],
        name=row["name"],
        ascii_name=row["ascii_name"],
        alternate_names=tuple(name for name in row["alternate_names"].split(",") if name),
        latitude=row["latitude"],
        longitude=row["longitude"],
        feature_class=row["feature_class"],
        feature_code=row["feature_code"],
        country=row["country"],
        admin1=row["admin1"],
        population=row["population"],
        elevation=row["elevation"],
        timezone=row["timezone"],
    )
