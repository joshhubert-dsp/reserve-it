from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from apscheduler.jobstores.base import JobLookupError

from reserve_it.app.build_app import _normalize_request_classes
from reserve_it.app.calendar_service import GoogleCalendarService
from reserve_it.app.database import ReservationDatabase
from reserve_it.app.reminders import ReminderService
from reserve_it.models.reservation import Reservation
from reserve_it.models.reservation_request import ReservationRequest
from reserve_it.models.resource_config import ResourceConfig


@pytest.fixture
def reservation_request() -> ReservationRequest:
    target_date = datetime.today().date() + timedelta(days=1)
    return ReservationRequest.model_validate(
        {
            "email": "user@example.com",
            "date": target_date,
            "start_time": "10:00 AM",
            "end_time": "11:00 AM",
        }
    )


def _session_factory(session: MagicMock):
    @contextmanager
    def _factory():
        yield session

    return _factory


def test_normalize_request_classes_accepts_global_model():
    config = {
        "foo": MagicMock(spec=ResourceConfig),
        "bar": MagicMock(spec=ResourceConfig),
    }
    mapping = _normalize_request_classes(ReservationRequest, config)
    assert mapping == {"foo": ReservationRequest, "bar": ReservationRequest}


def test_google_calendar_service_creates_reservation(reservation_request):
    client = MagicMock()
    client.timezone = ZoneInfo("UTC")
    service = GoogleCalendarService(client)

    added_event = SimpleNamespace(
        event_id="evt-123",
        attendees=[SimpleNamespace(email=reservation_request.email)],
        start=reservation_request.start_dt,
        end=reservation_request.end_dt,
    )
    client.add_event.return_value = added_event

    reservation = service.create_reservation(
        "calendar-1", "Room A", reservation_request
    )

    client.add_event.assert_called_once()
    assert isinstance(reservation, Reservation)
    assert reservation.event_id == "evt-123"
    assert reservation.calendar_id == "calendar-1"


def test_reservation_db_upsert_updates_existing():
    session = MagicMock()
    existing = MagicMock(spec=Reservation)
    exec_result = MagicMock()
    exec_result.one_or_none.return_value = existing
    session.exec.return_value = exec_result
    repository = ReservationDatabase(_session_factory(session), lambda: None)

    new_reservation = Reservation(
        email="user@example.com",
        event_id="evt",
        calendar_id="cal",
        start_dt=datetime.now(),
        end_dt=datetime.now() + timedelta(hours=1),
        shareable=False,
    )

    repository.upsert(new_reservation)

    existing.sqlmodel_update.assert_called_once()
    session.add.assert_called_once_with(existing)
    session.commit.assert_called_once()


def test_reminder_service_schedule_and_cancel():
    scheduler = MagicMock()
    service = ReminderService(scheduler, ZoneInfo("UTC"))
    run_date = datetime.now() + timedelta(minutes=5)

    service.schedule(
        job_id="reminder-1",
        run_date=run_date,
        callback=lambda: None,
        kwargs={"foo": "bar"},
    )

    scheduler.add_job.assert_called_once()

    scheduler.reset_mock()
    scheduler.remove_job.side_effect = JobLookupError("missing")
    service.cancel("reminder-1")
    scheduler.remove_job.assert_called_once_with("reminder-1")
