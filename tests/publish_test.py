from __future__ import annotations

import sys
from importlib import metadata
from importlib.resources import files


def main() -> None:
    """test run by publish-pypi workflow on both sdist and wheel"""
    # 1) Import
    import reserve_it  # noqa: F401

    # 2) Package data is present in installed artifact
    # Adjust filename(s) to something you know must ship.
    nonpy_files_to_check = [
        "mkdocs_abuse/templates/form_page.md.j2",
        "mkdocs_abuse/templates/ri_form.html",
        "mkdocs_abuse/templates/ri_base.html",
        "mkdocs_abuse/assets/theme-tweaks.css",
        "mkdocs_abuse/assets/reserve-it.css",
        "app/templates/response.html",
        "example/app-config.yaml",
        "example/mkdocs.yml",
        "example/resource-configs/1-chargers.yaml",
        "example/resource-configs/2-courts.yaml",
        "example/resource-configs/courts.jpg",
        "example/docs/readme.md",
        "example/.gitignore",
        "example/.gcal-credentials/README.md",
    ]
    for f in nonpy_files_to_check:
        assert (files("reserve_it") / f).is_file(), f"Missing file in package data: {f}"

    # 3) FastAPI templating can load it (catches wrong loader/search path)
    from fastapi.templating import Jinja2Templates
    from jinja2 import Environment, PackageLoader, select_autoescape

    templates = Jinja2Templates(
        env=Environment(
            loader=PackageLoader("reserve_it", "app/templates"),
            autoescape=select_autoescape(["html", "xml"]),
        )
    )
    # Will raise TemplateNotFound if broken
    templates.env.get_template("response.html")

    # 4) MkDocs plugin entry point resolves
    eps = metadata.entry_points(group="mkdocs.plugins")
    ep = next((e for e in eps if e.name == "reserve-it"), None)
    assert ep is not None, "mkdocs.plugins entry point 'reserve-it' not found"
    plugin_cls = ep.load()
    assert plugin_cls is not None, "entry point load returned None"

    # Optional: assert it’s the class you expect
    assert plugin_cls.__name__ == "ReserveItPlugin"

    print("publish_test: ok", file=sys.stderr)


if __name__ == "__main__":
    main()
