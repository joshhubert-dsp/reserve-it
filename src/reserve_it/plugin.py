from __future__ import annotations

import tempfile
from datetime import date, datetime, timedelta

from pydantic import BaseModel, DirectoryPath, ValidationError

from reserve_it import MKDOCS_ROOT
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

# Python 3.9+
import importlib.resources
import shutil
from pathlib import Path

from jinja2 import (
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    PackageLoader,
    StrictUndefined,
    select_autoescape,
)
from material.extensions.emoji import to_svg, twemoji
from mkdocs.config import config_options
from mkdocs.config.base import Config
from mkdocs.exceptions import ConfigurationError
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import File, Files
from mkdocs.structure.pages import Page

# -----------------------------
# Data model for resource YAML
# -----------------------------


# def slugify(s: str) -> str:
#     """
#     Basic slugify:
#     - lowercases
#     - turns spaces/underscores into '-'
#     - strips repeated '-'

#     This is intentionally simple and dependency-free.
#     """
#     s = s.strip().lower()
#     s = re.sub(r"[^a-z0-9 _-]+", "", s)
#     s = re.sub(r"[\s_]+", "-", s)
#     s = re.sub(r"-{2,}", "-", s)
#     return s.strip("-") or "resource"


# Custom Assets: ship JS/CSS from package into site/ and auto-include them.
ASSETS_DIR = Path("assets/reserve-it")
ASSETS = {
    "js_local": [],
    "js_remote": ["https://unpkg.com/htmx.org@1.9.12"],
    "css": ["reserve-it.css"],
}
# Template names inside this package's templates/ directory.
TEMPLATES = {
    "resource_page": "form_page.md.j2",
    "index_page": "index.md.j2",
}
# MARKDOWN_EXTENSIONS = ["pymdownx.frontmatter"]


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
    assets_enabled = config_options.Type(bool, default=True)
    # Base path that your frontend calls for your FastAPI endpoints.
    # api_base = config_options.Type(str, default="/api")
    # Where generated docs live (inside MkDocs docs tree). This is logical paths,
    # not user filesystem paths.
    # docs_out_dir = config_options.Type(str, default="")


class ConfigValidator(BaseModel):
    app_config: YamlPath
    resource_config_dir: DirectoryPath
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
        self.app_config: AppConfig | None = None
        self._tmp: tempfile.TemporaryDirectory | None = None
        self._plugin_template_dir: Path | None = None

        # Jinja environment for rendering templates FROM THIS INSTALLED PACKAGE.
        # - PackageLoader points at reserve_it_mkdocs/templates
        # - StrictUndefined makes missing variables fail loudly (good for debugging)
        self._jinja = Environment(
            loader=PackageLoader("reserve_it", "mkdocs_abuse/templates"),
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

        self.app_config = AppConfig.from_yaml(self.cfg.app_config)
        self.resource_configs = load_resource_cfgs_from_yaml(
            self.cfg.resource_config_dir, self.app_config
        )

        # if not config.get("site_name"):
        config["site_name"] = self.app_config.title
        # config["use_directory_urls"] = True

        self._extract_templates(config)
        self._add_markdown_exts(config)
        # config["markdown_extensions"] += MARKDOWN_EXTENSIONS

        if self.cfg.assets_enabled:
            # MkDocs will emit <script src="..."> for each entry in extra_javascript.
            # It will emit <link rel="stylesheet" href="..."> for each entry in extra_css.
            extra_js = config.get("extra_javascript", [])
            extra_css = config.get("extra_css", [])

            for js in ASSETS.get("js_local", []):
                extra_js.append(str(ASSETS_DIR / js))

            for js in ASSETS.get("js_remote", []):
                extra_js.append(js)

            for css in ASSETS.get("css", []):
                extra_css.append(str(ASSETS_DIR / css))

            config["extra_javascript"] = extra_js
            config["extra_css"] = extra_css

        return config

    def _extract_templates(self, config):
        """
        Extract packaged templates to a real filesystem directory.
        Jinja2's FileSystemLoader needs actual files.
        """
        self._tmp = tempfile.TemporaryDirectory(prefix="reserve_it_templates_")
        out_dir = Path(self._tmp.name)

        # reserve_it/templates inside your installed package
        pkg_templates = Path(
            importlib.resources.files("reserve_it.mkdocs_abuse").joinpath("templates")
        )

        # Copy templates out of the package into the temp dir
        for res in pkg_templates.rglob("*"):
            if res.is_dir():
                continue
            rel = res.relative_to(pkg_templates)
            dst = out_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(res.read_bytes())

        self._plugin_template_dir = out_dir
        return config

    def on_env(self, env, config, files):
        """
        Add plugin templates to the Jinja loader search path.
        This makes `template: ri-form.html` resolvable.
        """
        if not self._plugin_template_dir:
            return env

        plugin_loader = FileSystemLoader(str(self._plugin_template_dir))

        # Put plugin loader AFTER user's overrides but BEFORE theme defaults.
        # Usually env.loader is already a ChoiceLoader; we just extend it.
        if isinstance(env.loader, ChoiceLoader):
            loaders = list(env.loader.loaders)
            env.loader = ChoiceLoader(loaders + [plugin_loader])
        else:
            env.loader = ChoiceLoader([env.loader, plugin_loader])

        return env

    def _add_markdown_exts(self, config):
        # 1) Ensure pymdownx.emoji is enabled
        mdx = config.setdefault("markdown_extensions", [])
        if "pymdownx.emoji" not in mdx:
            mdx.append("pymdownx.emoji")

        # 2) Ensure its config exists and set the callables
        # MkDocs commonly uses `mdx_configs`; some setups use `markdown_extensions_configs`
        cfg_key = (
            "mdx_configs" if "mdx_configs" in config else "markdown_extensions_configs"
        )
        mdx_cfgs = config.setdefault(cfg_key, {})
        emoji_cfg = mdx_cfgs.setdefault("pymdownx.emoji", {})

        # Set/override the bits you want
        emoji_cfg["emoji_index"] = twemoji
        emoji_cfg["emoji_generator"] = to_svg

    # def _add_markdown_exts(self, config):
    #     # MkDocs stores extension names in a list.
    #     mdx = config.get("markdown_extensions") or []
    #     existing = set(mdx)

    #     for ext in self.config["markdown_extensions"]:
    #         if ext not in existing:
    #             mdx.append(ext)
    #             existing.add(ext)

    #     config["markdown_extensions"] = mdx

    #     # Extension configs live in a dict keyed by extension name.
    #     # MkDocs historically used `markdown_extensions_configs`, but in many
    #     # setups you'll see `mdx_configs`. We'll support both.
    #     mdx_cfg_key = (
    #         "mdx_configs" if "mdx_configs" in config else "markdown_extensions_configs"
    #     )
    #     mdx_cfg = dict(config.get(mdx_cfg_key) or {})

    #     for ext, ext_cfg in (self.config["markdown_extensions_config"] or {}).items():
    #         if ext_cfg is None:
    #             continue
    #         if not isinstance(ext_cfg, Mapping):
    #             raise TypeError(
    #                 f"markdown_extensions_config[{ext!r}] must be a mapping, got {type(ext_cfg)}"
    #             )
    #         # Merge (plugin config wins only where it sets keys)
    #         merged = dict(mdx_cfg.get(ext) or {})
    #         merged.update(ext_cfg)
    #         mdx_cfg[ext] = merged

    #     config[mdx_cfg_key] = mdx_cfg

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

        # 2) For each resource, add a new virtual Markdown page.

        for cfg in self.resource_configs.values():
            # within the virtual docs tree
            src_path = f"{cfg.name}.md"

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

        # Our packaged static assets live at:
        static_dir = MKDOCS_ROOT / "assets"

        # Copy whatever files are declared in config.
        for name in js_files + css_files:
            src = static_dir / name
            if not src.exists():
                # Fail loudly: missing asset in package = broken install.
                raise FileNotFoundError(f"reserve-it asset missing from package: {src}")
            shutil.copy2(src, target_dir / name)

    def on_shutdown(self):
        # Clean up temp directory
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None

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
