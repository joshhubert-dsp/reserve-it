from pathlib import Path

from fastapi.templating import Jinja2Templates

PROJECT_ROOT = Path(__file__).parents[2]
SRC_ROOT = PROJECT_ROOT / "src" / "reserve_it"
TEMPLATES = Jinja2Templates(SRC_ROOT / "templates")


from reserve_it.app.build import build_app
from reserve_it.models.field_types import AmPmTime, HtmlFormInputType
from reserve_it.models.reservation_request import ReservationRequest
from reserve_it.models.resource_config import CustomFormField, ResourceConfig

__all__ = [
    "build_app",
    "AmPmTime",
    "HtmlFormInputType",
    "ReservationRequest",
    "ResourceConfig",
    "CustomFormField",
]
