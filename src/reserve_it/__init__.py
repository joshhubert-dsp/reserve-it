from pathlib import Path

from fastapi.templating import Jinja2Templates

PROJECT_ROOT = Path(__file__).parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src" / "reserve_it"
MKDOCS_ROOT = SOURCE_ROOT / "mkdocs_abuse"
EXAMPLE_DIR = SOURCE_ROOT / "example"
TEMPLATES = Jinja2Templates(SOURCE_ROOT / "app" / "templates")

# mkdocs assets directories:
ASSETS_SRC = MKDOCS_ROOT / "assets"
# ship JS/CSS from package into site/ and auto-include them.
ASSETS_DEST = Path("assets/reserve-it")
IMAGES_DEST = ASSETS_DEST / "images"

from reserve_it.app.build_app import build_app
from reserve_it.models.app_config import AppConfig
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
    "AppConfig",
]
