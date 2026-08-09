"""met.no's `locationforecast/2.0/compact`, read into the domain.

Everything above this deals in `Forecast` and `Moment` and has never heard of
JSON. The parsing is a pure function over a decoded response, which is what
lets it be exercised against a real capture rather than a mock.

Two things about the format are worth knowing before reading the code, both
established from a real response rather than from documentation:

**The series changes resolution part way along.** The first two or three days
are hourly and the rest six-hourly, so `next_1_hours` is present at the start
and absent later. Which blocks a moment carries is the source telling you how
specific it is prepared to be.

**A block describes the period *after* the moment it hangs on**, not the moment
itself. So a moment's symbol is what the weather will do next, and the last
moment in the series has no block at all -- there is no next hour inside the
forecast for it to summarise.
"""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from weather_viewdata.forecast.model import Forecast, Moment

#: The blocks a moment may carry, shortest first. The shortest present is used,
#: which keeps the answer as specific as the data allows.
_BLOCKS: Final = (
    ("next_1_hours", timedelta(hours=1)),
    ("next_6_hours", timedelta(hours=6)),
    ("next_12_hours", timedelta(hours=12)),
)


def parse_forecast(document: Mapping[str, Any]) -> Forecast:
    """Read a decoded `compact` response."""
    properties = document["properties"]
    return Forecast(
        updated_at=_instant(properties["meta"]["updated_at"]),
        moments=tuple(_moment(entry) for entry in properties["timeseries"]),
    )


def _moment(entry: Mapping[str, Any]) -> Moment:
    data = entry["data"]
    details = data.get("instant", {}).get("details", {})
    block, covers = _shortest_block(data)
    return Moment(
        at=_instant(entry["time"]),
        temperature=details.get("air_temperature"),
        wind_speed=details.get("wind_speed"),
        wind_from=details.get("wind_from_direction"),
        cloud_cover=details.get("cloud_area_fraction"),
        humidity=details.get("relative_humidity"),
        pressure=details.get("air_pressure_at_sea_level"),
        symbol=block.get("summary", {}).get("symbol_code"),
        precipitation=block.get("details", {}).get("precipitation_amount"),
        covers=covers,
    )


def _shortest_block(
    data: Mapping[str, Any],
) -> tuple[Mapping[str, Any], timedelta | None]:
    """The most specific summary a moment carries, and what period it covers."""
    for name, covers in _BLOCKS:
        block = data.get(name)
        if block is not None:
            return block, covers
    #  The last moment in the series, which has nothing after it to describe.
    return {}, None


def _instant(stamp: str) -> datetime:
    """One of met.no's times, which are Zulu.

    `fromisoformat` reads the `Z` from Python 3.11, and the result is made
    explicitly UTC-aware rather than left to be inferred -- a naive datetime
    escaping into a service that shows times in a place's own zone would be
    wrong by hours and look plausible.
    """
    return datetime.fromisoformat(stamp).astimezone(UTC)
