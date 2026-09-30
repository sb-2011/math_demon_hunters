#!/usr/bin/env python3
"""Double-clickable launcher for the subtraction trainer.

``python3 play.py`` — Math Demon Hunters.  Its sibling
``play_multiplication.py`` opens the Inuyasha-themed times-table hunt.

Adds ``src/`` to the import path so the app runs straight from a checkout with
no install step, then hands off to the normal CLI entry point.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from mathhunters.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main(game="subtraction")
