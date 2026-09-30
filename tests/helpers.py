"""Bits both server test modules need: a picture pack, and playing a hunt."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mathhunters.engine import operation  # noqa: E402

# The smallest valid PNG, used wherever a test needs a real image on disk.
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


def make_pack(images_root: Path, name: str, count: int) -> Path:
    pack = images_root / name
    pack.mkdir(parents=True, exist_ok=True)
    for i in range(1, count + 1):
        (pack / f"{i:02d}-pic.png").write_bytes(PNG_BYTES)
    return pack


def expected_answer(payload: dict, question: dict | None = None) -> int:
    """What the pending question works out to, under that hunt's operation."""
    question = question or payload["question"]
    assert question is not None, "no question was pending"
    return operation(payload["op"]).expected(question["left"], question["right"])


def answer_correctly(client, payload: dict, elapsed_ms: int = 500):
    """Answer the pending question of ``payload`` correctly."""
    return client(
        "POST",
        f"/api/series/{payload['id']}/answer",
        {"answer": expected_answer(payload), "elapsed_ms": elapsed_ms},
    )


def solve_series(client, payload: dict) -> dict:
    """Answer correctly until the series is mastered."""
    for _ in range(500):
        status, payload = answer_correctly(client, payload)
        assert status == 200
        if payload["result"]["series_mastered"]:
            return payload
    raise AssertionError("series never reached mastery")
