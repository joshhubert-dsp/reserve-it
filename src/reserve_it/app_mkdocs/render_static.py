from functools import partial

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import DirectoryPath

from reserve_it import SOURCE_ROOT, TEMPLATES
from reserve_it.app.route_helpers import (
    bind_post_endpoint,
    cancel_reservation,
    get_form,
    submit_reservation,
)
from reserve_it.app.utils import (
    ResourceBundle,
    get_all_resource_cfgs,
)
from reserve_it.models.app_config import AppConfig
from reserve_it.models.resource_config import ResourceConfig
import jinja2


def render_static(
    app_config: AppConfig,
    resource_configs: dict[str, ResourceConfig],
    image_dir: DirectoryPath | None = None,
    jinj_tmp: jinja2.Template 
) -> FastAPI:
    """
    Builds the static markdown content for resource reservation form webpages using the app
    config and resource configs you defined.

    # TODO update
    Args:
        app_config (AppConfig | YamlPath): Either an AppConfig object, or a path to a
            yaml file to instantiate one from.
        resource_config_path (DirectoryPath | YamlPath): Path to a single resource
            config yaml file, or a folder full of them.
        image_dir (DirectoryPath | None, optional): Path to a folder where images you
            want to display on reservation webpages are stored, to be mounted to the
            app. These can be helpful diagrams or just pretty pictures, whatever your
            heart desires. All image files must be in the root of this folder (no
            nesting). You can have one image per page, for now. Defaults to
            None.

    Returns:
        FastAPI: The FastAPI instance for your app.
    """
    tpl_name = TEMPLATES["resource_page"]
    tpl = jinj_env.get_template(tpl_name)

    # Everything you pass here becomes available in the .md.j2 template.
    return tpl.render(
        resource=resource,
        api_base=api_base,
        route_prefix=route_prefix,
        # You can add more global helpers later:
        json=json,
    )

    # add directory for js files
    app.mount("/static", StaticFiles(directory=SOURCE_ROOT / "static"), name="static")
    # add directory for optional webpage images
    if image_dir:
        app.mount("/images", StaticFiles(directory=image_dir), name="images")

    _register_resource_routes(app, dependencies.resource_bundles, app_config)

    # if there's only one resource, then no need for a separate home page
    if dependencies.num_resources > 1:
        _register_home_route(app)

    return app


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
