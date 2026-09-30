"""The front end is shared by both trainers, so its contract is worth a test.

``tests/game_config_check.js`` reads app.js, works out every setting it takes
from a game's config, and looks for each one in both games' ``game.js`` — plus
it checks each game's forge rules against the limits the Python engine enforces.
Node is not needed to play either game, only to run this check, so it is skipped
when node is not installed.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mathhunters import games as games_mod  # noqa: E402
from mathhunters.engine import MASTERY_TARGET, MAX_OPERAND, MAX_POOL_SIZE  # noqa: E402
from mathhunters.server import WEB_DIR  # noqa: E402

NODE = shutil.which("node")
CHECK = Path(__file__).resolve().parent / "game_config_check.js"

# Files a game's skin must ship; anything else it needs is shared.
SKIN_FILES = ("index.html", "skin.css", "game.js", "strategies.js")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_every_game_config_supplies_what_the_front_end_reads():
    result = subprocess.run(
        [NODE, str(CHECK)], capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, f"\n{result.stdout}{result.stderr}"


@pytest.mark.parametrize("game", sorted(games_mod.GAMES))
def test_every_game_ships_a_complete_skin(game):
    skin = WEB_DIR / games_mod.get(game).web_dir
    missing = [name for name in SKIN_FILES if not (skin / name).is_file()]
    assert not missing, f"{game} is missing {missing}"


def test_the_front_end_script_is_shared_not_copied():
    copies = sorted(p for p in WEB_DIR.glob("*/app.js"))
    assert copies == [], f"app.js should only exist once, found copies: {copies}"
    assert (WEB_DIR / "app.js").is_file()
    assert (WEB_DIR / "theme.css").is_file()


def test_the_javascript_check_knows_the_real_limits():
    """The node check hard-codes the engine's limits; keep them in step."""
    rules = (CHECK.read_text().split("const RULES =", 1)[1]).split("\n", 1)[0]
    for value in (MAX_OPERAND, MAX_POOL_SIZE, MASTERY_TARGET):
        assert str(value) in rules, f"{value} is missing from {rules.strip()}"
