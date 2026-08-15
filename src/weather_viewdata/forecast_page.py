"""Drawing one forecast as a page.

Everything between a `Forecast` and the frames that show it: the table of
days, the weather-now block, the two clocks, and the words for a position.
The handlers that fetch the forecast are in `pages`; anything a page draws
that is more than a row of text is here or in `hours`, `days` and `icons`.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import ClassVar, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sextile import Page, PageAddress, PageRequest, keyed, prose_page
from sextile.formatting import Lines, SequencePart
from sextile.layout import Custom, Flow, OnEveryFrame, OnOneFrame, PageLayout, Part, Shortcut
from sextile.viewdata.canvas import Canvas, Span
from sextile.viewdata.controls import Colour
from sextile.viewdata.encoding import cell_count, fitted
from sextile.viewdata.frame import COLUMNS
from weather_viewdata.days import HEADINGS, PICTURE_ROWS, Day, days_of, draw_day
from weather_viewdata.forecast.model import Forecast, Moment
from weather_viewdata.geonames import Place
from weather_viewdata.hours import HOURS_SHOWN, LABEL_CELLS, STRIP_ROWS, draw_strip
from weather_viewdata.icons import BANDS, COLUMN_CELLS, icon_for
from weather_viewdata.icons import draw as draw_icon
from weather_viewdata.store import Nearby
from weather_viewdata.symbols import in_words
from weather_viewdata.wind import from_the

#: The key that goes back to the search a reader came through. `F` for find,
#: which is what the page it leads to is called; `S` for search would have been
#: the obvious letter and is the framework's key for paging down.
FIND_KEY: Final = "F"

#: Rows the weather-now block takes: the picture is three cells tall and the
#: words beside it are two, so the first of the three is the picture's top band
#: and nothing else.
NOW_ROWS: Final = BANDS

#: What an attribute costs, where the cost has to be counted before the writing
#: rather than charged during it.
_ATTRIBUTE_CELL: Final = 1

#: Seconds an hour, for saying what period a rainfall figure covers, and an
#: hour itself for the moment at the end of a forecast, which carries no period
#: of its own because there is no next moment inside it.
_SECONDS_AN_HOUR: Final = 3600
_AN_HOUR: Final = timedelta(hours=1)

#: What separates the two ends of a range. A bar the full width of the cell,
#: which G0 keeps at 0x60 where ASCII has its backtick, rather than the hyphen
#: at 0x2D -- read out of Beebium's font. Not the underscore, whatever a
#: teletext editor's keyboard suggests: 0x5F is the hash.
_TO: Final = "―"


def forecast_page(
    request: PageRequest,
    place: Place,
    forecast: Forecast | None,
    *,
    near: Nearby | None = None,
    back_to: PageAddress | None = None,
) -> Page:
    """One place's weather, dealt into frames.

    A page with nothing to show says why. An empty table would read as calm
    weather, which is the one wrong answer a weather service must not give.
    """
    #  Offered on the page that says there is no forecast as well as on the one
    #  that has it: a reader told to come back in a few minutes is a reader
    #  who may prefer to go and look somewhere else instead.
    shortcuts = () if back_to is None else (Shortcut(FIND_KEY, back_to, "find"),)
    if forecast is None or not forecast.moments:
        return prose_page(
            request,
            f"No forecast for {place.name} just now.",
            "The Norwegian Meteorological Institute did not answer. This is our "
            "trouble rather than yours.",
            f"Key {keyed(request.address)} again in a few minutes.",
            title=_heading(place),
            shortcuts=shortcuts,
        )
    zone = _zone_of(place)
    now = forecast.current(datetime.now(UTC))
    #  The strip shows the hours after now; the days show all of them, today
    #  included. They are not one forecast said twice: the first is what this
    #  afternoon will do, the second which day to go out on.
    coming = [moment for moment in forecast.moments if now is None or moment.at > now.at]
    return PageLayout(
        title=_heading(place),
        #  Not `S`, which pages down, and not `0`, which is the index. A reader
        #  who has just found a place usually wants the next place, and the way
        #  back to the search is otherwise three keys and a page they have to
        #  remember the number of.
        shortcuts=shortcuts,
        parts=[
            *_preamble(place, forecast, near, coming),
            #  On every frame: a reader on frame c looking at four columns of
            #  figures has no way back to the words that say what they are.
            OnEveryFrame(Lines((HEADINGS,), colour=Colour.CYAN)),
            Flow(
                ForecastTable(
                    entries=days_of(forecast.moments, zone, from_day=_today(zone)),
                    today=_today(zone),
                )
            ),
        ],
    ).build(request)


@dataclass(frozen=True, kw_only=True)
class ForecastTable(SequencePart[Day]):
    """The days ahead, one to a block of four rows.

    Three rows of pictures and a blank, or two days running would read as one
    six-row block. Nothing on it is selectable: a forecast is something to
    read, not a menu, so no digit is spent on the rows and 1-9 do nothing here
    -- which is the rule about naming only the keys that work, rather than an
    exception to it. A `SequencePart` rather than a `RowSequencePart`: a day is
    placed by cell.
    """

    rows_per_entry: ClassVar[int] = PICTURE_ROWS
    gap: ClassVar[int] = 1
    numbered: ClassVar[bool] = False

    today: date

    def draw_entry(
        self, canvas: Canvas, row: int, entry: Day, digit: str | None = None
    ) -> None:
        draw_day(canvas, row, entry, self.today)


def _heading(place: Place) -> str:
    return fitted(place.name.upper(), COLUMNS - 12)


def _preamble(
    place: Place,
    forecast: Forecast,
    near: Nearby | None,
    coming: Sequence[Moment],
) -> list[Part]:
    """Where this is, which clocks it keeps, how old it is, and the weather now.

    A blank row after the position, and then the weather the reader is standing
    in -- three rows of it, since that is what a picture is tall, with the issue
    time filling the first of them beside the picture's top band.

    Returns the parts to lay above the table, each drawn on the first frame
    alone, with a blank row after the last of them.
    """
    lines: list[Part] = [OnOneFrame(Lines((_where(place, near), "")))]
    zone = _zone_of(place)
    now = forecast.current(datetime.now(UTC))
    issued = f"Issued {forecast.updated_at:%H:%M} UTC"
    if now is not None:
        lines.append(
            OnOneFrame(
                Custom(
                    rows=NOW_ROWS,
                    draw=lambda canvas, row: _draw_now(canvas, row, now, zone, issued),
                )
            )
        )
    else:
        lines.append(OnOneFrame(Lines((issued,))))
    if coming:
        #  Drawn rather than written, and the layout counts its rows like any
        #  others -- so the strip filling what is left of the frame simply
        #  leaves the table to start on the next one. Its own rules separate it
        #  from what is above and below.
        hours = list(coming[:HOURS_SHOWN])
        clock = _clock_name(zone)
        lines.append(
            OnOneFrame(
                Custom(
                    rows=STRIP_ROWS,
                    draw=lambda canvas, row: draw_strip(canvas, row, hours, zone, clock),
                )
            )
        )
    #  A blank row between the lead-in and the table, so the two read as two
    #  things, stated as a part rather than added automatically.
    lines.append(OnOneFrame(Lines(("",))))
    return lines


def _draw_now(
    canvas: Canvas, row: int, moment: Moment, zone: ZoneInfo | None, issued: str
) -> None:
    """The weather now: a picture, and three rows of words beside it.

    Three rows, because the picture is three cells tall. The issue time takes
    the first of them, which was blank when the picture arrived and is a row
    the charts below now want: met.no runs its models a few times a day, so a
    forecast fetched at nine may have been made at five, and a reader on a slow
    line deciding whether to ask again wants to know which.

    **Both clocks on one row, each saying which it is.** They were on separate
    rows -- `Times UTC and CEST (UTC+2)` above `NOW 16:00 18:00` -- and the
    saving is a row and a repetition: put the labels beside the times and the
    times explain the labels, so the offset in brackets is the only part that
    has to be said at all.

    **An hour, said as an hour.** `NOW 16:00` under `Issued 16:29` reads as a
    contradiction and is not one: met.no's series begins at the hour containing
    the model run -- measured, `updated_at` 15:29 with a first moment of 15:00
    -- so a forecast issued at half past can perfectly well tell you about the
    hour that began at the top of it. What was wrong was the word `NOW` beside
    a single time, which promises an instant. `16-17` promises the hour, which
    is what the readings are for and what a reader at 16:45 is standing in.
    """
    room = COLUMNS
    picture = icon_for(moment.symbol)
    if picture is not None:
        draw_icon(canvas, row, COLUMNS - COLUMN_CELLS, picture)
        #  No gap is added: the picture's own attribute cell is a blank one,
        #  and a second would be a cell spent twice on the same air.
        room = COLUMNS - COLUMN_CELLS
    canvas.row(row).text(fitted(issued, room), Colour.WHITE)
    canvas.row(row + 1).runs(_within(_clock_runs(moment, zone, room), room))
    canvas.row(row + 2).runs(_within(_figure_runs(moment), room))


def _clock_runs(moment: Moment, zone: ZoneInfo | None, room: int) -> list[Span]:
    """`NOW 16-17 UTC 18-19 CEST (UTC+2)`, in yellow and cyan.

    One space between the runs rather than two, because each of them already
    begins with an attribute cell that draws as a space. Two would be a gap of
    three, and the offset in brackets is what would pay for it.

    The offset goes only if the whole of it fits. Trimmed, `(UTC+5.75)` becomes
    `(UTC+5.` -- an answer that looks like a fact and is not one -- so it is
    dropped whole where there is no room, the two clocks side by side saying
    the same thing to anyone who cares to subtract.
    """
    runs = [Span("NOW", Colour.WHITE), Span(f" {_span(moment, None)} UTC", Colour.YELLOW)]
    if zone is None:
        return runs
    named, offset = _zone_named(zone)
    local = f" {_span(moment, zone)} {named}".rstrip()
    with_offset = f"{local} (UTC{offset})" if offset else local
    spent = sum(_ATTRIBUTE_CELL + cell_count(run.text) for run in runs)
    fits = spent + _ATTRIBUTE_CELL + cell_count(with_offset) <= room
    runs.append(Span(with_offset if fits else local, Colour.CYAN))
    return runs


def _span(moment: Moment, zone: ZoneInfo | None) -> str:
    """The hours a moment covers, in one clock, as a range.

    Hours alone where the range falls on them, which is everywhere a zone is a
    whole number of hours from UTC. Where it is not -- Kolkata is half an hour
    off and Kathmandu three quarters -- the minutes are shown, and it is the
    offset in brackets that gives way to make room for them.

    **The separator is a long dash and not a hyphen.** G0 has both: 0x2D is the
    hyphen and 0x60 -- where ASCII keeps its backtick -- is a bar the full width
    of the cell, which is what a range wants. Read out of Beebium's font rather
    than guessed. It is *not* the underscore, whatever a teletext editor's
    keyboard suggests: 0x5F is the hash, the viewdata command key.
    """
    ends = moment.at + (moment.covers or _AN_HOUR)
    start = moment.at.astimezone(zone) if zone is not None else moment.at
    finish = ends.astimezone(zone) if zone is not None else ends
    if start.minute or finish.minute:
        return f"{start:%H:%M}{_TO}{finish:%H:%M}"
    return f"{start:%H}{_TO}{finish:%H}"


def _figure_runs(moment: Moment) -> list[Span]:
    """The readings, and what the weather is called, in that order.

    The words go last and take what is left, which on a bad day is not all of
    them -- `heavy sleet shwrs+thunder` is twenty-five cells. That is a cost
    worth paying here and nowhere else: the picture at the end of the row is
    saying the same thing, and a reader who loses the tail of the words has not
    lost the weather.
    """
    return [
        Span(" ".join(_figures(moment)), Colour.WHITE),
        Span(f" {in_words(moment.symbol)}", Colour.GREEN),
    ]


def _within(runs: list[Span], room: int) -> list[Span]:
    """Runs trimmed to a budget, the last of them giving way first.

    `RowWriter.runs` trims to the end of the row, which is the wrong edge where
    something else is drawn further along it.
    """
    kept: list[Span] = []
    used = 0
    for run in runs:
        left = room - used - _ATTRIBUTE_CELL
        if left <= 0:
            break
        text = fitted(run.text, left)
        kept.append(Span(text, run.colour))
        used += _ATTRIBUTE_CELL + cell_count(text)
    return kept


def _figures(moment: Moment) -> list[str]:
    """Temperature, wind and rain, leaving out what there is no reading for.

    Left out rather than dashed, which is what the table below does. A dash in
    a column means the column is still there to be read; here there are no
    columns, and three words with a gap where the fourth was reads as a gap.
    """
    figures = [f"{_reading(moment.temperature, 1)}C"]
    speed = f"{_reading(moment.wind_speed, 1)}m/s"
    bearing = from_the(moment.wind_from)
    figures.append(f"{bearing} {speed}" if bearing else speed)
    if moment.precipitation is not None:
        figures.append(f"{moment.precipitation:.1f}mm{_over(moment.covers)}")
    return figures


def _over(covers: timedelta | None) -> str:
    """What period a rainfall figure is for.

    1.7mm in an hour and 1.7mm over six are different weather, and the figure
    alone cannot tell them apart. Said as `/h` rather than `/1h` because that is
    how a rate is written and it saves a cell.
    """
    if covers is None:
        return ""
    hours = round(covers.total_seconds() / _SECONDS_AN_HOUR)
    return "/h" if hours == 1 else f"/{hours}h"


def _where(place: Place, near: Nearby | None) -> str:
    """The position, and for a point the nearest place we know of.

    A coordinate page cannot claim to be a town, so it says what it is -- a
    position -- and names the nearest place only as a landmark.
    """
    position = f"{_degrees(place.latitude, 'NS')} {_degrees(place.longitude, 'EW')}"
    if place.elevation is not None:
        position += f"  {place.elevation}m"
    if near is not None:
        #  With the distance, because the nearest place may be ninety
        #  kilometres away and "near" would then be a polite lie.
        return fitted(f"{position}  {landmark(near)}", COLUMNS - 1)
    return fitted(f"{place.country}  {position}", COLUMNS - 1)


def _zone_named(zone: ZoneInfo) -> tuple[str, str]:
    """What a place's clock calls itself, and how far it is from UTC.

    Not every zone has letters -- Fiji reports `+12` -- so a name that is only
    an offset is dropped and the offset in brackets does the saying.
    """
    sample = datetime.now(UTC).astimezone(zone)
    named = sample.tzname() or ""
    offset = sample.utcoffset()
    hours = "" if offset is None else f"{offset.total_seconds() / 3600:+g}"
    return ("" if named.startswith(("+", "-")) else named), hours


def _clock_name(zone: ZoneInfo | None) -> str:
    """The four cells the hour strip has for saying which clock it keeps.

    `CEST`, `AEDT`, `NZDT` -- the abbreviations are four characters or fewer
    wherever a zone has one. Where it has not, or has one too long to draw,
    `loc` says the only thing left that is true.
    """
    if zone is None:
        return "UTC"
    named, _ = _zone_named(zone)
    return named if named and len(named) <= LABEL_CELLS else "loc"


def landmark(near: Nearby) -> str:
    """The nearest place we know of, as a landmark for a position.

    With the country, because a name on its own is not an answer: there are
    nine Wellingtons, and a reader who keys a position in the wrong hemisphere
    is told which one they have found rather than left to wonder. And with the
    distance, because the nearest place may be ninety kilometres away and
    "near" would then be a polite lie.
    """
    return f"{near.kilometres:.0f}km from {near.place.name}, {near.place.country}"


def _degrees(value: float, poles: str) -> str:
    return f"{abs(value):.1f}{poles[0] if value >= 0 else poles[1]}"


def _reading(value: float | None, places: int) -> str:
    """A number, or a dash where there is no reading.

    Not nought. Nought degrees is weather and no reading is not, and a service
    that confuses them is worse than one that says less.
    """
    return "-" if value is None else f"{value:.{places}f}"


def _today(zone: ZoneInfo | None) -> date:
    """The date it is where the forecast is, which is not always ours."""
    return datetime.now(UTC).astimezone(zone).date()


def _zone_of(place: Place) -> ZoneInfo | None:
    try:
        return ZoneInfo(place.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        #  A zone the system database has not heard of. Times go in UTC and the
        #  page says so, which is better than being an hour wrong in silence.
        return None


def point_place(lat: float, lon: float, near: Nearby | None) -> Place:
    """A position, dressed as somewhere a forecast can be asked for.

    It borrows a clock from the nearest known place, because timezone borders
    follow habitation and there is no other way to know one from coordinates
    alone. It borrows no altitude: the nearest town may be a fjord beneath a
    mountain, and met.no's own topography is a better guess than that.
    """
    return Place(
        geoname_id=0,
        name=f"{_degrees(lat, 'NS')} {_degrees(lon, 'EW')}",
        ascii_name="",
        alternate_names=(),
        latitude=lat,
        longitude=lon,
        feature_class="",
        feature_code="",
        country="",
        admin1="",
        population=0,
        elevation=None,
        timezone=near.place.timezone if near is not None else "UTC",
    )
