"""The weather service's command line.

Serving and drawing are the framework's, but the place index is this
application's own and so is filling it. Both halves default the index's location
the same way, so that they agree about where it is without being told twice.
"""

import logging
from pathlib import Path
from typing import Any, Final

import click
from sextile import Sextile
from sextile.cli import CONTEXT_SETTINGS, standard_commands

from weather_viewdata import __version__
from weather_viewdata.application import build_application
from weather_viewdata.dump import CITIES_500, download_dump
from weather_viewdata.forecast.met import MetNoSource
from weather_viewdata.importing import import_places
from weather_viewdata.store import Index

#: Beside the working directory, as Stardot's archive is. Noted in the
#: workspace's open questions as wanting `platformdirs` instead.
DEFAULT_INDEX_FILEPATH: Final = Path("places.sqlite")

#: Where the dump is kept between imports, so that a re-import that finds
#: nothing changed costs one request and no download.
DEFAULT_DUMP_FILEPATH: Final = Path("cities500.zip")


def _index_option(command: Any) -> Any:
    """Add `--index` to a Click command, naming the place index.

    Applied to `render`, `serve` and `import-places` alike, so all three agree
    about where the index lives without the service saying it three times.
    """
    return click.option(
        "--index",
        "index_filepath",
        type=click.Path(path_type=Path),
        default=DEFAULT_INDEX_FILEPATH,
        help=f"The place index (default: {DEFAULT_INDEX_FILEPATH})",
    )(command)


def _application(context: click.Context) -> Sextile:
    """Build the service from a standard command's parsed options."""
    return build_application(
        source=MetNoSource(), index_filepath=context.params["index_filepath"]
    )


@click.group(context_settings=CONTEXT_SETTINGS, help="The weather as a Viewdata service")
@click.version_option(__version__, "--version", message="weather-viewdata %(version)s")
def main() -> None:
    """The command line this service answers to, subcommands and all."""


@main.command(
    "import-places",
    context_settings=CONTEXT_SETTINGS,
    help="Fill the place index from GeoNames' dump, downloading it if needed",
)
@click.option(
    "--dump",
    "dump_filepath",
    type=click.Path(path_type=Path),
    default=DEFAULT_DUMP_FILEPATH,
    help=f"Where the dump is kept (default: {DEFAULT_DUMP_FILEPATH})",
)
@click.option(
    "--url",
    default=CITIES_500,
    help="Which dump to fetch (default: cities500, every place of 500 or more)",
)
@click.option(
    "--offline",
    is_flag=True,
    help="Import the dump already on disk without asking whether it has changed",
)
#  The service is global -- met.no forecasts anywhere -- but its readers are
#  mostly not, this being a retrocomputing curiosity dialled largely from
#  Britain. So the ranking leans that way by default and is one flag away from
#  leaning elsewhere.
@click.option(
    "--prefer",
    metavar="COUNTRY",
    default="GB",
    help="Two-letter code whose places win ties against others of similar "
    "size (default: GB). Use --prefer '' for no preference at all.",
)
@_index_option
@click.pass_context
def import_command(
    context: click.Context,
    /,
    dump_filepath: Path,
    url: str,
    offline: bool,
    prefer: str,
    index_filepath: Path,
) -> None:
    """Fill the gazetteer from a GeoNames dump, downloading it if need be.

    Args:
        context: The Click context, whose exit status this sets.
        dump_filepath: Where the GeoNames dump is kept.
        url: Which dump to fetch.
        offline: Whether to import the dump on disk without checking for changes.
        prefer: A two-letter country code whose places win ties, or empty for
            no preference.
        index_filepath: Where the place index lives.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("weather-viewdata")

    if not offline:
        log.info("Asking %s whether it has changed", url)
        fetched = download_dump(url, dump_filepath)
        log.info("Downloaded." if fetched else "Unchanged; using the dump on disk.")
    elif not dump_filepath.exists():
        log.error("No dump at %s, and --offline says not to fetch one.", dump_filepath)
        context.exit(1)

    with Index.open(index_filepath) as index:
        taken = import_places(
            dump_filepath,
            index,
            prefer_country=prefer or None,
            #  Every batch, which at five thousand a line is a readable rate
            #  for a couple of hundred thousand places.
            progress=lambda so_far: log.info("%d places", so_far),
        )
    log.info("%d places in %s", taken, index_filepath)


for _standard_command in standard_commands(
    _application, options=[_index_option], page_example="1 or 3213133880"
):
    main.add_command(_standard_command)


if __name__ == "__main__":
    main()
