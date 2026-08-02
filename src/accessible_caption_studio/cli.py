from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from .webapp import create_app

app = typer.Typer(help="Create, edit, validate, and export accessible captions.")


@app.callback()
def main() -> None:
    """Create, edit, validate, and export accessible captions."""


@app.command()
def start(
    storage: Annotated[Path, typer.Option(help="Folder used for private local projects.")] = Path(
        "storage"
    ),
    port: Annotated[int, typer.Option(min=1024, max=65535)] = 8765,
    open_browser: Annotated[bool, typer.Option("--open-browser/--no-open-browser")] = True,
) -> None:
    """Open Accessible Caption Studio in your browser."""
    address = f"http://127.0.0.1:{port}"
    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(address)).start()
    typer.echo(f"Accessible Caption Studio is open at {address}")
    typer.echo("Press Control+C to stop it. Your projects save automatically.")
    uvicorn.run(create_app(storage), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    app()
