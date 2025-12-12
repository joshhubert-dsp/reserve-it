from datetime import datetime, time
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field, StringConstraints

PositiveInt = Annotated[int, Field(gt=0)]

AM_PM_TIME_FORMAT = "%I:%M %p"


def parse_ampm_time(v: Any) -> time:
    if isinstance(v, time):
        return v
    if isinstance(v, datetime):
        return v.time()
    if isinstance(v, str):
        return datetime.strptime(v, AM_PM_TIME_FORMAT).time()
    raise TypeError(f"Expected datetime, time or AM/PM string, got {type(v)!r}")


AmPmTime = Annotated[
    time,
    BeforeValidator(parse_ampm_time),
    Field(
        description="Clock time that can be parsed from a string in AM/PM 12-hour format."
    ),
]

HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]

HtmlFormInputType = Literal[
    "button",
    "checkbox",
    "color",
    "date",
    "datetime-local",
    "email",
    "file",
    "hidden",
    "image",
    "month",
    "number",
    "password",
    "range",
    "reset",
    "search",
    "submit",
    "tel",
    "text",
    "time",
    "url",
    "week",
    Field(
        description="Possible values for the type argument of a custom form input field."
    ),
]
