"""The weather service's command line.

Serving and drawing are the framework's, but the place index is this
application's own and so is filling it. Both halves default the index's location
the same way, so that they agree about where it is without being told twice.
"""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from sextile import Sextile
from sextile.cli import add_standard_subcommands, run_standard

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


def build_parser() -> argparse.ArgumentParser:
    """The command line this service answers to, subcommands and all."""
    parser = argparse.ArgumentParser(
        prog="weather-viewdata",
        description="The weather as a Viewdata service",
    )
    parser.add_argument(
        "--version", action="version", version=f"weather-viewdata {__version__}"
    )
    subcommands = parser.add_subparsers(dest="command")

    importing = subcommands.add_parser(
        "import-places",
        help="Fill the place index from GeoNames' dump, downloading it if needed",
    )
    importing.add_argument(
        "--dump",
        type=Path,
        default=DEFAULT_DUMP_FILEPATH,
        help=f"Where the dump is kept (default: {DEFAULT_DUMP_FILEPATH})",
    )
    importing.add_argument(
        "--url",
        default=CITIES_500,
        help="Which dump to fetch (default: cities500, every place of 500 or more)",
    )
    importing.add_argument(
        "--offline",
        action="store_true",
        help="Import the dump already on disk without asking whether it has changed",
    )
    #  The service is global -- met.no forecasts anywhere -- but its readers
    #  are mostly not, this being a retrocomputing curiosity dialled largely
    #  from Britain. So the ranking leans that way by default and is one flag
    #  away from leaning elsewhere.
    importing.add_argument(
        "--prefer",
        metavar="COUNTRY",
        default="GB",
        help="Two-letter code whose places win ties against others of similar "
             "size (default: GB). Use --prefer '' for no preference at all.",
    )
    _add_index_argument(importing)

    add_standard_subcommands(
        subcommands, configure=_add_index_argument, page_example="1 or 3213133880"
    )

    return parser


def _add_index_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--index",
        type=Path,
        default=DEFAULT_INDEX_FILEPATH,
        help=f"The place index (default: {DEFAULT_INDEX_FILEPATH})",
    )


def import_command(arguments: argparse.Namespace) -> int:
    """Fill the gazetteer from a GeoNames dump, downloading it if need be.

    Args:
        arguments: The parsed command line, which says where the dump and
            the index live and whether to work offline.

    Returns:
        The process exit status: nought where the import succeeded.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("weather-viewdata")

    if not arguments.offline:
        log.info("Asking %s whether it has changed", arguments.url)
        fetched = download_dump(arguments.url, arguments.dump)
        log.info("Downloaded." if fetched else "Unchanged; using the dump on disk.")
    elif not arguments.dump.exists():
        log.error("No dump at %s, and --offline says not to fetch one.", arguments.dump)
        return 1

    with Index.open(arguments.index) as index:
        taken = import_places(
            arguments.dump,
            index,
            prefer_country=arguments.prefer or None,
            #  Every batch, which at five thousand a line is a readable rate
            #  for a couple of hundred thousand places.
            progress=lambda so_far: log.info("%d places", so_far),
        )
    log.info("%d places in %s", taken, arguments.index)
    return 0


def _application(arguments: argparse.Namespace) -> Sextile:
    return build_application(source=MetNoSource(), index_filepath=arguments.index)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command.

    Args:
        argv: The arguments after the program name, or None to take
            them from `sys.argv`.

    Returns:
        The process exit status: nought where the command succeeded.
    """
    parser = build_parser()
    arguments = parser.parse_args(argv)

    standard = run_standard(arguments, load=_application)
    if standard is not None:
        return standard

    if arguments.command == "import-places":
        return import_command(arguments)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
