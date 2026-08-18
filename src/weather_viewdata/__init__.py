"""The weather as a Viewdata service: the third Sextile application."""

from importlib.metadata import version

from weather_viewdata.application import SERVICE_NAME, build_application

__version__ = version("weather-viewdata")

__all__ = ["SERVICE_NAME", "build_application", "__version__"]
