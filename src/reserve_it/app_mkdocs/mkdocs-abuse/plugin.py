from __future__ import annotations

from datetime import date, datetime, timedelta

from pydantic import BaseModel, DirectoryPath, ValidationError

from reserve_it.app.utils import load_resource_cfgs_from_yaml
from reserve_it.models.app_config import AppConfig
from reserve_it.models.field_types import AM_PM_TIME_FORMAT, YamlPath
from reserve_it.models.resource_config import ResourceConfig

"""
MkDocs plugin: reserve-it
-------------------------

Goal:
- User has YAML configs describing reservable resources (courts, chargers, etc.)
- At `mkdocs build` time, we generate one Markdown page per resource + an index page.
- We generate Markdown by rendering Jinja templates that live INSIDE this Python package.
- We DO NOT ask the user to copy templates/overrides into their repo.
- MkDocs then renders these pages normally, so Material search/nav works.

Key ideas:
- `on_files`: add "virtual" pages to MkDocs' file list.
- `on_page_read_source`: when MkDocs asks for a page's Markdown, we return a generated string.
- `on_config`: inject JS/CSS URLs into the MkDocs config so users don't have to.
- `on_post_build`: copy packaged assets into the built `site/` directory (so those URLs exist).
"""

import re
import shutil
from pathlib import Path

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from mkdocs.config import config_options
from mkdocs.config.base import Config
from mkdocs.exceptions import ConfigurationError
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import File, Files
from mkdocs.structure.pages import Page

# -----------------------------
# Data model for resource YAML
# -----------------------------


def slugify(s: str) -> str:
    """
    Basic slugify:
    - lowercases
    - turns spaces/underscores into '-'
    - strips repeated '-'

    This is intentionally simple and dependency-free.
    """
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9 _-]+", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-") or "resource"


# Custom Assets: ship JS/CSS from package into site/ and auto-include them.
ASSETS_DIR = Path("reserve-it-assets")
ASSETS = {
    "js_local": [],
    "js_remote": ["https://unpkg.com/htmx.org@1.9.12"],
    "css": ["reserve-it.css"],
}
# Template names inside this package's templates/ directory.
TEMPLATES = {
    "resource_page": "form-page.md.j2",
    "index_page": "index.md.j2",
}

# -----------------------------------
# The actual MkDocs plugin class
# -----------------------------------


class ReserveItPluginConfig(Config):
    """
    MkDocs plugin configuration schema.
    MkDocs reads these from mkdocs.yml and validates/coerces types.
    """

    app_config = config_options.Type(str, default="app-config.yaml")
    resource_config_dir = config_options.Type(str, default="resource-configs")
    image_dir = config_options.Type(str, default="resource-configs")
    assets_enabled = config_options.Type(bool, default=True)
    # Base path that your frontend calls for your FastAPI endpoints.
    # api_base = config_options.Type(str, default="/api")
    # Where generated docs live (inside MkDocs docs tree). This is logical paths,
    # not user filesystem paths.
    # docs_out_dir = config_options.Type(str, default="")


class ConfigValidator(BaseModel):
    app_config: YamlPath
    resource_config_dir: DirectoryPath
    image_dir: DirectoryPath
    assets_enabled: bool
    # Base path that your frontend calls for your FastAPI endpoints.
    # api_base: str
    # Where generated docs live (inside MkDocs docs tree). This is logical paths,
    # not user filesystem paths.
    # docs_out_dir: DirectoryPath


class ReserveItPlugin(BasePlugin[ReserveItPluginConfig]):
    """
    MkDocs plugin that generates resource pages from YAML configs.

    User config example in mkdocs.yml:

    plugins:
      - reserve-it:
          config_dir: client_configs/resources
          route_prefix: reserve
          api_base: /api
          include_index: true
          assets:
            enabled: true
            asset_dir: assets/reserve-it
    """

    def __init__(self):
        super().__init__()

        # Map virtual src_path -> generated Markdown content.
        # MkDocs will ask us "what is the source for this page?" later.
        self._generated_markdown: dict[str, str] = {}

        # Stash resources so multiple hooks can access them.
        self.resource_configs: dict[str, ResourceConfig] = {}

        # Jinja environment for rendering templates FROM THIS INSTALLED PACKAGE.
        # - PackageLoader points at reserve_it_mkdocs/templates
        # - StrictUndefined makes missing variables fail loudly (good for debugging)
        self._jinja = Environment(
            loader=PackageLoader("reserve_it", "templates"),
            undefined=StrictUndefined,
            autoescape=select_autoescape(enabled_extensions=()),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    # -----------------------------
    # Hook: on_config
    # -----------------------------
    def on_config(self, config):
        """
        Called early. Great place to:
        - inject extra JS/CSS into MkDocs config so user doesn't have to
        - normalize paths
        - read basic settings

        IMPORTANT:
        - This runs before rendering begins.
        """

        try:
            self.cfg = ConfigValidator.model_validate(self.config)
        except ValidationError as e:
            # MkDocs wants ConfigurationError for pretty output
            raise ConfigurationError(str(e)) from e

        if self.cfg.assets_enabled:
            # MkDocs will emit <script src="..."> for each entry in extra_javascript.
            # It will emit <link rel="stylesheet" href="..."> for each entry in extra_css.
            extra_js = config.get("extra_javascript", [])
            extra_css = config.get("extra_css", [])

            for js in ASSETS.get("js_local", []):
                extra_js.append(ASSETS_DIR / js)

            for js in ASSETS.get("js_remote", []):
                extra_js.append(js)

            for css in ASSETS.get("css", []):
                extra_css.append(ASSETS_DIR / css)

            config["extra_javascript"] = extra_js
            config["extra_css"] = extra_css

        return config

    # -----------------------------
    # Hook: on_files
    # -----------------------------
    def on_files(self, files: Files, config) -> Files:
        """
        MkDocs calls this with the discovered set of documentation source files.

        We can add additional virtual pages by appending mkdocs.structure.files.File objects.

        These files do NOT have to exist on disk if we also implement on_page_read_source
        to supply their contents as strings.
        """

        self.resource_configs = load_resource_cfgs_from_yaml(
            self.cfg.resource_config_dir, AppConfig.from_yaml(self.cfg.app_config)
        )

        # 2) For each resource, add a new virtual Markdown page.

        for name, cfg in self.resource_configs.items():
            # within the virtual docs tree
            src_path = f"{name}.md"
            # src_path = self.cfg.docs_out_dir / f"{name}.md"

            # Generate Markdown content now (via Jinja template).
            self._generated_markdown[src_path] = self._render_resource_page_markdown(
                cfg
            )

            # Add file to MkDocs "known files". MkDocs uses docs_dir for source root,
            # but the file doesn't actually need to exist because we'll provide content later.
            files.append(
                File(
                    path=src_path,  # doc-relative path
                    src_dir=None,  # virtual file
                    # output root, arg already available at yaml top level
                    dest_dir=config["site_dir"],
                    use_directory_urls=True,
                )
            )

        # 3) Optional index page: <base>/index.md listing all resources.
        # if bool(self.config["include_index"]):
        #     index_src_path = f"{base}/index.md"
        #     self._generated_markdown[index_src_path] = self._render_index_page_markdown(
        #         resources=self.resource_configs,
        #         route_prefix=route_prefix,
        #         base_path=base,
        #     )
        #     files.append(
        #         File(
        #             path=index_src_path,
        #             src_dir=str(Path(config["docs_dir"])),
        #             dest_dir=config["site_dir"],
        #             use_directory_urls=config.get("use_directory_urls", True),
        #         )
        #     )

        return files

    # -----------------------------
    # Hook: on_page_read_source
    # -----------------------------
    def on_page_read_source(self, page: Page, config) -> str | None:
        """
        MkDocs calls this when it wants the *source Markdown text* for a page.

        For our virtual pages, return the generated Markdown string.
        For all other pages, return None to let MkDocs read from disk normally.
        """
        return self._generated_markdown.get(page.file.src_path)

    # -----------------------------
    # Hook: on_post_build
    # -----------------------------
    def on_post_build(self, config) -> None:
        """
        Called after MkDocs has rendered the site into `site/`.

        Perfect time to copy packaged JS/CSS assets into the final output folder,
        so that URLs we injected via extra_javascript/extra_css actually resolve.

        This does NOT modify the user's repo. It only affects the built output.
        """
        if not self.cfg.assets_enabled:
            return

        js_files = ASSETS.get("js_local", [])
        css_files = ASSETS.get("css", [])

        # Built site directory (where MkDocs outputs HTML/CSS/JS).
        target_dir = config["site_dir"] / ASSETS_DIR
        target_dir.mkdir(parents=True, exist_ok=True)

        # Our packaged static assets live at: reserve_it_mkdocs/static/*
        pkg_root = Path(__file__).resolve().parent
        static_dir = pkg_root / ASSETS_DIR

        # Copy whatever files are declared in config.
        for name in js_files + css_files:
            src = static_dir / name
            if not src.exists():
                # Fail loudly: missing asset in package = broken install.
                raise FileNotFoundError(f"reserve-it asset missing from package: {src}")
            shutil.copy2(src, target_dir / name)

    # -----------------------------
    # Jinja rendering helpers
    # -----------------------------
    def _render_resource_page_markdown(self, resource: ResourceConfig) -> str:
        """
        Render resource page Markdown using a Jinja template shipped in this package.

        This is your "custom Jinja step", but we keep it producing Markdown, not HTML.
        That means MkDocs + Material still do all the theming + search + nav work.
        """
        tpl_name = TEMPLATES["resource_page"]
        tpl = self._jinja.get_template(tpl_name)

        dt_start = datetime.combine(date.today(), resource.day_start_time)
        dt_end = datetime.combine(date.today(), resource.day_end_time)
        time_slots = [dt_start]

        while (
            next_dt := time_slots[-1] + timedelta(minutes=resource.minutes_increment)
        ) <= dt_end:
            time_slots.append(next_dt)

        time_slots = [dt.time().strftime(AM_PM_TIME_FORMAT) for dt in time_slots]

        # Everything you pass here becomes available in the .md.j2 template.
        return tpl.render(
            resource=resource,
            custom_form_fields=[
                model.model_dump(mode="json") for model in resource.custom_form_fields
            ],
            time_slots=time_slots,
        )

    # def _render_index_page_markdown(
    #     self, resources: list[Resource], route_prefix: str, base_path: str
    # ) -> str:
    #     """
    #     Render index page Markdown listing resources.
    #     """
    #     tpl_name = str(self.config["templates"]["index_page"])
    #     tpl = self._jinja.get_template(tpl_name)

    #     return tpl.render(
    #         resources=resources,
    #         route_prefix=route_prefix,
    #         base_path=base_path,
    #     )
