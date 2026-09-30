#!/usr/bin/env python3
"""Double-clickable launcher for the multiplication trainer.

``python3 play_multiplication.py`` — Math Jewel Hunters, the Inuyasha-themed
times-table hunt.  Its sibling ``play.py`` opens the subtraction trainer; both
can be running at once, on ports of their own.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from mathhunters.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main(game="multiplication")
