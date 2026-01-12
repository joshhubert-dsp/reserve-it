from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol
from zoneinfo import ZoneInfo

from devtools import pformat
from gcsa._services.events_service import SendUpdatesMode
from gcsa.event import Event as GcalEvent
from gcsa.event import Transparency, Visibility
from gcsa.google_calendar import GoogleCalendar
from loguru import logger
from rich import print

from reserve_it.models.reservation import Reservation
from reserve_it.models.reservation_request import ReservationRequest
from reserve_it.models.resource_config import ResourceConfig


@dataclass
class EventCalendarId:
    event: GcalEvent
    calendar_id: str


class CalendarService(Protocol):
    """Protocol defining the calendar operations the app relies on."""

    def find_all_existing_events(
        self, request: ReservationRequest, config: ResourceConfig
    ) -> list[EventCalendarId]: ...

    def find_user_existing_event(
        self, request: ReservationRequest, config: ResourceConfig
    ) -> EventCalendarId | None: ...

    def create_reservation(
        self, calendar_id: str, event_label: str, request: ReservationRequest
    ) -> Reservation: ...

    def delete_event(self, event: EventCalendarId) -> None: ...

    async def send_reminder(
        self,
        calendar_id: str,
        event_id: str,
        event_label: str,
        request: ReservationRequest,
    ) -> None: ...


@dataclass
class GoogleCalendarService(CalendarService):
    """Calendar service backed by Google Calendar via GCSA."""

    client: GoogleCalendar

    def get_free_calendars(
        self, reservation: ReservationRequest, config: ResourceConfig
    ) -> dict[str, str]:
        """Return calendars without conflicts for the requested time slot."""

        free_busy = self.client.get_free_busy(
            resource_ids=list(config._calendar_ids),
            time_min=reservation.start_dt,
            time_max=reservation.end_dt,
            timezone=self.client.timezone.key,
        )
        print(pformat(free_busy.calendars))
        free_candidates = deepcopy(config._calendar_ids)

        for cal_id in free_busy.calendars.keys():
            free_candidates.pop(cal_id, None)
        return free_candidates

    def find_all_existing_events(
        self, request: ReservationRequest, config: ResourceConfig
    ) -> list[EventCalendarId]:
        """
        Search for existing reservation events during the requested timespan on any
        resource calendar, and return them.

        Args:
            request (ReservationRequest): validated reservation request model object
                for current resource.
            config (ResourceConfig): validated resource config model object for current
                resource.

        Returns:
            list[EventCalendarId]: list of objects holding event found and its
                calendar_id, or empty list if no corresponding events found.
        """
        event_n_cals: list[EventCalendarId] = []

        for cal_id in config._calendar_ids:
            found_events = list(
                self.client.get_events(
                    time_min=request.start_dt,
                    time_max=request.end_dt,
                    timezone=self.client.timezone.key,
                    query=None,
                    calendar_id=cal_id,
                )
            )
            for event in found_events:
                event_n_cals.append(EventCalendarId(event, cal_id))
        return event_n_cals

    def find_user_existing_event(
        self, request: ReservationRequest, config: ResourceConfig
    ) -> EventCalendarId | None:
        """
        Search for a user's existing reservation event during the requested timespan on any
        resource calendar, and return it.

        Args:
            request (ReservationRequest): validated reservation request model object
                for current resource.
            config (ResourceConfig): validated resource config model object for current
                resource.
        Returns:
            EventCalendarId | None: object holding event found and its calendar_id,
                or None if no corresponding event found.
        """
        for cal_id in config._calendar_ids:
            found_events = self.client.get_events(
                time_min=request.start_dt,
                time_max=request.end_dt,
                timezone=self.client.timezone.key,
                query=request.email,
                calendar_id=cal_id,
            )
            try:
                return EventCalendarId(next(found_events), cal_id)
            except StopIteration:
                continue
        return None

    def create_reservation(
        self, calendar_id: str, event_label: str, request: ReservationRequest
    ) -> Reservation:
        event = self.client.add_event(
            _build_gcal_event(event_label, request, self.client.timezone),
            send_updates=SendUpdatesMode.ALL,
            calendar_id=calendar_id,
        )
        return Reservation.from_gcal_event(event, calendar_id, request.shareable)

    def delete_event(self, event: EventCalendarId) -> None:
        self.client.delete_event(
            event=event.event,
            calendar_id=event.calendar_id,
            send_updates=SendUpdatesMode.ALL,
        )

    async def send_reminder(
        self,
        calendar_id: str,
        event_id: str,
        event_label: str,
        request: ReservationRequest,
    ) -> None:
        """Trigger reminder email by updating the event summary."""

        logger.info(f"sending reminder for {event_label}")
        self.client.update_event(
            _build_gcal_event(
                event_label=event_label,
                request=request,
                timezone=self.client.timezone,
                event_id=event_id,
                reminder=True,
            ),
            send_updates=SendUpdatesMode.ALL,
            calendar_id=calendar_id,
        )


def _build_gcal_event(
    event_label: str,
    request: ReservationRequest,
    timezone: ZoneInfo,
    event_id: str | None = None,
    reminder: bool = False,
):
    return GcalEvent(
        event_id=event_id,
        summary=("Reminder: " if reminder else "") + f"{event_label} Reservation",
        description=f"This invitation confirms your reservation for {event_label}.",
        start=request.start_dt,
        end=request.end_dt,
        timezone=timezone.key,
        visibility=Visibility.PRIVATE,
        transparency=Transparency.OPAQUE,
        attendees=request.email,
    )
