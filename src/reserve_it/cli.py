import contextlib
from pathlib import Path

import typer
from mkdocs.commands.serve import serve

app = typer.Typer(
    no_args_is_help=True, context_settings={"help_option_names": ["-h", "--help"]}
)

EXAMPLE_ROOT = Path(__file__).parent / "example"


@app.command()
def serve_example(port: int = 8000):
    """Builds and serves a static example site template for viewing purposes. No actual
    functionality beyond page navigation and no embedded calendar view, and a bit of
    jinja template syntax strewn about, but gives you a good idea of the aesthetic anyway."""
    with contextlib.chdir(EXAMPLE_ROOT):
        serve(
            config_file="mkdocs.yml",
            open_in_browser=True,
            dev_addr=f"localhost:{port}",
        )


@app.command()
def init(project_root: Path | None = None):
    """Initializes a new reserve-it project with the necessary directories and files,
    copied directly from example dir."""
    if not project_root:
        project_root = Path.cwd()

    for file_or_dir in EXAMPLE_ROOT.rglob("*"):
        relative = file_or_dir.relative_to(EXAMPLE_ROOT)

        if file_or_dir.is_file():
            dest = project_root / relative
            if not dest.exists():
                try:
                    dest.write_text(file_or_dir.read_text("utf-8"), "utf-8")
                except UnicodeDecodeError:  # not text, probably an image, don't need it
                    pass
            elif file_or_dir.name == ".gitignore":
                # append to an existing gitignore
                with open(dest, "a", encoding="utf-8") as f:
                    f.write("\n" + file_or_dir.read_text("utf-8"))

        elif file_or_dir.is_dir():
            (project_root / relative).mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    app()
