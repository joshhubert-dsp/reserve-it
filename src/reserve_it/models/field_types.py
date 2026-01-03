from datetime import datetime, time
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, FilePath, StringConstraints
from pydantic.functional_validators import AfterValidator


def must_be_yaml(p: Path) -> Path:
    if p.suffix.lower() != ".yaml" and p.suffix.lower() != ".yml":
        raise ValueError(f"'{p}' must be a yaml file")
    return p


YamlPath = Annotated[FilePath, AfterValidator(must_be_yaml)]


AM_PM_TIME_FORMAT = "%I:%M %p"


def parse_ampm_time(v: Any) -> time:
    if isinstance(v, time):
        return v
    if isinstance(v, datetime):
        return v.time()
    if isinstance(v, str):
        return datetime.strptime(v, AM_PM_TIME_FORMAT).time()
    raise TypeError(f"Expected datetime, time or AM/PM string, got {type(v)!r}")


AmPmTime = Annotated[time, BeforeValidator(parse_ampm_time)]
"""Clock time that can be parsed from a string in AM/PM 12-hour format, `HH:MM AM/PM`."""

HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]
"""Color hex string with 6 digits (no alpha), ie. "#AAAAAA", used for the color of individual resource
calendars in the embedded calendar view"""

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
]
""""Possible values for the `type` argument of a custom form input field."
"""
