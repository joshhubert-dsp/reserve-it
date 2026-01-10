"""Console script for ppp_reservations."""

import contextlib
from pathlib import Path

import typer
from mkdocs.commands.serve import serve

app = typer.Typer(
    no_args_is_help=True, context_settings={"help_option_names": ["-h", "--help"]}
)

EXAMPLE_ROOT = Path(__file__).parent / "example"


@app.command()
def serve_example(port: int = 8080):
    """builds and serves a static example site for viewing purposes (no actual
    functionality beyond page navigation)."""
    with contextlib.chdir(EXAMPLE_ROOT):
        serve(
            config_file="mkdocs.yml",
            open_in_browser=True,
            dev_addr=f"localhost:{port}",
        )


@app.command()
def init(project_root: Path | None = None):
    """Initializes a new reserve-it project with the necessary directories and files."""
    if not project_root:
        project_root = Path.cwd()

    for file_or_dir in EXAMPLE_ROOT.rglob("*"):
        relative = file_or_dir.relative_to(EXAMPLE_ROOT)
        if file_or_dir.is_file():
            try:
                (project_root / relative).write_text(
                    (EXAMPLE_ROOT / relative).read_text("utf-8"), "utf-8"
                )
            except UnicodeDecodeError:  # not text, probably an image, don't need it
                pass

        elif file_or_dir.is_dir():
            (project_root / relative).mkdir()


if __name__ == "__main__":
    app()
