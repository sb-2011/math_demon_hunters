"""Command line entry point: ``python3 -m mathhunters``."""

from __future__ import annotations

import argparse
from pathlib import Path

from .server import ASSETS_DIR, IMAGES_DIR, serve
from .storage import default_data_dir


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="mathhunters",
        description="Launch the Math Demon Hunters subtraction trainer.",
    )
    parser.add_argument("--port", type=int, default=8765, help="preferred port (default: 8765)")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help=f"where progress is saved (default: {default_data_dir()})",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=None,
        help=f"folder scanned for custom artwork (default: {ASSETS_DIR})",
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
        )
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
