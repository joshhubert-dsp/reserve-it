"""mkdocs page generation script."""

from pathlib import Path

import mkdocs_gen_files

PROJECT_ROOT = Path(__file__).parents[1]
README_PATH = PROJECT_ROOT / "README.md"
SRC_ROOT = PROJECT_ROOT / "src"

INCLUDED_PY_FILES = [
    SRC_ROOT / "reserve_it" / "app" / "build_app.py",
    SRC_ROOT / "reserve_it" / "models" / "app_config.py",
    SRC_ROOT / "reserve_it" / "models" / "resource_config.py",
    SRC_ROOT / "reserve_it" / "models" / "field_types.py",
    SRC_ROOT / "reserve_it" / "models" / "reservation_request.py",
    # SRC_ROOT / "reserve_it" / "__init__.py",
]


def gen_home_page(readme_path: Path):
    """generates homepage copied from README.md specified"""
    with mkdocs_gen_files.open("index.md", "w") as f:
        f.write(readme_path.read_text())


def gen_code_refs_and_nav(src_root: Path):
    """generates code reference page stubs for use by mkdocstrings, and updates the nav sidebar
    to include them"""
    nav = mkdocs_gen_files.Nav()

    for path in INCLUDED_PY_FILES:
        # for path in sorted(src_root.rglob("*.py")):
        module_path = path.relative_to(src_root).with_suffix("")
        doc_path = path.relative_to(src_root).with_suffix(".md")
        full_doc_path = Path("reference", doc_path)

        parts = tuple(module_path.parts)

        if parts[-1] == "__init__":
            parts = parts[:-1]
        elif parts[-1] == "__main__":
            continue

        nav[parts] = doc_path.as_posix()

        with mkdocs_gen_files.open(full_doc_path, "w") as fd:
            ident = ".".join(parts)
            fd.write(f"::: {ident}")

        mkdocs_gen_files.set_edit_path(full_doc_path, path.relative_to(src_root))

    with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as nav_file:
        nav_file.writelines(nav.build_literate_nav())


# if __name__ == "__main__":
gen_home_page(README_PATH)
gen_code_refs_and_nav(SRC_ROOT)
