import datetime
from functools import cached_property
from typing import Self

from pydantic import (
    BaseModel,
    EmailStr,
    ValidationInfo,
    computed_field,
    model_validator,
)

from reserve_it.models.field_types import AmPmTime


class ReservationRequest(BaseModel):
    """
    Base model for validating reservation web form input.
    Works as is, or subclass to add extra form fields for additional user validation.

    Args:
        email (str): The user's email, required for inviting them to the reservation
            event and sending a reminder email.
        date (date): The date of the reservation.
        start_time (AmPmTime): The start time, can be input as a string "HH:MM
            AM/PM", converted to a time object.
        end_time (AmPmTime): The end time, can be input as a string "HH:MM AM/PM",
            converted to a time object.
        end_next_day (bool): Whether to interpret end_time as on the day after date, for
            overnight reservations. Defaults to False.
        shareable (bool): Whether the user is willing to share a shareable resource with
            others who are willing to share during their reservation slot. Defaults to False.
        reminder (bool): Whether the user wants an email reminder before the reservation
            begins. Defaults to True.
    """

    email: EmailStr
    date: datetime.date
    start_time: AmPmTime
    end_time: AmPmTime
    end_next_day: bool = False
    shareable: bool = False
    reminder: bool = True

    @model_validator(mode="after")
    def end_after_start(self) -> Self:
        if not self.end_next_day and self.start_time >= self.end_time:
            raise ValueError("Start Time must be before End Time.")
        return self

    @model_validator(mode="after")
    def in_the_future(self) -> Self:
        if self.start_dt <= datetime.datetime.now():
            raise ValueError("Reservation time must be in the future.")
        return self

    @model_validator(mode="after")
    def within_maximum_days_ahead(self, info: ValidationInfo) -> Self:
        max_days_ahead = (info.context or {}).get("maximum_days_ahead")

        if max_days_ahead is not None:
            max_dt = datetime.datetime.now() + datetime.timedelta(days=max_days_ahead)
            if self.start_dt > max_dt:
                raise ValueError(
                    f"A reservation for this resource can't be made further out than "
                    f"{max_dt.strftime('%m/%d/%Y')} ({max_days_ahead} days from now)."
                )

        return self

    @model_validator(mode="after")
    def within_maximum_minutes(self, info: ValidationInfo) -> Self:
        max_minutes = (info.context or {}).get("maximum_minutes")

        if max_minutes is not None:
            minutes = (self.end_dt - self.start_dt).total_seconds() // 60
            if minutes > max_minutes:
                raise ValueError(
                    "A reservation for this resource can't be longer than "
                    + (
                        f"{max_minutes} minutes."
                        if max_minutes < 120
                        else f"{max_minutes / 60:.1f} hours."
                    )
                )

        return self

    @computed_field
    @cached_property
    def start_dt(self) -> datetime.datetime:
        return datetime.datetime.combine(self.date, self.start_time)

    @computed_field
    @cached_property
    def end_dt(self) -> datetime.datetime:
        return datetime.datetime.combine(
            self.date + datetime.timedelta(days=int(self.end_next_day)), self.end_time
        )
