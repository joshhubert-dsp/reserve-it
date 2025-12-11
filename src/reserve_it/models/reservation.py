from datetime import datetime
from typing import Self

from gcsa.event import Event as GcalEvent
from pydantic import EmailStr
from sqlmodel import Field, SQLModel


# TODO make this extensible?
class Reservation(SQLModel, table=True):
    """The Reservation SQL model class. Instances are produced and stored on successful
    reservation event creation. So far only used for:
    - ensuring one reservation per email
    - tracking whether a user designated their reservation as shareable\n
    but could be opened up to extension in the future.
    """

    id: int | None = Field(default=None, primary_key=True)
    email: EmailStr = Field(index=True)
    event_id: str = Field(index=True)
    calendar_id: str
    start_dt: datetime
    end_dt: datetime
    shareable: bool

    @classmethod
    def from_gcal_event(
        cls, event: GcalEvent, calendar_id: str, shareable: bool
    ) -> Self:
        """reservation database object is created after successful return from gcal api
        for adding event to calendar, that way we can stash the actual event_id"""
        return cls(
            email=event.attendees[0].email,
            event_id=event.event_id,
            calendar_id=calendar_id,
            start_dt=event.start,
            end_dt=event.end,
            shareable=shareable,
        )
