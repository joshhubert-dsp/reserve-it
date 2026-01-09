from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime

from sqlalchemy import Engine as SqlEngine
from sqlmodel import Session, delete, select

from reserve_it.models.reservation import Reservation

SessionFactory = Callable[[], AbstractContextManager[Session]]


def create_session_factory(engine: SqlEngine) -> SessionFactory:
    """Create a session factory bound to the provided engine."""

    @contextmanager
    def session_scope():
        with Session(engine) as session:  # type: ignore[arg-type]
            yield session

    return session_scope


class ReservationDatabase:
    """Data access wrapper around the Reservation SQLModel."""

    def __init__(
        self,
        session_factory: SessionFactory,
        dispose_callback: Callable[[], None],
    ) -> None:
        self._session_factory = session_factory
        self._dispose_callback = dispose_callback

    def has_pending_reservation(self, email: str) -> bool:
        with self._session_factory() as session:
            statement = select(Reservation).where(
                Reservation.email == email,
                Reservation.end_dt > datetime.now(),
            )
            return session.exec(statement).one_or_none() is not None

    def is_non_shareable(self, event_id: str, calendar_id: str) -> bool:
        with self._session_factory() as session:
            statement = select(Reservation).where(
                Reservation.event_id == event_id,
                Reservation.calendar_id == calendar_id,
                Reservation.shareable == False,  # noqa: E712
            )
            return session.exec(statement).one_or_none() is not None

    def upsert(self, reservation: Reservation) -> Reservation:
        with self._session_factory() as session:
            statement = select(Reservation).where(
                Reservation.email == reservation.email
            )
            existing = session.exec(statement).one_or_none()
            if existing:
                updated = reservation.model_dump(exclude={"id", "email"})
                existing.sqlmodel_update(updated)
                reservation = existing

            session.add(reservation)
            session.commit()
            session.refresh(reservation)
            return reservation

    def delete(self, event_id: str, calendar_id: str) -> None:
        with self._session_factory() as session:
            statement = delete(Reservation).where(
                Reservation.event_id == event_id,
                Reservation.calendar_id == calendar_id,
            )
            session.exec(statement)
            session.commit()

    def dispose(self) -> None:
        self._dispose_callback()
