"""The trainers this app can launch.

Both games run the same engine, server and front-end script; a ``Game`` is the
short list of things that make one of them itself — which operation it drills,
what it is called, which skin the browser loads, and where its progress lives.

Adding a third trainer means adding an ``Operation`` in :mod:`engine`, a folder
under ``web/`` with the four skin files, and one entry here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .engine import MUL, SUB


@dataclass(frozen=True)
class Game:
    """One trainer: an operation, a skin, and its own saved progress."""

    id: str
    op: str  # the engine operation it drills
    title: str  # banner and window title
    tagline: str  # one line under the title in the console banner
    web_dir: str  # folder inside web/ holding this game's skin
    home_dir: str  # folder under $HOME when no --data-dir is given
    progress_file: str  # file inside the data dir, so a shared dir is still safe
    assets_dir: str  # folder under the repo's assets root ("" is the root itself)
    port: int  # preferred port, so both can be open at once

    @property
    def default_data_dir(self) -> Path:
        return Path.home() / self.home_dir


SUBTRACTION = Game(
    id="subtraction",
    op=SUB,
    title="MATH DEMON HUNTERS",
    tagline="Seal the demons. One subtraction at a time.",
    web_dir="subtraction",
    home_dir=".math-demon-hunters",
    progress_file="progress.json",
    assets_dir="",
    port=8765,
)

MULTIPLICATION = Game(
    id="multiplication",
    op=MUL,
    title="MATH JEWEL HUNTERS",
    tagline="Claim every shard. One times table at a time.",
    web_dir="multiplication",
    home_dir=".math-jewel-hunters",
    # Named apart from the subtraction trainer's, so even one shared --data-dir
    # cannot have one game's save overwrite the other's.
    progress_file="progress-multiplication.json",
    assets_dir="jewel",
    port=8766,
)

GAMES: dict[str, Game] = {SUBTRACTION.id: SUBTRACTION, MULTIPLICATION.id: MULTIPLICATION}
DEFAULT_GAME = SUBTRACTION.id


def get(name: str | Game | None = None) -> Game:
    """Look up a game by name; ``None`` gives the subtraction trainer."""
    if isinstance(name, Game):
        return name
    if not name:
        return GAMES[DEFAULT_GAME]
    try:
        return GAMES[name]
    except KeyError:
        known = ", ".join(sorted(GAMES))
        raise ValueError(f"unknown game {name!r} — pick one of: {known}") from None
