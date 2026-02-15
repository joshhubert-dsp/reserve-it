from fastapi.templating import Jinja2Templates
from jinja2 import Environment, PackageLoader, select_autoescape

TEMPLATES = Jinja2Templates(
    env=Environment(
        loader=PackageLoader("reserve_it", "app/templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )
)

from reserve_it.app.build_app import build_app
from reserve_it.models.app_config import AppConfig
from reserve_it.models.field_types import (
    CalendarInfo,
    CustomFormField,
    HtmlFormInputType,
    ImageFile,
)
from reserve_it.models.reservation_request import ReservationRequest
from reserve_it.models.resource_config import ResourceConfig

__all__ = [
    "AppConfig",
    "ResourceConfig",
    "CalendarInfo",
    "CustomFormField",
    "HtmlFormInputType",
    "ImageFile",
    "ReservationRequest",
    "build_app",
]
