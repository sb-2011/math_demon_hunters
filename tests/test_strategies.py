"""The strategy pictures live in the browser, so their checks run under node.

``tests/strategies_check.js`` loads ``web/strategies.js`` and exercises every
problem the bridge covers.  Node is not needed to play the game, only to run
this one test, so it is skipped when node is not installed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
CHECK = Path(__file__).resolve().parent / "strategies_check.js"


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_strategy_pictures_hold_up():
    result = subprocess.run(
        [NODE, str(CHECK)], capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, f"\n{result.stdout}{result.stderr}"
