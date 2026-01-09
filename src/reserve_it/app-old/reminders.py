from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler


class ReminderService:
    """Wrapper around the APScheduler for reminder jobs."""

    def __init__(self, scheduler: AsyncIOScheduler, timezone: ZoneInfo) -> None:
        self._scheduler = scheduler
        self._timezone = timezone

    def schedule(
        self,
        job_id: str,
        run_date: datetime,
        callback: Callable[..., Any],
        *,
        kwargs: dict[str, Any],
    ) -> None:
        self._scheduler.add_job(
            callback,
            "date",
            id=job_id,
            run_date=run_date,
            timezone=self._timezone,
            kwargs=kwargs,
            replace_existing=True,
            misfire_grace_time=None,
        )

    def cancel(self, job_id: str) -> None:
        try:
            self._scheduler.remove_job(job_id)
        except JobLookupError:
            pass
