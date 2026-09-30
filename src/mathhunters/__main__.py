"""Command line entry point: ``python3 -m mathhunters [--game GAME]``."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import games as games_mod
from .server import IMAGES_DIR, game_assets_dir, serve
from .storage import default_data_dir


def main(argv: list[str] | None = None, game: str | None = None) -> None:
    """Launch a trainer.

    ``game`` is what the double-clickable launchers pass, and it also sets the
    defaults shown in ``--help``; on the command line ``--game`` overrides it.
    Either way, subtraction is what you get by asking for nothing.
    """
    default_game = games_mod.get(game)
    parser = argparse.ArgumentParser(
        prog="mathhunters",
        description="Launch a Math Hunters trainer: subtraction, or multiplication.",
    )
    parser.add_argument(
        "--game",
        choices=sorted(games_mod.GAMES),
        default=default_game.id,
        help=f"which trainer to play (default: {default_game.id})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"preferred port (default: {default_game.port} for {default_game.id})",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help=f"where progress is saved (default: {default_data_dir(default_game)})",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=None,
        help=f"folder scanned for custom artwork (default: {game_assets_dir(default_game)})",
    )
    parser.add_argument(
        "--images",
        type=Path,
        default=None,
        metavar="DIR",
        help=f"image pack to play with, e.g. {IMAGES_DIR}/kpop-demon-hunters",
    )
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    args = parser.parse_args(argv)

    try:
        serve(
            host=args.host,
            port=args.port,
            data_dir=args.data_dir,
            assets_dir=args.assets_dir,
            images=args.images,
            open_browser=not args.no_browser,
            game=args.game,
        )
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
