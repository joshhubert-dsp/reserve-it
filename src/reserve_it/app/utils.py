import asyncio
import re
from dataclasses import dataclass
from itertools import chain
from time import time
from typing import cast
from urllib.parse import quote_plus, urlencode
from zoneinfo import ZoneInfo

import yaml
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request, status
from fastapi.concurrency import asynccontextmanager
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from gcsa.google_calendar import GoogleCalendar
from google.oauth2.credentials import Credentials
from loguru import logger
from pydantic import DirectoryPath, FilePath, ValidationError
from sqlalchemy import Engine as SqlEngine
from sqlmodel import SQLModel, create_engine

from reserve_it.app.calendar_service import GoogleCalendarService
from reserve_it.app.database import ReservationDatabase, create_session_factory
from reserve_it.app.reminders import ReminderService
from reserve_it.models.app_config import AppConfig
from reserve_it.models.reservation_request import ReservationRequest
from reserve_it.models.resource_config import (
    ResourceConfig,
)

LEADING_INT_PATTERN = re.compile(r"^\d+")
LEADING_DASH_PATTERN = re.compile(r"^-")


def extract_leading_int(s: str) -> tuple[int, str]:
    match = re.match(LEADING_INT_PATTERN, s)
    if match is None:
        return 0, s
    int_part = match.group(0)
    the_rest = re.sub(LEADING_INT_PATTERN, "", s)
    return int(int_part), the_rest


@dataclass
class ResourceBundle:
    """convenience dataclass for stashing necessary objects for each resource route"""

    config: ResourceConfig
    request_class: type[ReservationRequest]
    database: ReservationDatabase
    # NOTE: locks are instantiated in app_lifespan when the event loop is available
    resource_lock: asyncio.Lock | None = None


@dataclass
class AppDependencies:
    resource_bundles: dict[str, ResourceBundle]
    calendar_service: GoogleCalendarService

    def __post_init__(self):
        self.num_resources = len(self.resource_bundles)


def load_resource_cfgs_from_yaml(
    config_dir: DirectoryPath, app_config: AppConfig
) -> dict[str, ResourceConfig]:
    configs: dict[str, ResourceConfig] = {}
    config_file_paths = list(chain(config_dir.glob("*.yaml"), config_dir.glob("*.yml")))

    # sort by file names to allow explicit ordering with "1-name1", "2-name2", etc
    config_file_paths.sort(key=lambda p: extract_leading_int(p.stem))

    for path in config_file_paths:
        # NOTE: these prefixes will be used for the route paths too
        prefix = re.sub(LEADING_INT_PATTERN, "", path.stem)
        prefix = re.sub(LEADING_DASH_PATTERN, "", prefix)

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        data["file_prefix"] = prefix if len(config_file_paths) > 1 else "index"
        data["route_prefix"] = f"/{prefix}" if len(config_file_paths) > 1 else ""
        # update with global custom form fields if passed
        data["custom_form_fields"] = data.get("custom_form_fields", []) + (
            app_config.custom_form_fields
        )

        for field in ResourceConfig.DEFAULT_TO_APP_CONFIG_FIELDS:
            if field not in data:
                data[field] = getattr(app_config, field)
        configs[prefix] = ResourceConfig._model_validate_cleanly(data, extra="ignore")

    if not configs:
        raise ValueError(
            "you didn't create any resource config yaml files, or provided the wrong "
            "path for resource_config_path"
        )
    # print(f"{pformat(configs)}")

    return configs


def init_gcal(
    timezone: ZoneInfo,
    gcal_secret_path: FilePath,
    gcal_token_path: FilePath | None = None,
) -> GoogleCalendar:
    if gcal_token_path and gcal_token_path.exists():
        # load already stored refresh token, bypass initial client secrets auth
        creds = Credentials.from_authorized_user_file(gcal_token_path)
        gcal = GoogleCalendar(credentials=creds, save_token=False)
    else:
        # initialize with client secrets auth, and store token
        gcal = GoogleCalendar(credentials_path=gcal_secret_path, save_token=False)
    if gcal_token_path:
        gcal_token_path.write_text(gcal.credentials.to_json())

    # stash the global timezone in the GoogleCalendar instance for convenience
    # (it's only needed for calendar event creation and queries)
    gcal.timezone = timezone
    return gcal


def create_db_engine(
    sqlite_db_path: DirectoryPath, file_prefix: str, db_echo: bool = False
) -> SqlEngine:
    sqlite_db_path.mkdir(parents=True, exist_ok=True)
    db_filepath = sqlite_db_path / f"{file_prefix}.sqlite3"
    sqlite_url = f"sqlite:///{db_filepath}"
    engine = create_engine(sqlite_url, echo=db_echo)
    SQLModel.metadata.create_all(engine)
    return engine


def init_dbs_and_bundles(
    resource_configs: dict[str, ResourceConfig],
    request_classes: dict[str, type[ReservationRequest]],
    sqlite_dir: DirectoryPath,
    db_echo: bool = False,
) -> dict[str, ResourceBundle]:
    bundles: dict[str, ResourceBundle] = {}

    for prefix, cfg in resource_configs.items():
        engine = create_db_engine(sqlite_dir, prefix, db_echo)
        session_factory = create_session_factory(engine)
        database = ReservationDatabase(session_factory, engine.dispose)
        bundles[prefix] = ResourceBundle(cfg, request_classes[prefix], database)
    return bundles


@asynccontextmanager
async def app_lifespan(app: FastAPI, sqlite_db_path: DirectoryPath):
    """App lifespan used setting up reminder scheduler and for shutting down dbs."""
    db_filepath = sqlite_db_path / "jobs.sqlite3"
    jobstores = {"default": SQLAlchemyJobStore(url=f"sqlite:///{db_filepath}")}
    scheduler = AsyncIOScheduler(
        jobstores=jobstores, timezone=app.state.config.timezone
    )
    scheduler.start()
    app.state.scheduler = scheduler
    app.state.reminder_service = ReminderService(scheduler, app.state.config.timezone)

    # instantiate the resource locks here now that event loop is running
    for bundle in app.state.resource_bundles.values():
        bundle.resource_lock = asyncio.Lock()

    try:
        yield

    finally:
        scheduler.shutdown(wait=False)

        for bundle in app.state.resource_bundles.values():
            bundle.database.dispose()


def build_calendar_embed_url(config: ResourceConfig, timezone: ZoneInfo) -> str | None:
    if not config.calendar_shown_final:
        return None

    base = "https://calendar.google.com/calendar/embed?"
    params = {
        "title": config.name,
        "ctz": timezone,
        "mode": "WEEK",
        "showCalendars": 1,
        "showTabs": 0,
        "showPrint": 0,
        "showTz": 0,
        "refresh": int(time()),  # cache-buster, forces refresh
    }
    # need to listify to handle duplicate queries for multiple calendars
    params = list(params.items())
    for cal in config.calendars.values():
        params.append(("src", cal.id))
        params.append(("color", cal.color))
    return base + urlencode(params, quote_via=quote_plus)


# --- APP SINGLETON/CONSTANT GETTERS W/ TYPE HINTING ---


def get_calendar_service(request: Request):
    from reserve_it.app.calendar_service import CalendarService

    return cast(CalendarService, request.app.state.calendar_service)


def get_app_cfg(request: Request) -> AppConfig:
    return cast(AppConfig, request.app.state.config)


def get_timezone(request: Request) -> ZoneInfo:
    return cast(ZoneInfo, request.app.state.config.timezone)


def get_app_email(request: Request) -> ZoneInfo:
    return cast(str, request.app.state.config.app_email)


def get_reminder_service(request: Request) -> ReminderService:
    return cast(ReminderService, request.app.state.reminder_service)


def get_all_resource_bundles(request: Request) -> dict[str, ResourceBundle]:
    return cast(dict[str, ResourceBundle], request.app.state.resource_bundles)


def get_form_templates(request: Request) -> Jinja2Templates:
    return cast(Jinja2Templates, request.app.state.form_templates)


def get_all_resource_cfgs(request: Request) -> dict[str, ResourceConfig]:
    return cast(
        dict[str, ResourceConfig],
        {
            prefix: rsc.config
            for prefix, rsc in request.app.state.resource_bundles.items()
        },
    )


# --- APP LOGGING EXCEPTION HANDLERS ---


async def log_request_validation_error(request: Request, exc: RequestValidationError):
    logger.exception(
        f"RequestValidationError during {request.method} {request.url.path}: {exc.errors()}"
    )
    # Delegate to FastAPI’s default handler for the exact same JSON shape
    return await request_validation_exception_handler(request, exc)


async def handle_validation_error(request: Request, exc: ValidationError):
    """just using this for now to report both request and response model validation
    failure. in prod, should probably remove and allow for default server error 500 for
    response error"""
    logger.exception(f"A validation error occurred: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": "\n".join([e["msg"] for e in exc.errors()])},
    )


async def log_unexpected_exception(request: Request, exc: Exception):
    logger.exception(
        f"An unexpected error occurred during {request.method} {request.url.path}: {exc}"
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
