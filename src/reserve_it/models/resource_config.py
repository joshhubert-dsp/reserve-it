from datetime import time
from functools import cached_property
from typing import Annotated, Self

from loguru import logger
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from reserve_it.models.field_types import AmPmTime, HtmlFormInputType, PositiveInt

HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]


class CalendarInfo(BaseModel):
    id: str
    color: HexColor


class CustomFormField(BaseModel):
    """
    Custom html form input fields can be defined for a resource, either in your python
    source (handy for global custom fields), or in its config yaml file (good for
    individual custom fields).
    You can directly specify any legal html form attribute as a key/value pair.
    Just make sure to also subclass the ReservationRequest model for proper validation
    of custom fields.
    NOTE: the name value is used by both an input's name and id attribute (for linking
    the input to the label).
    """

    type: HtmlFormInputType
    name: str
    label: str
    required: bool = True
    title: str = ""

    model_config = ConfigDict(extra="allow")


class ResourceConfig(BaseSettings):
    """Base reservation configuration model. Works as is, or subclass to add extras.
    Encapsulates as many individual calendars as you put in the calendars dict,
    and together they constitute the total reservation capacity for a resource.

    Any settings you want to be constant for all resources in your system can be set
    globally using environment variables with the same names (case-insensitive), they
    are automatically loaded.

    Args:
        file_prefix (str): the loaded yaml file prefix for this resource, used as a
            short name in the app.
        route_prefix (str): the fastapi endpoint prefix for this resource, will be
            `/file_prefix` unless there's only one resource, then it will be set to
            the empty string to avoid an unnecessary extra url path component.
        resource_name (str): the webpage title for this resources.
        calendars (dict[str, CalendarInfo]): dict of "calendar short name" to
            CalendarInfos for each individual calendar.
        day_start_time (AmPmTime): The beginning of the day for a resource. Defaults to
            12:00 AM.
        day_end_time (AmPmTime): The end of the day for a resource. Defaults to
            11:59 PM.
        minutes_increment (int): Positive integer, the increment between allowed
            start/end time slots. Defaults to 30.
        maximum_minutes (int): Positive integer, the maximum number of minutes allowed
            for a reservation. Must be a multiple of minutes_increment. Defaults to 120.
        maximum_days_ahead (int | None): Positive integer, how many days ahead the user
            can reserve this resource. If None, reservations can be made for any time
            in the future. Defaults to 14.
        minutes_before_reminder (int): Positive integer, how many minutes before the
            event to send an email reminder to the user, if they've selected to receive
            one.
        allow_end_next_day (bool): Include the checkbox for making a reservation end time
            the next day. Should be enabled if overnight reservations are allowed.
            Defaults to False.
        allow_shareable (bool): Include the checkbox for the user to note that they're
            willing to share a resource. Should only be enabled for a resource that can
            be shared. Defaults to False.
        emoji (str): emoji symbol to append to the title. Defaults to ''.
        description (str): descriptive sub-heading for the resource page. Defaults to ''.
        custom_form_fields (list[CustomFormField]): custom html form input fields to add
            for the resource page. Defaults to empty list.


    """

    file_prefix: str
    route_prefix: str
    resource_name: str
    calendars: dict[str, CalendarInfo]
    day_start_time: AmPmTime = Field(default_factory=lambda: time(hour=0, minute=0))
    day_end_time: AmPmTime = Field(default_factory=lambda: time(hour=23, minute=59))
    minutes_increment: PositiveInt = 30
    maximum_minutes: PositiveInt = 120
    maximum_days_ahead: PositiveInt | None = 14
    minutes_before_reminder: PositiveInt = 60
    allow_end_next_day: bool = False
    allow_shareable: bool = False
    emoji: str = ""
    description: str = ""
    custom_form_fields: list[CustomFormField] = Field(default_factory=list)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def end_after_start(self) -> Self:
        if self.day_start_time >= self.day_end_time:
            raise ValueError("day_start_time must be before day_end_time.")
        return self

    @model_validator(mode="after")
    def maximum_minutes_is_multiple(self) -> Self:
        if self.maximum_minutes % self.minutes_increment:
            raise ValueError("maximum_minutes must be a multiple of minutes_increment.")
        return self

    @cached_property
    def calendar_ids(self) -> dict[str, str]:
        """dict[cal_id, event_label], this ends up being useful."""
        return {cal.id: label for label, cal in self.calendars.items()}

    @classmethod
    def model_validate_logging(cls, obj: dict, *, context=None, **kwargs):
        """model_validate overload that adds helpful error log for determining which
        resource config is bad in the case of many resources
        """
        try:
            return super().model_validate(obj, context=context, **kwargs)
        except ValidationError as e:
            logger.error(
                f"Error loading ResourceConfig for resource '{obj['route_prefix']}': {e}"
            )
            # Kill the process cleanly; uvicorn etc will just see a non-zero exit
            raise SystemExit(1) from e
