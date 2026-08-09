"""The domain: what this service knows about weather.

Nothing here mentions met.no, JSON or HTTP. That is the seam another source
slots into -- and unlike Stardot's, whose second implementation is expected,
this one exists mainly to keep the page handlers honest: a page drawn from a
`Forecast` cannot accidentally come to depend on the shape of somebody's API
response.

Readings are optional throughout. A missing reading is not nought degrees, and
on a weather page that difference matters more than almost anywhere else.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Moment:
    """The weather at one time, and what it will do for a while after."""

    at: datetime
    """In UTC. The place's own zone is applied when a page is drawn, because a
    forecast is not about one reader."""

    temperature: float | None = None
    """Degrees Celsius."""

    wind_speed: float | None = None
    """Metres per second, which is what Norwegian forecasts are read in."""

    wind_from: float | None = None
    """Degrees, meteorological: the direction the wind blows *from*."""

    cloud_cover: float | None = None
    """Percent of the sky covered."""

    humidity: float | None = None
    """Percent, relative."""

    pressure: float | None = None
    """Hectopascals, at sea level."""

    symbol: str | None = None
    """met.no's own name for the weather -- `rain`, `cloudy`, `clearsky_day`.

    Kept as the source's word rather than mapped to something of our own here:
    what a symbol becomes on a forty-column screen is the drawing layer's
    business, and there are ninety of them.
    """

    precipitation: float | None = None
    """Millimetres, over the period `covers` names."""

    covers: timedelta | None = None
    """What period `symbol` and `precipitation` describe.

    Carried because 1.7mm in an hour and 1.7mm over six are different weather,
    and a page showing only the figure could not tell them apart. None on the
    last moment, which has no period after it inside the forecast.
    """


@dataclass(frozen=True)
class Forecast:
    """What one place's weather will do, as far ahead as anyone will say."""

    updated_at: datetime
    """When the meteorologists last ran it -- not when we fetched it."""

    moments: tuple[Moment, ...] = ()
    """In time order. Hourly at first and coarser further out, which is the
    source's doing and is left as it arrives: pretending to an hourly forecast
    ten days ahead would be inventing weather."""

    def current(self, when: datetime) -> Moment | None:
        """The moment a reader at `when` is standing in.

        The last one that has started, rather than the nearest one: at 12:59 the
        weather is the noon hour's, and rounding to the nearest would show a
        reader weather that has not happened yet.

        Falls forward to the first moment where the whole forecast is still
        ahead -- an answer fetched at 09:58 can begin at 10:00 -- because the
        nearest thing to now is then the only honest thing to show, and showing
        nothing would read as a fault.
        """
        current = None
        for moment in self.moments:
            if moment.at > when:
                break
            current = moment
        return current or (self.moments[0] if self.moments else None)
