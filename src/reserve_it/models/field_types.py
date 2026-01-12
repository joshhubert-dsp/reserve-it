"""
Definitions of custom types for `ResourceConfig` fields.
"""

from datetime import datetime, time
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, FilePath, StringConstraints
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
"""Possible values for the `type` argument of a custom form input field."""


class CalendarInfo(BaseModel):
    """Loaded from resource config yaml as the values under the `calendars` dictionary.
    Each identifies a Google calendar mapping to an individually reservable resource
    (ie. a single tennis court out of many).

    Args:
        id (str): The ID string for the Google calendar, of the form
            "[longhexstring]@group.calendar.google.com".
        color (HexColor | None , optional): Color hex string with 6 digits (no alpha),
            ie. "#AAAAAA", used for the color of the Google calendar in the embedded
            calendar view. Can be omitted from the yaml dict if you don't care. Also it
            will not be used if a resource has more than 4 calendars, since then the
            calendars won't be shown.Defaults to None.
    """

    id: str
    color: HexColor | None = None


class CustomFormField(BaseModel):
    """
    Custom html form input fields can be defined for a resource, either globally in
    app-config.yaml, or per resource in its own resource config yaml file.
    You can directly specify any additional legal html form attributes as a key/value pair.
    Just make sure to also subclass the ReservationRequest model for proper validation
    of custom fields.

    Args:
        type (HtmlFormInputType): A string specifying for one of the legal form input types.
        name (str): The name value is used by both an input's returned key name
            (made accessible to ReservationRequest for validation) and id attribute (for
            linking the input to the label).
        label (str): The label text that appears above the form input box.
        required (bool, optional): Whether the field is requiered. Defaults to True.
        title (str, optional): This is the "tool tip" text that will appear over the
            input when you mouse over it.
    """

    type: HtmlFormInputType
    name: str
    label: str
    required: bool = True
    title: str = ""

    model_config = ConfigDict(extra="allow")


class ImageFile(BaseModel):
    """Bundle of info for an image to display on a reservation webpage. Uses the image's
    actual dimensions if not specified. If both pixel_width and pixel_height are None,
    then the rendered image uses the original image's actual dimensions. If only one of them is
    None, then the rendered image keeps the original image's aspect ratio.

    Args:
        path (Path): Image filepath. Must be relative to the resource-configs directory.
        caption (str, optional): Caption to display for the image. Defaults to "".
        pixel_width (int | None , optional): Desired pixel width for the displayed image.
            Defaults to None. See above for behavior details.
        pixel_height (int | None , optional): Desired pixel height for the displayed image.
            Defaults to None. See above for behavior details.
    """

    path: Path
    caption: str = ""
    pixel_width: int | None = None
    pixel_height: int | None = None
