from zoneinfo import ZoneInfo

from gcsa._services.events_service import SendUpdatesMode
from pydantic import FilePath
from sqlmodel import Session, SQLModel, create_engine, delete, select

from reserve_it.app.utils import init_gcal
from reserve_it.models.reservation import Reservation


def clear_resource_calendar(
    db_filepath: FilePath,
    timezone: ZoneInfo,
    gcal_cred_path: FilePath,
    gcal_token_path: FilePath | None = None,
):
    sqlite_url = f"sqlite:///{db_filepath}"
    engine = create_engine(sqlite_url, echo=True)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        statement = select(Reservation)
        reservations = session.exec(statement).all()

    gcal = init_gcal(timezone, gcal_cred_path, gcal_token_path)

    for res in reservations:
        gcal.delete_event(
            event=res.event_id,
            calendar_id=res.calendar_id,
            send_updates=SendUpdatesMode.ALL,
        )

    with Session(engine) as session:
        statement = delete(Reservation)
        reservations = session.exec(statement)
