from functools import partial
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import DirectoryPath, FilePath, ValidationError, validate_call

from reserve_it.app.calendar_service import GoogleCalendarService
from reserve_it.app.route_helpers import (
    bind_post_endpoint,
    cancel_reservation,
    get_form,
    submit_reservation,
)
from reserve_it.app.utils import (
    AppDependencies,
    ResourceBundle,
    app_lifespan,
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

DEFAULT_APP_CONFIG_FILE = "app-config.yaml"
DEFAULT_RESOURCE_CONFIG_DIR = "resource-configs"
DEFAULT_SQLITE_DIR = "sqlite-dbs"
DEFAULT_GCAL_DIR = Path(".gcal-credentials")
DEFAULT_GCAL_SECRET_FILE = DEFAULT_GCAL_DIR / "client-secret.json"
DEFAULT_GCAL_TOKEN_FILE = DEFAULT_GCAL_DIR / "auth-token.json"
DEFAULT_SITE_DIR = "site"


@validate_call
def build_app(
    app_config: AppConfig | YamlPath | None = None,
    resource_config_path: DirectoryPath | None = None,
    sqlite_dir: DirectoryPath | None = None,
    gcal_secret_path: FilePath | None = None,
    gcal_token_path: FilePath | None = None,
    site_dir: DirectoryPath | None = None,
    request_classes: (
        type[ReservationRequest] | dict[str, type[ReservationRequest]]
    ) = ReservationRequest,
) -> FastAPI:
    """Builds your resource reservation app using the app config and resource yaml
    files you defined.

    Args:
        app_config (AppConfig | YamlPath): Either an AppConfig object, or a path to a
            yaml file to instantiate one from. Defaults to `[CWD]/app-config.yaml`.
        resource_config_path (DirectoryPath): Path to a folder full of resource config
            yaml files. Defaults to `[CWD]/resource-configs/`.
        sqlite_dir (DirectoryPath): Path to a folder where sqlite databases will be
            generated and stored. Each resource generates a database, and the reminder
            job scheduler generates an additional one that serves all resources.
            Defaults to `[CWD]/sqlite-dbs/`.
        gcal_secret_path (FilePath): Path to the json file holding static OAuth client ID
            desktop app credentials you generated and downloaded from
            <https://console.cloud.google.com/apis/credentials>. Defaults to
            `[CWD]/.gcal-credentials/client-secret.json`.
        gcal_token_path (FilePath | None, optional): If desired, path to a json file to
            save the refresh token and temporary auth token to on first authenticating
            your credentials, to reduce token churn. If passed, the token is automatically
            refreshed if expired. Defaults to `[CWD]/.gcal-credentials/auth-token.json`.
        site_dir (DirectoryPath): Path of your desired mkdocs static site build directory.
            Defaults to `[CWD]/site/`.
        request_classes (type[ReservationRequest] | dict[str, type[ReservationRequest]], optional):
            Either a single global ReservationRequest model subclass to use for form input
            validation for all resources, one a dict of one subclass per resource, with
            keys matching the names of the resource config files (minus any integer
            prefixes for ordering). Defaults to `ReservationRequest`, the default base
            model class.

    Returns:
        FastAPI: The FastAPI instance for your app.
    """
    # is this TOO EASY?
    if not app_config:
        app_config = Path.cwd() / DEFAULT_APP_CONFIG_FILE
    if not resource_config_path:
        resource_config_path = Path.cwd() / DEFAULT_RESOURCE_CONFIG_DIR
    if not sqlite_dir:
        sqlite_dir = Path.cwd() / DEFAULT_SQLITE_DIR
    if not gcal_secret_path:
        gcal_secret_path = Path.cwd() / DEFAULT_GCAL_SECRET_FILE
    if not gcal_token_path:
        gcal_token_path = Path.cwd() / DEFAULT_GCAL_TOKEN_FILE
    if not site_dir:
        site_dir = Path.cwd() / DEFAULT_SITE_DIR

    if isinstance(app_config, Path):
        app_config = AppConfig.from_yaml(app_config)

    dependencies = _initialize_dependencies(
        resource_config_path,
        request_classes,
        sqlite_dir,
        app_config,
        gcal_secret_path,
        gcal_token_path,
    )

    app = _create_app(app_config, sqlite_dir)
    _configure_app_state(app, app_config, dependencies, site_dir)

    app.add_exception_handler(RequestValidationError, log_request_validation_error)
    app.add_exception_handler(ValidationError, handle_validation_error)
    app.add_exception_handler(Exception, log_unexpected_exception)

    _register_resource_routes(app, dependencies.resource_bundles, app_config)
    # add directory for static built files (including from any markdown files the user added)
    app.mount("/", StaticFiles(directory=site_dir, html=True), name="static")

    return app


def _initialize_dependencies(
    resource_config_path: DirectoryPath,
    request_classes: type[ReservationRequest] | dict[str, type[ReservationRequest]],
    sqlite_dir: DirectoryPath,
    app_config: AppConfig,
    gcal_secret_path: FilePath,
    gcal_token_path: FilePath | None,
) -> AppDependencies:
    resource_configs = load_resource_cfgs_from_yaml(resource_config_path, app_config)

    normalized_requests = _normalize_request_classes(request_classes, resource_configs)
    resource_bundles = init_dbs_and_bundles(
        resource_configs, normalized_requests, sqlite_dir, app_config.db_echo
    )
    gcal = init_gcal(app_config.timezone, gcal_secret_path, gcal_token_path)
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
    site_dir: DirectoryPath,
) -> None:
    app.state.config = app_config
    app.state.resource_bundles = dependencies.resource_bundles
    app.state.calendar_service = dependencies.calendar_service
    app.state.form_templates = Jinja2Templates(site_dir / "form-templates")


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
