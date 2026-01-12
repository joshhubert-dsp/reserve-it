from __future__ import annotations

import importlib.resources
import shutil
import tempfile
from datetime import date, datetime, timedelta
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
from pydantic import BaseModel, DirectoryPath, ValidationError

from reserve_it import ASSETS_DEST, ASSETS_SRC, IMAGES_DEST
from reserve_it.app.utils import load_resource_cfgs_from_yaml
from reserve_it.models.app_config import AppConfig
from reserve_it.models.field_types import AM_PM_TIME_FORMAT, YamlPath
from reserve_it.models.resource_config import ResourceConfig

CSS_ASSETS = [css.name for css in ASSETS_SRC.glob("*.css")]
JS_ASSETS = [js.name for js in ASSETS_SRC.glob("*.js")]


REMOTE_JS = ["https://unpkg.com/htmx.org@1.9.12"]
FORM_TEMPLATE = "form_page.md.j2"
FORM_TEMPLATES_DIR = "form-templates"


# TODO args for switching theme tweaks
class ReserveItPluginConfig(Config):
    """
    MkDocs plugin configuration schema.
    MkDocs reads these from mkdocs.yml and validates/coerces types.
    """

    app_config = config_options.Type(str, default=str(Path.cwd() / "app-config.yaml"))
    resource_config_dir = config_options.Type(
        str, default=str(Path.cwd() / "resource-configs")
    )
    assets_enabled = config_options.Type(bool, default=True)


class ConfigValidator(BaseModel):
    app_config: YamlPath
    resource_config_dir: DirectoryPath
    assets_enabled: bool


class ReserveItPlugin(BasePlugin[ReserveItPluginConfig]):
    """
    MkDocs plugin that generates resource reservation pages from YAML configs.

    User config example in mkdocs.yml:

    plugins:
      - reserve-it
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

    # --- HOOKS ---
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
        # self._add_markdown_exts(config)
        config["extra_javascript"] += REMOTE_JS

        if self.cfg.assets_enabled:
            # MkDocs will emit <script src="..."> for each entry in extra_javascript.
            # It will emit <link rel="stylesheet" href="..."> for each entry in extra_css.
            config["extra_javascript"] += [str(ASSETS_DEST / js) for js in JS_ASSETS]
            config["extra_css"] += [str(ASSETS_DEST / css) for css in CSS_ASSETS]

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

    def on_files(self, files: Files, config) -> Files:
        """
        MkDocs calls this with the discovered set of documentation source files.

        We can add additional virtual pages by appending mkdocs.structure.files.File objects.

        These files do NOT have to exist on disk if we also implement on_page_read_source
        to supply their contents as strings.
        """
        # if only one page, hide the nav bar
        single_page = (len(files) + len(self.resource_configs)) == 1

        # 2) For each resource, add a new virtual Markdown page.

        for cfg in self.resource_configs.values():
            # within the virtual docs tree
            src_path = f"{cfg.file_prefix}.md"

            # Generate Markdown content now (via Jinja template).
            self._generated_markdown[src_path] = self._render_resource_page_markdown(
                cfg, single_page
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

        return files

    def on_page_read_source(self, page: Page, config) -> str | None:
        """
        MkDocs calls this when it wants the *source Markdown text* for a page.

        For our virtual pages, return the generated Markdown string.
        For all other pages, return None to let MkDocs read from disk normally.
        """
        return self._generated_markdown.get(page.file.src_path)

    def on_post_build(self, config) -> None:
        """
        Called after MkDocs has rendered the site into `site/`.

        Perfect time to copy packaged JS/CSS assets into the final output folder,
        so that URLs we injected via extra_javascript/extra_css actually resolve.

        This does NOT modify the user's repo. It only affects the built output.
        """
        if not self.cfg.assets_enabled:
            return

        # Built site directory (where MkDocs outputs HTML/CSS/JS).
        dest_dir = config["site_dir"] / ASSETS_DEST
        dest_dir.mkdir(parents=True)
        for name in JS_ASSETS + CSS_ASSETS:
            src = ASSETS_SRC / name
            if not src.exists():
                raise FileNotFoundError(f"reserve-it asset missing from package: {src}")
            shutil.copy2(src, dest_dir / name)

        # copy over images, if provided
        image_rel_paths = [
            r.image.path for r in self.resource_configs.values() if r.image
        ]
        if image_rel_paths:
            image_dest_dir = config["site_dir"] / IMAGES_DEST
            image_dest_dir.mkdir(parents=True)
            for ipath in image_rel_paths:
                src = self.cfg.resource_config_dir / ipath
                shutil.copy2(src, image_dest_dir / ipath)

        self._copy_built_html_to_form_templates(config)

    def on_shutdown(self):
        # Clean up temp directory
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None

    # --- HELPERS ---

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

    def _render_resource_page_markdown(
        self, resource: ResourceConfig, single_page: bool
    ) -> str:
        """
        Custom Jinja step renders resource page Markdown using a template shipped in this package.
        Makes use of yaml frontmatter in the markdown page.
        """
        tpl = self._jinja.get_template(FORM_TEMPLATE)

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
            single_page=single_page,
            resource=resource,
            image_path=(IMAGES_DEST / resource.image.path).as_posix()
            if resource.image
            else None,
            custom_form_fields=[
                model.model_dump(mode="json") for model in resource.custom_form_fields
            ],
            time_slots=time_slots,
        )

    def _copy_built_html_to_form_templates(self, config) -> None:
        site_dir = Path(config["site_dir"])
        dest_root = site_dir / FORM_TEMPLATES_DIR

        for cfg in self.resource_configs.values():
            src = self._find_built_html(site_dir, cfg.file_prefix)
            if src is None:
                continue
            rel = src.relative_to(site_dir)
            dest = dest_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

    def _find_built_html(self, site_dir: Path, file_prefix: str) -> Path | None:
        candidates = [
            site_dir / Path(file_prefix) / "index.html",
            site_dir / f"{file_prefix}.html",
        ]

        for path in candidates:
            if path.exists():
                return path

        return None
