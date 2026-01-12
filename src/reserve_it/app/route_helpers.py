import asyncio
from collections import Counter
from collections.abc import Coroutine
from copy import deepcopy
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from devtools import pformat
from fastapi import Request
from loguru import logger
from pydantic import ValidationError
from starlette.templating import _TemplateResponse

from reserve_it import TEMPLATES
from reserve_it.app.calendar_service import CalendarService
from reserve_it.app.database import ReservationDatabase
from reserve_it.app.reminders import ReminderService
from reserve_it.app.utils import (
    ResourceBundle,
    build_calendar_embed_url,
    get_calendar_service,
    get_form_templates,
    get_reminder_service,
    get_timezone,
)
from reserve_it.models.app_config import AppConfig
from reserve_it.models.field_types import AM_PM_TIME_FORMAT
from reserve_it.models.reservation_request import ReservationRequest
from reserve_it.models.resource_config import ResourceConfig

# --- RESOURCE ENDPOINT FUNCTIONS ---


async def get_form(request: Request, config: ResourceConfig):
    return get_form_templates(request).TemplateResponse(
        f"{config.file_prefix}/index.html",
        {
            "request": request,
            "today": date.today().isoformat(),
            "calendar_embed_url": build_calendar_embed_url(
                config, get_timezone(request)
            ),
        },
    )


def bind_post_endpoint(
    endpoint: Coroutine, bundle: ResourceBundle, app_cfg: AppConfig
) -> Coroutine:
    """have to hide bound args from fastapi bc it's too clever"""

    async def bound_endpoint(request: Request):
        if bundle.resource_lock is None:
            raise RuntimeError("Resource lock not initialized for bundle")
        calendar_service = get_calendar_service(request)
        reminder_service = get_reminder_service(request)
        return await endpoint(
            request=request,
            config=bundle.config,
            request_class=bundle.request_class,
            database=bundle.database,
            resource_lock=bundle.resource_lock,
            calendar_service=calendar_service,
            reminder_service=reminder_service,
            app_cfg=app_cfg,
        )

    return bound_endpoint


def validate_request(
    form, request_class: type[ReservationRequest], config: ResourceConfig
) -> ReservationRequest:
    form_dict = dict(form)
    logger.debug(pformat(form_dict))
    return request_class.model_validate(
        form_dict,
        context={
            "maximum_days_ahead": config.maximum_days_ahead,
            "maximum_minutes": config.maximum_minutes,
        },
    )


async def submit_reservation(
    request: Request,
    config: ResourceConfig,
    request_class: type[ReservationRequest],
    database: ReservationDatabase,
    resource_lock: asyncio.Lock,
    calendar_service: CalendarService,
    reminder_service: ReminderService,
    app_cfg: AppConfig,
) -> _TemplateResponse:
    try:
        reserv_request = validate_request(await request.form(), request_class, config)
    except ValidationError as e:
        return invalid_input_response(request, e)

    # TODO email verification if first time this email is seen

    if database.has_pending_reservation(reserv_request.email):
        return denial_response(
            request,
            "This email already has an upcoming reservation. Check for a prior email "
            f"from {app_cfg.app_email} with the details. "
            "A new one can be made once the current one has passed or been cancelled.",
        )

    free_candidates = deepcopy(config._calendar_ids)

    async with resource_lock:
        # get existing gcal events, check for sharing
        existing_events = calendar_service.find_all_existing_events(
            reserv_request, config
        )

        # each of these branches knock ineligible calendars off free_candidates
        if existing_events:
            if not reserv_request.shareable:
                # user not sharing, any reserved calendars are a no-go
                for event in existing_events:
                    free_candidates.pop(event.calendar_id, None)

            else:  # user is sharing, check whether existing events are sharing as well
                for event in existing_events:
                    if database.is_non_shareable(event.event.id, event.calendar_id):
                        free_candidates.pop(event.calendar_id, None)

                # if there's more than one shareable resource (calendar) still available,
                #  pick the one with fewer concurrent reservations
                if len(free_candidates) > 1:
                    sharing_cals = [
                        e.calendar_id
                        for e in existing_events
                        if e.calendar_id in free_candidates
                    ]
                    cal_counter = Counter(sharing_cals)
                    n_most_wanted = cal_counter.most_common(len(free_candidates) - 1)
                    n_most_wanted = [n[0] for n in n_most_wanted]
                    for cal in n_most_wanted:
                        free_candidates.pop(cal, None)

        if not free_candidates:
            return denial_response(
                request, "All resources are busy during the requested timespan."
            )

        # create the reservation
        cal_id, event_label = free_candidates.popitem()
        reservation = calendar_service.create_reservation(
            calendar_id=cal_id,
            event_label=event_label,
            request=reserv_request,
        )

        event_id = reservation.event_id
        database.upsert(reservation)

        # --- SET REMINDER ---
        reminder_time = reserv_request.start_dt - timedelta(
            minutes=config.minutes_before_reminder
        )
        reminder = reserv_request.reminder and (reminder_time > datetime.now())
        if reminder:
            reminder_service.schedule(
                job_id=_reminder_job_id(event_id, cal_id),
                run_date=reminder_time,
                callback=calendar_service.send_reminder,
                kwargs={
                    "calendar_id": cal_id,
                    "event_id": event_id,
                    "event_label": event_label,
                    "request": reserv_request,
                },
            )

    success_msg = (
        f"{event_label} successfully reserved: {reserv_request.date.strftime('%m/%d/%Y')}, "
        f"{reserv_request.start_time.strftime(AM_PM_TIME_FORMAT)} → "
        f"{reserv_request.end_time.strftime(AM_PM_TIME_FORMAT)}."
    )
    if reminder:
        success_msg += f" You'll receive a reminder email {config.minutes_before_reminder} minutes before."
    return success_response(request, success_msg, config, app_cfg.timezone)


async def cancel_reservation(
    request: Request,
    config: ResourceConfig,
    request_class: type[ReservationRequest],
    database: ReservationDatabase,
    resource_lock: asyncio.Lock,
    calendar_service: CalendarService,
    reminder_service: ReminderService,
    app_cfg: AppConfig,
) -> _TemplateResponse:
    try:
        reserv_request = validate_request(await request.form(), request_class, config)
    except ValidationError as e:
        return invalid_input_response(request, e)

    # NOTE: with 1 reservation per email constraint, could just go directly to the
    # database and not need to look for an event during the time, but this is more
    # generalizable if I want to add more reservations
    async with resource_lock:
        event_n_cal = calendar_service.find_user_existing_event(reserv_request, config)
        if not event_n_cal:
            return denial_response(
                request,
                "No reservations were found to cancel with the requested parameters.",
            )

        # cancel the event
        calendar_service.delete_event(event_n_cal)
        database.delete(event_n_cal.event.id, event_n_cal.calendar_id)

    reminder_service.cancel(
        _reminder_job_id(event_n_cal.event.id, event_n_cal.calendar_id)
    )

    evt = event_n_cal.event
    success_msg = (
        f"{evt.summary} successfully cancelled: {evt.start.strftime('%m/%d/%Y')}, "
        f"{evt.start.strftime(AM_PM_TIME_FORMAT)} → "
        f"{evt.end.strftime(AM_PM_TIME_FORMAT)}."
    )
    return success_response(request, success_msg, config, app_cfg.timezone)


# --- RESPONSE TEMPLATES ---


def success_response(
    request: Request, success_msg: str, config: ResourceConfig, timezone: ZoneInfo
) -> _TemplateResponse:
    """send response to render success message"""

    return TEMPLATES.TemplateResponse(
        "response.html",
        {
            "request": request,
            "error": False,
            "message": success_msg,
            "calendar_embed_url": build_calendar_embed_url(config, timezone),
        },
    )


def invalid_input_response(request: Request, exc: ValidationError) -> _TemplateResponse:
    """
    prepare a template with more palatable validation error messages, to display to user
    at top of web form
    """
    errors = exc.errors()
    error_msgs = []
    for e in errors:
        if e["loc"]:
            error_msgs.append(f"{e['loc'][0]}: " + e["msg"].split(",")[0])
        else:
            error_msgs.append(e["msg"])
        if error_msgs[-1][-1] != ".":
            error_msgs[-1] = error_msgs[-1] + "."

    return TEMPLATES.TemplateResponse(
        "response.html",
        {
            "request": request,
            "error": True,
            "message": " ".join(error_msgs).replace("Value error, ", ""),
        },
        status_code=200,
    )


def denial_response(request: Request, message: str) -> _TemplateResponse:
    """
    Jinja template response for denial of the user's request, with explanatory message.
    """
    return TEMPLATES.TemplateResponse(
        "response.html",
        {"request": request, "error": True, "message": message},
        status_code=200,
    )


def _reminder_job_id(event_id: str, calendar_id: str) -> str:
    return f"reminder-{event_id}-{calendar_id}"
