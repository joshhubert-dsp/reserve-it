from datetime import time
from functools import cached_property
from typing import ClassVar, Self

from loguru import logger
from pydantic import (
    EmailStr,
    Field,
    PositiveInt,
    ValidationError,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from reserve_it.models.field_types import (
    AmPmTime,
    CalendarInfo,
    CustomFormField,
    ImageFile,
)


class ResourceConfig(BaseSettings):
    """Reservation resource configuration model, loaded from the yaml files you add to your
    `resource-configs` directory.
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
        name (str): the webpage title for this resources.
        calendars (dict[str, CalendarInfo]): dict of "calendar short name" to
            CalendarInfos for each individual calendar. If more than 4 calendars are
            included
        day_start_time (AmPmTime, optional): The beginning of the day for a resource,
            passed as a string of the form `HH:MM AM/PM`. Defaults to 12:00 AM.
        day_end_time (AmPmTime, optional): The end of the day for a resource, passed as
            a string of the form `HH:MM AM/PM`. Defaults to 11:59 PM.
        minutes_increment (int, optional): Positive integer, the increment between allowed
            start/end time slots. Defaults to 30.
        maximum_minutes (int, optional): Positive integer, the maximum number of minutes allowed
            for a reservation. Must be a multiple of minutes_increment. Defaults to 120.
        allow_end_next_day (bool, optional): Include the checkbox for making a reservation end time
            the next day. Should be enabled if overnight reservations are allowed.
            Defaults to False.
        allow_shareable (bool, optional): Include the checkbox for the user to note that they're
            willing to share a resource. Should only be enabled for a resource that can
            be shared. Defaults to False.
        emoji (str, optional): emoji symbol to append to the form page title. Defaults to ''.
        description (str, optional): descriptive sub-heading for the resource page. Defaults to ''.
        image (ImageFile | None, optional): Bundle object for image to display on the
            webpage. Images can be helpful diagrams or just pretty pictures, whatever
            your heart desires. All image files must be in the root of the
            resource-configs dir (no nesting). You can have one image per page, for now.
            Defaults to None.
        custom_form_fields (list[CustomFormField], optional): custom html form input fields to add
            for the resource page. Defaults to empty list.
        maximum_days_ahead (int | None, optional): Positive integer, how many days ahead the user
            can reserve this resource. If None, reservations can be made for any time
            in the future. Overrides the value defined in app config file, if present.
            Defaults to 14.
        minutes_before_reminder (int, optional): Positive integer, how many minutes
            before the reservation to send an email reminder to the user, if they've
            selected to receive one. Overrides the value defined in app config file, if
            present. Defaults to 60.
        calendar_shown (bool, optional): If False, omit the embedded Google calendar
            from the form page. The calendar view will also be omitted if the resource
            has more than 4 calendars, to avoid visual clutter. Overrides the value
            defined in app config file, if present. Defaults to True.
        contact_email (str, optional): A contact email address for user issues, listed
            on this reservation page, if desired. Overrides the value defined in app
            config file, if present. Defaults to None.
    """

    MAX_CALENDARS_SHOWN: ClassVar = 4
    """If a resource page has more than this many individual resource calendars, the Google calendar
    view won't be shown on the form webpage. It'd be too hectic with the potential for
    lots of overlapping reservations."""

    DEFAULT_TO_APP_CONFIG_FIELDS: ClassVar = (
        "maximum_days_ahead",
        "minutes_before_reminder",
        "calendar_shown",
        "contact_email",
    )
    """These required fields are duplicated between both AppConfig and ResourceConfig
    models. Supply them either globally in `app-config.yaml`, or per-resource in the
    resource-config yaml file. If they're specifid in both, the resource-config value takes
    precedence.
    """

    file_prefix: str
    route_prefix: str
    name: str
    calendars: dict[str, CalendarInfo]
    day_start_time: AmPmTime = Field(default_factory=lambda: time(hour=0, minute=0))
    day_end_time: AmPmTime = Field(default_factory=lambda: time(hour=23, minute=59))
    minutes_increment: PositiveInt = 30
    maximum_minutes: PositiveInt = 120
    allow_end_next_day: bool = False
    allow_shareable: bool = False
    emoji: str = ""
    description: str = ""
    image: ImageFile | None = None
    # fields that can also be specified globally in app-config file, and which are merged
    custom_form_fields: list[CustomFormField] = Field(default_factory=list)
    # fields that can also be specified globally in app-config file, and which override
    # app-config when present in resource-config. The effective default values are
    # defined in AppConfig model.
    maximum_days_ahead: PositiveInt | None
    minutes_before_reminder: PositiveInt
    calendar_shown: bool
    contact_email: EmailStr | None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def end_after_start(self) -> Self:
        if self.day_start_time >= self.day_end_time:
            raise ValueError("day_start_time must be before day_end_time.")
        return self

    @model_validator(mode="after")
    def maximum_minutes_is_multiple(self) -> Self:
        if self.maximum_minutes % self.minutes_increment != 0:
            raise ValueError("maximum_minutes must be a multiple of minutes_increment.")
        return self

    @cached_property
    def _calendar_ids(self) -> dict[str, str]:
        """dict[cal_id, event_label], this ends up being useful."""
        return {cal.id: label for label, cal in self.calendars.items()}

    @cached_property
    def calendar_shown_final(self) -> bool:
        return len(self.calendars) <= self.MAX_CALENDARS_SHOWN and self.calendar_shown

    @classmethod
    def _model_validate_cleanly(cls, obj: dict, *, context=None, **kwargs):
        """model_validate overload that adds helpful error log for determining which
        resource config is bad in the case of many resources
        """
        try:
            return super().model_validate(obj, context=context, **kwargs)
        except ValidationError as e:
            logger.error(
                f"Error loading ResourceConfig for resource '{obj['route_prefix']}': {e}"
            )
            # Kill the process cleanly; uvicorn will just see a non-zero exit
            raise SystemExit(1) from e
