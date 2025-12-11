# Project configuration
project_name := "reserve-it"


set shell := ["zsh", "-c"]

# use uv as a script runner since we depend on it anyway
set script-interpreter := ['uv', 'run', '--script']
set unstable

# don't echo back commands
set quiet
set dotenv-load
set ignore-comments


# display help information
default:
    just --list


# run all tests
test:
    uv run pytest


# format code using ruff
format:
    uvx ruff format .


# run code quality checks
lint:
    uvx ruff check --fix .
    # TODO
    #uvx mypy .


# clean up temporary files and caches
[script]
clean:
    import shutil
    from pathlib import Path

    patterns = [
        ".pytest_cache",
        ".coverage",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        "**/__pycache__",
        "**/*.pyc",
    ]

    for pattern in patterns:
        for path in Path().glob(pattern):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)


