"""JSON-file persistence for hunt progress.

Everything lives in one small file so a parent can back it up, inspect it, or
delete it without touching the app.  Writes go through a temp file + rename so
an interrupted save can never leave a half-written profile behind.

Each trainer keeps its own store: a different folder by default, and a different
file name inside it, so pointing both games at one data dir with ``--data-dir``
still cannot have one overwrite the other's hunts.  A store also ignores saved
hunts belonging to another operation, whatever file they turn up in.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from . import games as games_mod
from .engine import Series, SeriesError

SCHEMA_VERSION = 1
ENV_DATA_DIR = "MATH_HUNTERS_DATA_DIR"


def default_data_dir(game: games_mod.Game | str | None = None) -> Path:
    """Where this game saves when nothing else is asked for.

    The environment override is per-game too: it names the folder the trainers
    save under, each still in its own subfolder.
    """
    resolved = games_mod.get(game)
    override = os.environ.get(ENV_DATA_DIR)
    if override:
        root = Path(override).expanduser()
        return root if resolved.id == games_mod.DEFAULT_GAME else root / resolved.id
    return resolved.default_data_dir


class Store:
    """Thread-safe collection of one game's saved series, keyed by hunt id."""

    def __init__(
        self, data_dir: Path | None = None, game: games_mod.Game | str | None = None
    ) -> None:
        self.game = games_mod.get(game)
        self.data_dir = Path(data_dir) if data_dir else default_data_dir(self.game)
        self.path = self.data_dir / self.game.progress_file
        self._lock = threading.RLock()
        self._series: dict[str, Series] = {}
        self.load()

    # -- persistence ----------------------------------------------------------

    def load(self) -> None:
        with self._lock:
            self._series = {}
            if not self.path.exists():
                return
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                # A corrupt profile should not brick the app; park it and start clean.
                self._quarantine()
                return
            for entry in raw.get("series", []):
                try:
                    series = Series.from_dict(entry)
                except (SeriesError, KeyError, TypeError, ValueError):
                    continue
                if series.op != self.game.op:
                    continue  # another trainer's hunt; not this one's business
                # Two hunts saved under the old one-sided scheme can upgrade to
                # the same pool (10 − 10 either way round); keep the livelier one.
                clash = self._series.get(series.id)
                if clash is None or series.updated_at >= clash.updated_at:
                    self._series[series.id] = series

    def save(self) -> None:
        with self._lock:
            payload: dict[str, Any] = {
                "version": SCHEMA_VERSION,
                "series": [s.to_dict() for s in self.all_series()],
            }
            self.data_dir.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(dir=self.data_dir, prefix=".progress-", suffix=".json")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=2)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_name, self.path)
            except BaseException:
                Path(tmp_name).unlink(missing_ok=True)
                raise

    def _quarantine(self) -> None:
        backup = self.path.with_suffix(".corrupt.json")
        try:
            os.replace(self.path, backup)
        except OSError:
            pass

    # -- access ---------------------------------------------------------------

    def all_series(self) -> list[Series]:
        with self._lock:
            return sorted(self._series.values(), key=lambda s: s.updated_at, reverse=True)

    def get(self, series_id: str) -> Series | None:
        with self._lock:
            return self._series.get(series_id)

    def get_or_create(
        self, m1: int, m2: int, s1: int, s2: int, allow_negative: bool = False
    ) -> Series:
        op = self.game.op
        series_id = Series.make_id(m1, m2, s1, s2, allow_negative, op=op)
        with self._lock:
            series = self._series.get(series_id)
            if series is None:
                series = Series.create(m1, m2, s1, s2, allow_negative, op=op)
                self._series[series_id] = series
                self.save()
            return series

    def delete(self, series_id: str) -> bool:
        with self._lock:
            if series_id in self._series:
                del self._series[series_id]
                self.save()
                return True
            return False

    @property
    def lock(self) -> threading.RLock:
        return self._lock
