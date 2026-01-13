"""mkdocs page generation script."""

from pathlib import Path

import mkdocs_gen_files

# from reserve_it import PROJECT_ROOT
PROJECT_ROOT = Path(__file__).parents[1]
README_PATH = PROJECT_ROOT / "README.md"
SRC_ROOT = PROJECT_ROOT / "src"

# specific objects to include pages for in the code reference
INCLUDED_OBJECTS = [
    "reserve_it.app.build_app.build_app",
    "reserve_it.models.app_config.AppConfig",
    "reserve_it.models.resource_config.ResourceConfig",
    "reserve_it.models.reservation_request.ReservationRequest",
]
# whole files to include pages for in the code reference
INCLUDED_PY_FILES = [SRC_ROOT / "reserve_it" / "models" / "field_types.py"]


def gen_home_page(readme_path: Path):
    """generates homepage copied from README.md specified"""
    with mkdocs_gen_files.open("index.md", "w") as f:
        f.write(readme_path.read_text())


def gen_code_refs_and_nav(src_root: Path):
    """generates code reference page stubs for use by mkdocstrings, and updates the nav sidebar
    to include them"""
    nav = mkdocs_gen_files.Nav()

    for obj in INCLUDED_OBJECTS:
        name = obj.split(".")[-1]
        doc_path = f"{name}.md"
        full_doc_path = Path("reference", doc_path)
        nav[name] = doc_path

        with mkdocs_gen_files.open(full_doc_path, "w") as fd:
            fd.write(f"::: {obj}")

    for path in INCLUDED_PY_FILES:
        module_path = path.relative_to(src_root).with_suffix("")
        # flatten nav to just show files, not full hierarchy
        doc_path = Path(f"{path.stem}.md")
        full_doc_path = Path("reference", doc_path)

        parts = tuple(module_path.parts)

        if parts[-1] == "__init__":
            parts = parts[:-1]
        elif parts[-1] == "__main__":
            continue

        nav[path.stem] = doc_path

        with mkdocs_gen_files.open(full_doc_path, "w") as fd:
            ident = ".".join(parts)
            fd.write(f"::: {ident}")

    with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as nav_file:
        nav_file.writelines(nav.build_literate_nav())


# if __name__ == "__main__":
gen_home_page(README_PATH)
gen_code_refs_and_nav(SRC_ROOT)
