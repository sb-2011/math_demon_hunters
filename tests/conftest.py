"""A live server for the tests to talk to — one fixture per trainer."""

from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mathhunters.server import HunterServer, find_free_port  # noqa: E402
from mathhunters.storage import Store  # noqa: E402


def _serve(tmp_path: Path, game: str, port_hint: int):
    """A running server for ``game``, plus a callable that talks to it.

    The returned ``call(method, path, body)`` gives back ``(status, payload)``;
    ``call.raw(path)`` gives back ``(status, content_type, bytes)`` for the
    static files.  Everything it touches lives under ``tmp_path``.
    """
    store = Store(tmp_path / "data", game=game)
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(exist_ok=True)
    images_root = tmp_path / "images"
    images_root.mkdir(exist_ok=True)
    port = find_free_port("127.0.0.1", port_hint)
    httpd = HunterServer(("127.0.0.1", port), store, assets_dir, images_root, None, game)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    base = f"http://127.0.0.1:{port}"

    def call(method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(base + path, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return exc.code, json.loads(raw) if raw else None

    def raw(path: str):
        try:
            with urllib.request.urlopen(base + path, timeout=5) as response:
                return response.status, response.headers.get("Content-Type", ""), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers.get("Content-Type", ""), exc.read()

    call.store = store  # type: ignore[attr-defined]
    call.assets_dir = assets_dir  # type: ignore[attr-defined]
    call.images_root = images_root  # type: ignore[attr-defined]
    call.server = httpd  # type: ignore[attr-defined]
    call.raw = raw  # type: ignore[attr-defined]
    return call, httpd


@pytest.fixture()
def client(tmp_path):
    """The subtraction trainer: Math Demon Hunters."""
    call, httpd = _serve(tmp_path, "subtraction", 8900)
    try:
        yield call
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture()
def jewel_client(tmp_path):
    """The multiplication trainer: Math Jewel Hunters."""
    call, httpd = _serve(tmp_path, "multiplication", 8940)
    try:
        yield call
    finally:
        httpd.shutdown()
        httpd.server_close()
