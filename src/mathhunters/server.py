"""Standard-library HTTP server for the trainers' UI.

No third-party dependencies: ``http.server`` serves the front end and a small
JSON API.  The socket is bound to loopback only -- this is a local app for one
kid at one desk, not something to expose on a network.

One server runs one game (see :mod:`games`).  Static files are looked up in that
game's skin folder first and in the shared ``web/`` folder second, so both
trainers share one front-end script and differ only in their skins.
"""

from __future__ import annotations

import json
import re
import socket
import threading
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import assets as assets_mod
from . import games as games_mod
from . import packs as packs_mod
from .engine import (
    CORRECT_POINTS,
    MASTERY_TARGET,
    MAX_OPERAND,
    MAX_POOL_SIZE,
    TIMER_DEFAULT_SECONDS,
    TIMER_MAX_SECONDS,
    TIMER_MIN_SECONDS,
    WRONG_PENALTY,
    Series,
    SeriesError,
    clamp_timer_seconds,
    operation,
)
from .storage import Store

PACKAGE_DIR = Path(__file__).resolve().parent
WEB_DIR = PACKAGE_DIR / "web"
PROJECT_ROOT = PACKAGE_DIR.parents[1]
ASSETS_DIR = PROJECT_ROOT / "assets"
IMAGES_DIR = PROJECT_ROOT / "images"

# The leading letter is the operation's (see engine.Operation.id_prefix).
SERIES_ID_RE = re.compile(r"^[a-z]\d{1,3}-\d{1,3}x\d{1,3}-\d{1,3}(-neg)?$")

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
    ".ico": "image/x-icon",
}

MAX_BODY_BYTES = 64 * 1024


class ApiError(Exception):
    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class HunterServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        store: Store,
        assets_dir: Path,
        images_root: Path | None = None,
        default_pack: str | None = None,
        game: games_mod.Game | str | None = None,
    ) -> None:
        super().__init__(address, HunterHandler)
        self.store = store
        # A store already belongs to a game; naming one here is for tests.
        self.game = games_mod.get(game if game is not None else store.game)
        self.assets_dir = assets_dir
        self.images_root = images_root or IMAGES_DIR
        self.default_pack = default_pack


class HunterHandler(BaseHTTPRequestHandler):
    server_version = "MathDemonHunters"
    protocol_version = "HTTP/1.1"

    # -- plumbing -------------------------------------------------------------

    @property
    def store(self) -> Store:
        return self.server.store  # type: ignore[attr-defined]

    @property
    def game(self) -> games_mod.Game:
        return self.server.game  # type: ignore[attr-defined]

    @property
    def assets_dir(self) -> Path:
        return self.server.assets_dir  # type: ignore[attr-defined]

    @property
    def images_root(self) -> Path:
        return self.server.images_root  # type: ignore[attr-defined]

    @property
    def default_pack(self) -> str | None:
        return self.server.default_pack  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        """Quiet by default -- the console belongs to the launch banner."""

    def _send(self, status: int, body: bytes, content_type: str, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def _drain_body(self) -> None:
        """Consume an unread request body so keep-alive stays in sync.

        ``sendBeacon`` and friends may attach one even where none is needed.
        """
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return
        if 0 < length <= MAX_BODY_BYTES:
            self.rfile.read(length)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError("malformed Content-Length")
        if length <= 0:
            return {}
        if length > MAX_BODY_BYTES:
            raise ApiError("request body too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            return json.loads(self.rfile.read(length).decode("utf-8")) or {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ApiError("request body was not valid JSON")

    # -- routing --------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        self._route("GET")

    def do_HEAD(self) -> None:  # noqa: N802
        self._route("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._route("POST")

    def do_DELETE(self) -> None:  # noqa: N802
        self._route("DELETE")

    def _route(self, method: str) -> None:
        # Strip the query first, then percent-decode -- decoding earlier would let
        # an encoded "%3F" masquerade as a query separator.
        raw_path = self.path.split("?", 1)[0].split("#", 1)[0]
        path = urllib.parse.unquote(raw_path).rstrip("/") or "/"
        try:
            if method == "GET":
                self._route_get(path)
            elif method == "POST":
                self._route_post(path)
            elif method == "DELETE":
                self._route_delete(path)
        except ApiError as exc:
            self._send_json({"error": exc.message}, status=exc.status)
        except SeriesError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except BrokenPipeError:
            pass
        except Exception as exc:  # pragma: no cover - last-resort guard
            self._send_json({"error": f"unexpected server error: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _route_get(self, path: str) -> None:
        if path == "/":
            self._serve_static("index.html")
            return
        if path.startswith("/static/"):
            self._serve_static(path[len("/static/") :])
            return
        if path.startswith("/assets/"):
            self._serve_asset(path[len("/assets/") :])
            return
        if path.startswith("/pack/"):
            self._serve_pack_image(path[len("/pack/") :])
            return
        if path == "/api/bootstrap":
            self._send_json(self._bootstrap())
            return
        raise ApiError("not found", HTTPStatus.NOT_FOUND)

    def _route_post(self, path: str) -> None:
        if path == "/api/series":
            self._send_json(self._start_series(self._read_json()))
            return
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "series":
            series = self._require_series(parts[2])
            if parts[3] == "answer":
                self._send_json(self._answer(series, self._read_json()))
                return
            if parts[3] == "restart":
                self._drain_body()
                with self.store.lock:
                    series.restart()
                    series.next_problem()
                    series.resume()
                    self.store.save()
                self._send_json(self._series_payload(series))
                return
            if parts[3] in ("pause", "resume"):
                # Sent when the player leaves for HQ or the tab goes away, and
                # again when they come back to it.
                self._drain_body()
                with self.store.lock:
                    if parts[3] == "pause":
                        series.pause()
                    elif not series.is_mastered:
                        series.resume()
                    self.store.save()
                self._send_json(self._series_payload(series))
                return
        raise ApiError("not found", HTTPStatus.NOT_FOUND)

    def _route_delete(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "series":
            series_id = parts[2]
            self._validate_series_id(series_id)
            if not self.store.delete(series_id):
                raise ApiError("no such hunt", HTTPStatus.NOT_FOUND)
            self._send_json({"ok": True, "series": [s.summary() for s in self.store.all_series()]})
            return
        raise ApiError("not found", HTTPStatus.NOT_FOUND)

    # -- API handlers ---------------------------------------------------------

    def _bootstrap(self) -> dict[str, Any]:
        packs = packs_mod.list_packs(self.images_root)
        names = {pack["name"] for pack in packs}
        return {
            "game": {
                "id": self.game.id,
                "op": self.game.op,
                "title": self.game.title,
                "glyph": operation(self.game.op).glyph,
            },
            "series": [s.summary() for s in self.store.all_series()],
            "assets": assets_mod.scan(self.assets_dir),
            "packs": packs,
            "pack": self.default_pack if self.default_pack in names else None,
            "rules": {
                "mastery_target": MASTERY_TARGET,
                "correct_points": CORRECT_POINTS,
                "wrong_penalty": WRONG_PENALTY,
                "max_operand": MAX_OPERAND,
                "max_pool_size": MAX_POOL_SIZE,
                "timer_default_seconds": TIMER_DEFAULT_SECONDS,
                "timer_min_seconds": TIMER_MIN_SECONDS,
                "timer_max_seconds": TIMER_MAX_SECONDS,
            },
        }

    def _start_series(self, body: dict[str, Any]) -> dict[str, Any]:
        # Either side may be a range; a side pinned to one number just sends the
        # same value twice.  What the sides are called depends on the operation.
        labels = operation(self.game.op).labels
        m1 = _as_int(body.get("m1"), labels["m1"])
        m2 = _as_int(body.get("m2"), labels["m2"])
        s1 = _as_int(body.get("s1"), labels["s1"])
        s2 = _as_int(body.get("s2"), labels["s2"])
        allow_negative = bool(body.get("allow_negative"))
        restart = bool(body.get("restart"))

        with self.store.lock:
            series = self.store.get_or_create(m1, m2, s1, s2, allow_negative)
            # Timer settings are a launch choice, not part of the hunt's identity,
            # so they are re-applied every time the hunt is opened.
            series.timer_enabled = bool(body.get("timer_enabled", series.timer_enabled))
            if "timer_seconds" in body:
                series.timer_seconds = clamp_timer_seconds(body.get("timer_seconds"))
            # A finished hunt always starts over -- there is nothing left to resume.
            if restart or series.is_mastered:
                series.restart()
            series.next_problem()
            series.resume()  # the session clock runs while the hunt is open
            self.store.save()
            return self._series_payload(series)

    def _answer(self, series: Series, body: dict[str, Any]) -> dict[str, Any]:
        timed_out = bool(body.get("timed_out"))
        value = (
            None
            if timed_out
            else _as_int(body.get("answer"), "answer", low=-MAX_OPERAND, high=MAX_OPERAND)
        )
        elapsed = body.get("elapsed_ms")
        elapsed_ms = int(elapsed) if isinstance(elapsed, (int, float)) and elapsed >= 0 else None

        with self.store.lock:
            if series.current_key is None:
                series.next_problem()
            if series.current_key is None:
                raise ApiError("this hunt is already complete")
            result = series.answer(value, elapsed_ms=elapsed_ms, timed_out=timed_out)
            if not result["series_mastered"]:
                series.next_problem()
            self.store.save()
            payload = self._series_payload(series)
            payload["result"] = result
            return payload

    def _series_payload(self, series: Series) -> dict[str, Any]:
        detail = series.detail()
        problem = series.problems.get(series.current_key) if series.current_key else None
        detail["question"] = series.problem_view(problem) if problem else None
        return detail

    def _require_series(self, series_id: str) -> Series:
        self._validate_series_id(series_id)
        series = self.store.get(series_id)
        if series is None:
            raise ApiError("no such hunt", HTTPStatus.NOT_FOUND)
        return series

    @staticmethod
    def _validate_series_id(series_id: str) -> None:
        if not SERIES_ID_RE.match(series_id):
            raise ApiError("malformed hunt id", HTTPStatus.BAD_REQUEST)

    # -- static files ---------------------------------------------------------

    def _serve_static(self, relative: str) -> None:
        """Serve a front-end file: this game's skin wins, the shared copy backs it.

        Both are flat folders of files, so a path with a folder in it is asking
        for something that is not this game's to serve -- the other game's skin,
        say -- and is refused rather than resolved.
        """
        if "/" in relative:
            raise ApiError("not found", HTTPStatus.NOT_FOUND)
        for root in (WEB_DIR / self.game.web_dir, WEB_DIR):
            target = _safe_join(root, relative)
            if target is not None and target.is_file():
                content_type = STATIC_TYPES.get(target.suffix.lower(), "application/octet-stream")
                self._send(HTTPStatus.OK, target.read_bytes(), content_type)
                return
        raise ApiError("not found", HTTPStatus.NOT_FOUND)

    def _serve_pack_image(self, relative: str) -> None:
        """Serve ``/pack/<pack-name>/<file>`` out of the images root."""
        # Folder names may contain spaces or non-ASCII; _safe_join does the
        # containment check, so only the obviously bogus segments are rejected here.
        pack_name, _, file_name = relative.partition("/")
        if not file_name or pack_name in ("", ".", "..") or pack_name.startswith("."):
            raise ApiError("not found", HTTPStatus.NOT_FOUND)
        target = _safe_join(self.images_root, f"{pack_name}/{file_name}")
        if target is None or not packs_mod.is_image(target):
            raise ApiError("not found", HTTPStatus.NOT_FOUND)
        self._send(
            HTTPStatus.OK,
            target.read_bytes(),
            packs_mod.content_type(target),
            cache="public, max-age=3600",
        )

    def _serve_asset(self, relative: str) -> None:
        target = _safe_join(self.assets_dir, relative)
        if target is None or not target.is_file() or not assets_mod.is_allowed(target):
            raise ApiError("not found", HTTPStatus.NOT_FOUND)
        self._send(
            HTTPStatus.OK,
            target.read_bytes(),
            assets_mod.content_type(target),
            cache="public, max-age=300",
        )


def _safe_join(root: Path, relative: str) -> Path | None:
    """Resolve ``relative`` under ``root``, refusing anything that escapes it."""
    if not relative or relative.startswith("/") or ".." in relative.split("/"):
        return None
    try:
        candidate = (root / relative).resolve()
        candidate.relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    return candidate


def _as_int(value: Any, name: str, low: int = 0, high: int = MAX_OPERAND) -> int:
    if isinstance(value, bool) or value is None:
        raise ApiError(f"{name} is required")
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise ApiError(f"{name} is required")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ApiError(f"{name} must be a whole number")
    if not (low <= number <= high):
        raise ApiError(f"{name} must be between {low} and {high}")
    return number


def find_free_port(host: str, preferred: int, attempts: int = 25) -> int:
    for offset in range(attempts):
        port = preferred + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    raise SystemExit(f"Could not find a free port near {preferred}.")


def game_assets_dir(game: games_mod.Game, root: Path | None = None) -> Path:
    """Where this game looks for drop-in artwork, under the shared assets root."""
    base = Path(root) if root else ASSETS_DIR
    return base / game.assets_dir if game.assets_dir else base


def serve(
    host: str = "127.0.0.1",
    port: int | None = None,
    data_dir: Path | None = None,
    assets_dir: Path | None = None,
    images: Path | None = None,
    open_browser: bool = True,
    game: games_mod.Game | str | None = None,
) -> None:
    resolved_game = games_mod.get(game)
    store = Store(data_dir, game=resolved_game)
    resolved_assets = Path(assets_dir) if assets_dir else game_assets_dir(resolved_game)

    # --images points at one pack folder; its parent becomes the images root so
    # sibling packs can be switched to from the home screen without a restart.
    images_root, default_pack = IMAGES_DIR, None
    if images is not None:
        default_pack = packs_mod.resolve_selection(images)
        images_root = Path(images).expanduser().resolve().parent

    resolved_port = find_free_port(host, port if port is not None else resolved_game.port)
    httpd = HunterServer(
        (host, resolved_port), store, resolved_assets, images_root, default_pack, resolved_game
    )
    url = f"http://{host}:{resolved_port}/"

    found_assets = assets_mod.scan(resolved_assets)
    available = packs_mod.list_packs(images_root)
    selected = next((p for p in available if p["name"] == default_pack), None)

    print(f"\n  \033[95m✦ {resolved_game.title} ✦\033[0m")
    print(f"  {resolved_game.tagline}")
    print(f"  playing at  {url}")
    print(f"  progress    {store.path}")
    print(f"  artwork     {len(found_assets)} custom file(s) in {resolved_assets}")
    if selected:
        print(f"  images      '{selected['name']}' — {selected['count']} picture(s)")
    elif available:
        names = ", ".join(p["name"] for p in available)
        print(f"  images      none selected (pass --images {images_root}/<pack>); available: {names}")
    else:
        print(f"  images      no packs found in {images_root}")
    print("  press Ctrl+C to stop\n", flush=True)

    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Hunt paused. Progress saved. See you next time!\n")
    finally:
        httpd.shutdown()
        httpd.server_close()
