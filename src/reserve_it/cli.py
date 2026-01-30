from pathlib import Path

import typer

app = typer.Typer(
    no_args_is_help=True,
    help="A command line interface is provided with a couple conveniences.",
    context_settings={"help_option_names": ["-h", "--help"]},
)

EXAMPLE_ROOT = Path(__file__).parent / "example"


@app.command()
def serve_example(port: int = typer.Argument(8000, help="localhost port to serve on.")):
    """Builds and serves a non-functional static example site template on `localhost:PORT` for
    viewing purposes. Note that the embedded calendar view won't work since it's serving
    the page template directly (you'll see a bit of jinja syntax that the app uses to
    serve it), but you'll get a decent idea anyway."""
    import contextlib

    from mkdocs.commands.serve import serve

    with contextlib.chdir(EXAMPLE_ROOT):
        serve(
            config_file="mkdocs.yml",
            open_in_browser=True,
            dev_addr=f"localhost:{port}",
        )


README_TEXT = """\
# Google Calendar Credentials

This directory is intentionally gitignored by default.
Your `client-secret.json` downloaded from your installed google calendar app should go
here. `auth-token.json` will be generated and stored here as well on first run.
"""


def ensure_gcal_credentials_dir(root: Path) -> None:
    gcal_dir = root / ".gcal-credentials"
    gcal_dir.mkdir(exist_ok=True)
    readme = gcal_dir / "README.md"

    if not readme.exists():
        readme.write_text(README_TEXT, encoding="utf-8")


@app.command()
def init(
    project_root: Path | None = typer.Argument(
        None,
        help="Root path of your project to initialize. If none is passed, uses the current working directory. ",
    ),
):
    """Initializes a new reserve-it project with the necessary directories and files,
    copied directly from the `example` dir."""
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

    ensure_gcal_credentials_dir(project_root)


if __name__ == "__main__":
    app()
