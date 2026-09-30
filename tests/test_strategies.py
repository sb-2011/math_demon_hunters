"""The strategy pictures live in the browser, so their checks run under node.

Each trainer has its own ``tests/strategies_check_<game>.js``, which loads that
game's ``strategies.js`` and exercises every problem its strategies cover.  Node
is not needed to play either game, only to run these checks, so they are skipped
when node is not installed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
CHECKS_DIR = Path(__file__).resolve().parent


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("game", ["subtraction", "multiplication"])
def test_strategy_pictures_hold_up(game):
    check = CHECKS_DIR / f"strategies_check_{game}.js"
    result = subprocess.run(
        [NODE, str(check)], capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, f"\n{result.stdout}{result.stderr}"
