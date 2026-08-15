"""Where a forecast comes from.

The port. Everything above it asks a `ForecastSource` for a `Forecast` and has
never heard of met.no, HTTP or JSON. A page handler that knew how the data
arrived would have to be rewritten when it arrived differently.

A source returns `None` where it has nothing to give. That is deliberately the
same shape a Sextile handler uses for a page that is not there, and it means a
page can say *why* there is no forecast rather than drawing an empty one --
which on a weather service reads as calm weather.
"""

from abc import ABC, abstractmethod

from weather_viewdata.forecast.model import Forecast
from weather_viewdata.geonames import Place


class AnonymousError(RuntimeError):
    """A source was built without saying who is asking.

    met.no requires an identifying User-Agent carrying somewhere to complain
    to, and the stated penalty for going without is being blocked with no
    warning. Their side was found to answer an anonymous request anyway, which
    means nothing but this stops us making one.
    """


class ForecastSource(ABC):
    """Somewhere forecasts come from."""

    @abstractmethod
    async def forecast_for(self, place: Place) -> Forecast | None:
        """This place's weather, or None if it cannot be had just now."""

    #  Empty on purpose, and not abstract: a source with nothing open has
    #  nothing to close, and should not be made to say so.
    async def aclose(self) -> None:  # noqa: B027
        """Let go of whatever was opened. Nothing, unless a source says so."""
