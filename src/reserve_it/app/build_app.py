from dataclasses import dataclass
from functools import partial
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from pydantic import DirectoryPath, FilePath, ValidationError, validate_call

from reserve_it import TEMPLATES
from reserve_it.app.calendar_service import GoogleCalendarService
from reserve_it.app.route_helpers import (
    bind_post_endpoint,
    cancel_reservation,
    get_form,
    submit_reservation,
)
from reserve_it.app.utils import (
    ResourceBundle,
    app_lifespan,
    get_all_resource_cfgs,
    handle_validation_error,
    init_dbs_and_bundles,
    init_gcal,
    load_resource_cfgs_from_yaml,
    log_request_validation_error,
    log_unexpected_exception,
)
from reserve_it.models.app_config import AppConfig
from reserve_it.models.field_types import YamlPath
from reserve_it.models.reservation_request import ReservationRequest
from reserve_it.models.resource_config import ResourceConfig


@dataclass
class AppDependencies:
    resource_bundles: dict[str, ResourceBundle]
    calendar_service: GoogleCalendarService

    def __post_init__(self):
        self.num_resources = len(self.resource_bundles)


@validate_call
def build_app(
    app_config: AppConfig | YamlPath,
    resource_config_path: DirectoryPath,
    sqlite_dir: DirectoryPath,
    gcal_cred_path: FilePath,
    gcal_token_path: FilePath | None = None,
    image_dir: DirectoryPath | None = None,
    request_classes: (
        type[ReservationRequest] | dict[str, type[ReservationRequest]]
    ) = ReservationRequest,
) -> FastAPI:
    """Builds your resource reservation app using the app config and resource yaml
    files you defined.

    Args:
        app_config (AppConfig | YamlPath): Either an AppConfig object, or a path to a
            yaml file to instantiate one from.
        resource_config_path (DirectoryPath): Path to a folder full of resource config
            yaml files.
        sqlite_dir (DirectoryPath): Path to a folder where sqlite databases will be
            generated and stored. Each resource generates a database, and the reminder
            job scheduler generates an additional one that serves all resources.
        gcal_cred_path (FilePath): Path to the json file holding static OAuth client ID
            desktop app credentials you generated and downloaded from
            `https://console.cloud.google.com/apis/credentials`, `client_secret.json` or
            similarly named.
        gcal_token_path (FilePath | None, optional): If desired, path to a json file to
            save the refresh token and temporary auth token to on first authenticating
            your credentials, to reduce token churn. If passed, the token is automatically
            refreshed if expired. Defaults to None, in which case no tokens are saved.
        image_dir (DirectoryPath | None, optional): Path to a folder where images you
            want to display on reservation webpages are stored, to be mounted to the
            app. These can be helpful diagrams or just pretty pictures, whatever your
            heart desires. All image files must be in the root of this folder (no
            nesting). You can have one image per page, for now. Defaults to
            None.
        request_classes (type[ReservationRequest] | dict[str, type[ReservationRequest]], optional):
            Either a single global ReservationRequest model subclass to use for form input
            validation for all resources, one a dict of one subclass per resource, with
            keys matching the names of the resource config files (minus any integer
            prefixes for ordering). Defaults to ReservationRequest, the default base
            model class.

    Returns:
        FastAPI: The FastAPI instance for your app.
    """
    if isinstance(app_config, Path):
        app_config = AppConfig.from_yaml(app_config)

    dependencies = _initialize_dependencies(
        resource_config_path,
        request_classes,
        sqlite_dir,
        app_config,
        gcal_cred_path,
        gcal_token_path,
    )

    app = _create_app(app_config, sqlite_dir)
    _configure_app_state(app, app_config, dependencies, image_dir)

    app.add_exception_handler(RequestValidationError, log_request_validation_error)
    app.add_exception_handler(ValidationError, handle_validation_error)
    app.add_exception_handler(Exception, log_unexpected_exception)

    # add directory for js files
    # app.mount("/static", StaticFiles(directory=SOURCE_ROOT / "static"), name="static")
    # # add directory for optional webpage images
    # if image_dir:
    #     app.mount("/images", StaticFiles(directory=image_dir), name="images")

    _register_resource_routes(app, dependencies.resource_bundles, app_config)

    # if there's only one resource, then no need for a separate home page
    # if dependencies.num_resources > 1:
    #     _register_home_route(app)

    return app


def _initialize_dependencies(
    resource_config_path: DirectoryPath,
    request_classes: type[ReservationRequest] | dict[str, type[ReservationRequest]],
    sqlite_dir: DirectoryPath,
    app_config: AppConfig,
    gcal_cred_path: FilePath,
    gcal_token_path: FilePath | None,
) -> AppDependencies:
    resource_configs = load_resource_cfgs_from_yaml(resource_config_path, app_config)

    normalized_requests = _normalize_request_classes(request_classes, resource_configs)
    resource_bundles = init_dbs_and_bundles(
        resource_configs, normalized_requests, sqlite_dir, app_config.db_echo
    )
    gcal = init_gcal(app_config.timezone, gcal_cred_path, gcal_token_path)
    calendar_service = GoogleCalendarService(gcal)
    return AppDependencies(resource_bundles, calendar_service)


def _normalize_request_classes(
    request_classes: type[ReservationRequest] | dict[str, type[ReservationRequest]],
    resource_configs: dict[str, ResourceConfig],
) -> dict[str, type[ReservationRequest]]:
    if isinstance(request_classes, dict):
        if len(request_classes) != len(resource_configs):
            raise ValueError(
                "request_classes dict must be the same length as the number of resource configs."
            )
        missing = set(request_classes) - set(resource_configs)
        if missing:
            raise ValueError(
                "request_classes contains keys not present in resource_configs: "
                + ", ".join(sorted(missing))
            )
        return request_classes

    return {key: request_classes for key in resource_configs}


def _create_app(app_config: AppConfig, sqlite_db_path: DirectoryPath) -> FastAPI:
    return FastAPI(
        title=app_config.title,
        description=app_config.description,
        version=app_config.version,
        openapi_url=app_config.openapi_url,
        lifespan=partial(app_lifespan, sqlite_db_path=sqlite_db_path),
    )


def _configure_app_state(
    app: FastAPI,
    app_config: AppConfig,
    dependencies: AppDependencies,
    image_dir: DirectoryPath,
) -> None:
    app.state.config = app_config
    app.state.resource_bundles = dependencies.resource_bundles
    app.state.calendar_service = dependencies.calendar_service
    app.state.image_dir = image_dir


def _register_resource_routes(
    app: FastAPI, resource_bundles: dict[str, ResourceBundle], app_config: AppConfig
) -> None:
    multi_resource = len(resource_bundles) > 1
    for bundle in resource_bundles.values():
        router: FastAPI | APIRouter
        if multi_resource:
            router = APIRouter(prefix=bundle.config.route_prefix)
        else:
            router = app
        build_route(router, bundle, app_config)
        if multi_resource:
            app.include_router(router)


def _register_home_route(app: FastAPI) -> None:
    @app.get("/", response_class=HTMLResponse)
    async def get_home_page(
        request: Request,
        all_configs: dict[str, ResourceConfig] = Depends(get_all_resource_cfgs),
    ):
        return TEMPLATES.TemplateResponse(
            "home.html",
            {
                "request": request,
                "site_title": app.state.config.title,
                "description": app.state.config.description,
                "resources": all_configs,
            },
        )


def build_route(
    router: FastAPI | APIRouter, bundle: ResourceBundle, app_cfg: AppConfig
):
    get_form_bound = partial(get_form, config=bundle.config)
    router.add_api_route(
        "/",
        endpoint=get_form_bound,
        name=f"get_form_{bundle.config.file_prefix}",
        methods=["GET"],
        response_class=HTMLResponse,
    )

    submit_bound = bind_post_endpoint(submit_reservation, bundle, app_cfg)
    router.add_api_route(
        "/reserve",
        endpoint=submit_bound,
        name=f"submit_{bundle.config.file_prefix}",
        methods=["POST"],
        response_class=HTMLResponse,
    )

    cancel_bound = bind_post_endpoint(cancel_reservation, bundle, app_cfg)
    router.add_api_route(
        "/cancel",
        endpoint=cancel_bound,
        name=f"cancel_{bundle.config.file_prefix}",
        methods=["POST"],
        response_class=HTMLResponse,
    )
