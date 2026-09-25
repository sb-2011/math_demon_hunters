"""End-to-end tests over the real HTTP server and the on-disk store."""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mathhunters import packs as packs_mod  # noqa: E402
from mathhunters.engine import MASTERY_TARGET, MAX_POOL_SIZE  # noqa: E402
from mathhunters.server import HunterServer, find_free_port  # noqa: E402
from mathhunters.storage import Store  # noqa: E402


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


@pytest.fixture()
def client(tmp_path):
    store = Store(tmp_path / "data")
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    images_root = tmp_path / "images"
    images_root.mkdir()
    port = find_free_port("127.0.0.1", 8900)
    httpd = HunterServer(("127.0.0.1", port), store, assets_dir, images_root, None)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

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
    try:
        yield call
    finally:
        httpd.shutdown()
        httpd.server_close()


def answer_correctly(client, payload: dict, elapsed_ms: int = 500):
    """Answer the pending question of ``payload`` correctly."""
    question = payload["question"]
    assert question is not None, "no question was pending"
    return client(
        "POST",
        f"/api/series/{payload['id']}/answer",
        {"answer": question["minuend"] - question["subtrahend"], "elapsed_ms": elapsed_ms},
    )


def solve_series(client, payload: dict) -> dict:
    """Answer correctly until the series is mastered."""
    for _ in range(500):
        status, payload = answer_correctly(client, payload)
        assert status == 200
        if payload["result"]["series_mastered"]:
            return payload
    raise AssertionError("series never reached mastery")


# --- static files ------------------------------------------------------------


def test_index_and_stylesheet_are_served(client):
    status, content_type, body = client.raw("/")
    assert status == 200
    assert content_type.startswith("text/html")
    assert b"MATH" in body

    status, content_type, body = client.raw("/static/theme.css")
    assert status == 200
    assert content_type.startswith("text/css")
    assert b"--magenta" in body


# --- bootstrap ---------------------------------------------------------------


def test_bootstrap_reports_rules_and_empty_history(client):
    status, data = client("GET", "/api/bootstrap")
    assert status == 200
    assert data["series"] == []
    assert data["rules"]["mastery_target"] == MASTERY_TARGET
    assert data["rules"]["max_pool_size"] == MAX_POOL_SIZE
    assert data["assets"] == {}


# --- starting a hunt ---------------------------------------------------------


def test_one_start_number_asks_from_the_pool(client):
    status, data = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 9})
    assert status == 200
    assert data["id"] == "r10-10x0-9"
    assert data["pool_size"] == 10
    assert data["question"]["minuend"] == 10
    assert 0 <= data["question"]["subtrahend"] <= 9
    assert {p["text"] for p in data["problems"]} == {f"10 − {v}" for v in range(10)}


def test_one_take_away_asks_from_the_pool(client):
    status, data = client("POST", "/api/series", {"m1": 5, "m2": 12, "s1": 3, "s2": 3})
    assert status == 200
    assert data["id"] == "r5-12x3-3"
    assert data["pool_size"] == 8
    assert data["question"]["subtrahend"] == 3
    assert 5 <= data["question"]["minuend"] <= 12
    assert {p["text"] for p in data["problems"]} == {f"{v} − 3" for v in range(5, 13)}


def test_a_range_on_both_sides_asks_from_the_whole_grid(client):
    status, data = client("POST", "/api/series", {"m1": 10, "m2": 12, "s1": 0, "s2": 4})
    assert status == 200
    assert data["id"] == "r10-12x0-4"
    assert data["label"] == "[10…12] − [0…4]"
    assert data["pool_size"] == 15
    assert {p["text"] for p in data["problems"]} == {
        f"{m} − {s}" for m in range(10, 13) for s in range(5)
    }


def test_pairs_below_zero_are_left_out_unless_asked_for(client):
    _, data = client("POST", "/api/series", {"m1": 0, "m2": 4, "s1": 0, "s2": 4})
    assert data["pool_size"] == 15
    assert all(p["minuend"] >= p["subtrahend"] for p in data["problems"])

    _, allowed = client(
        "POST", "/api/series", {"m1": 0, "m2": 4, "s1": 0, "s2": 4, "allow_negative": True}
    )
    assert allowed["pool_size"] == 25
    assert allowed["id"] == "r0-4x0-4-neg"
    assert allowed["id"] != data["id"], "the two pools are different hunts"


def test_the_two_orientations_are_stored_separately(client):
    client("POST", "/api/series", {"m1": 4, "m2": 4, "s1": 0, "s2": 6})
    client("POST", "/api/series", {"m1": 4, "m2": 6, "s1": 4, "s2": 4})
    _, boot = client("GET", "/api/bootstrap")
    assert {s["id"] for s in boot["series"]} == {"r4-4x0-6", "r4-6x4-4"}


# --- answering ---------------------------------------------------------------


def test_a_correct_answer_scores_and_advances(client):
    _, data = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 9})
    asked = data["question"]["text"]
    status, data = answer_correctly(client, data)
    assert status == 200
    assert data["result"]["correct"] is True
    assert data["result"]["delta"] == 1
    assert data["question"] is not None
    assert data["question"]["text"] != asked


def test_a_wrong_answer_reports_the_expected_value(client):
    _, data = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 9})
    question = data["question"]
    _, data = client("POST", "/api/series/r10-10x0-9/answer", {"answer": 999})
    assert data["result"]["correct"] is False
    assert data["result"]["expected"] == question["minuend"] - question["subtrahend"]
    assert data["result"]["points"] == 0


def test_absurd_answers_are_rejected_rather_than_scored(client):
    """The keypad caps at three digits; anything past that is a client bug."""
    client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 9})
    status, data = client("POST", "/api/series/r10-10x0-9/answer", {"answer": 12345})
    assert status == 400
    assert "error" in data


def test_negative_answers_are_accepted(client):
    _, data = client(
        "POST", "/api/series", {"m1": 2, "m2": 2, "s1": 0, "s2": 6, "allow_negative": True}
    )
    assert min(p["minuend"] - p["subtrahend"] for p in data["problems"]) == -4
    for _ in range(12):
        status, data = answer_correctly(client, data)
        assert status == 200
        assert data["result"]["correct"] is True


def test_the_client_cannot_be_told_the_answer_before_replying(client):
    """The pending problem lives on the server; the payload never leaks the result."""
    _, data = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 9})
    assert "expected" not in data["question"]
    assert "answer" not in json.dumps(data["question"])


# --- persistence -------------------------------------------------------------


def test_progress_survives_a_restart_of_the_store(client, tmp_path):
    _, data = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4})
    _, data = answer_correctly(client, data)
    earned = data["points_earned"]

    reopened = Store(tmp_path / "data")
    restored = reopened.get("r10-10x0-4")
    assert restored is not None
    assert restored.points_earned == earned


def test_a_profile_from_the_one_sided_app_still_loads_and_plays(client, tmp_path):
    """Hunts saved before both sides could be ranges keep their progress."""
    path = tmp_path / "old" / "progress.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "version": 1,
        "series": [
            {
                "fixed": 10, "t1": 0, "t2": 4, "vary": "subtrahend",
                "problems": [{"v": v, "points": 2, "asked": 2, "correct": 2} for v in range(5)],
                "completions": 1, "best_streak": 7,
            },
            {
                "fixed": 3, "t1": 5, "t2": 8, "vary": "minuend",
                "problems": [{"v": v, "points": 1} for v in range(5, 9)],
            },
        ],
    }))

    store = Store(tmp_path / "old")
    by_id = {s.id: s for s in store.all_series()}
    assert set(by_id) == {"r10-10x0-4-neg", "r5-8x3-3-neg"}

    carried_over = by_id["r10-10x0-4-neg"]
    assert carried_over.label == "10 − [0…4]"
    assert carried_over.points_earned == 10
    assert carried_over.best_streak == 7 and carried_over.completions == 1

    # And it is still a hunt the running app can open and answer.
    client.server.store = store
    status, data = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4, "allow_negative": True})
    assert status == 200 and data["id"] == "r10-10x0-4-neg"
    assert data["points_earned"] == 10
    assert answer_correctly(client, data)[0] == 200


def test_a_corrupt_profile_is_quarantined_rather_than_crashing(client, tmp_path):
    path = tmp_path / "data" / "progress.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json at all")

    store = Store(tmp_path / "data")
    assert store.all_series() == []
    assert path.with_suffix(".corrupt.json").exists()


# --- lifecycle ---------------------------------------------------------------


def test_mastering_a_series_reports_victory_and_lands_in_history(client):
    _, start = client("POST", "/api/series", {"m1": 6, "m2": 6, "s1": 0, "s2": 2})
    payload = solve_series(client, start)
    assert payload["result"]["series_mastered"] is True
    assert payload["is_mastered"] is True
    assert payload["mastered_count"] == 3
    assert payload["question"] is None

    _, boot = client("GET", "/api/bootstrap")
    assert boot["series"][0]["id"] == "r6-6x0-2"
    assert boot["series"][0]["completions"] == 1


def test_replaying_a_mastered_series_starts_it_over(client):
    _, start = client("POST", "/api/series", {"m1": 6, "m2": 6, "s1": 0, "s2": 2})
    solve_series(client, start)

    status, data = client("POST", "/api/series", {"m1": 6, "m2": 6, "s1": 0, "s2": 2})
    assert status == 200
    assert data["points_earned"] == 0
    assert data["is_mastered"] is False
    assert data["completions"] == 1
    assert data["question"] is not None


def test_resuming_an_unfinished_series_keeps_its_points(client):
    _, data = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4})
    _, data = answer_correctly(client, data)
    _, resumed = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4})
    assert resumed["points_earned"] == data["points_earned"] == 1


def test_restart_endpoint_resets_points(client):
    _, data = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4})
    answer_correctly(client, data)
    status, data = client("POST", "/api/series/r10-10x0-4/restart")
    assert status == 200
    assert data["points_earned"] == 0
    assert data["question"] is not None


def test_deleting_a_series_removes_it(client):
    client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4})
    status, data = client("DELETE", "/api/series/r10-10x0-4")
    assert status == 200
    assert data["series"] == []
    assert client("DELETE", "/api/series/r10-10x0-4")[0] == 404


# --- validation & safety -----------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"m1": 10, "m2": 10, "s1": 9, "s2": 0},   # take-aways out of order
        {"m1": 10, "m2": 5, "s1": 0, "s2": 9},    # start numbers out of order
        {"m1": -5, "m2": 5, "s1": 0, "s2": 9},    # below zero
        {"m1": 10, "m2": 10, "s1": 0, "s2": 1000},  # past the operand ceiling
        {"m1": 0, "m2": 60, "s1": 0, "s2": 60},   # far too many problems
        {"m1": "ten", "m2": 10, "s1": 0, "s2": 9},
        {"s1": 0, "s2": 9},                       # no start numbers at all
        {"m1": 0, "m2": 3, "s1": 5, "s2": 9},     # every pair would go below zero
    ],
)
def test_invalid_series_requests_are_rejected(client, body):
    status, data = client("POST", "/api/series", body)
    assert status == 400
    assert "error" in data


def test_unknown_series_and_routes_return_404(client):
    assert client("POST", "/api/series/r99-99x0-9/answer", {"answer": 1})[0] == 404
    assert client("GET", "/api/nope")[0] == 404
    assert client("POST", "/api/series/bad-id/answer", {"answer": 1})[0] == 400


def test_asset_route_only_serves_known_slots(client):
    (client.assets_dir / "demon.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (client.assets_dir / "secret.txt").write_text("nope")

    _, data = client("GET", "/api/bootstrap")
    assert data["assets"]["demon"] == "/assets/demon.png"
    assert client.raw("/assets/demon.png")[0] == 200
    assert client.raw("/assets/secret.txt")[0] == 404


def test_path_traversal_is_blocked(client):
    assert client.raw("/assets/../../etc/passwd")[0] in (400, 404)
    assert client.raw("/static/../storage.py")[0] in (400, 404)
    assert client.raw("/pack/../../../etc/passwd")[0] in (400, 404)


# --- countdown ---------------------------------------------------------------


def test_the_countdown_is_off_unless_asked_for(client):
    _, data = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4})
    assert data["timer_enabled"] is False
    assert data["timer_seconds"] == 10

    _, boot = client("GET", "/api/bootstrap")
    assert boot["rules"]["timer_default_seconds"] == 10
    assert boot["rules"]["timer_min_seconds"] == 3
    assert boot["rules"]["timer_max_seconds"] == 120


def test_the_countdown_can_be_enabled_and_timed(client):
    _, data = client(
        "POST",
        "/api/series",
        {"m1": 10, "m2": 10, "s1": 0, "s2": 4, "timer_enabled": True, "timer_seconds": 20},
    )
    assert data["timer_enabled"] is True
    assert data["timer_seconds"] == 20


def test_out_of_range_countdowns_are_clamped_not_rejected(client):
    _, data = client(
        "POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4, "timer_enabled": True, "timer_seconds": 9999}
    )
    assert data["timer_seconds"] == 120


def test_timer_settings_are_reapplied_when_a_hunt_is_reopened(client):
    client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4, "timer_enabled": True, "timer_seconds": 15})
    _, data = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4, "timer_enabled": False})
    assert data["timer_enabled"] is False
    assert data["timer_seconds"] == 15, "the duration is remembered even when switched off"


def test_a_timeout_is_scored_as_a_miss(client):
    _, data = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4, "timer_enabled": True})
    question = data["question"]
    status, data = client("POST", "/api/series/r10-10x0-4/answer", {"timed_out": True, "elapsed_ms": 10_000})
    assert status == 200
    assert data["result"]["correct"] is False
    assert data["result"]["timed_out"] is True
    assert data["result"]["expected"] == question["minuend"] - question["subtrahend"]
    assert data["question"] is not None


def test_a_timeout_needs_no_answer_field(client):
    client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4})
    assert client("POST", "/api/series/r10-10x0-4/answer", {"timed_out": True})[0] == 200
    assert client("POST", "/api/series/r10-10x0-4/answer", {})[0] == 400


# --- session clock -----------------------------------------------------------


def test_opening_a_hunt_starts_its_clock(client):
    _, data = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4})
    assert data["running"] is True
    assert data["elapsed_ms"] >= 0


def test_going_back_to_hq_pauses_the_clock(client):
    _, data = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4})
    answer_correctly(client, data)
    time.sleep(0.2)

    status, paused = client("POST", "/api/series/r10-10x0-4/pause")
    assert status == 200
    assert paused["running"] is False
    banked = paused["elapsed_ms"]
    assert banked > 0

    time.sleep(0.3)  # sitting at HQ
    _, boot = client("GET", "/api/bootstrap")
    assert boot["series"][0]["elapsed_ms"] == banked, "a paused hunt must not tick"


def test_resuming_a_hunt_continues_its_clock(client):
    _, data = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4})
    time.sleep(0.2)
    _, paused = client("POST", "/api/series/r10-10x0-4/pause")
    banked = paused["elapsed_ms"]

    time.sleep(0.3)  # away
    _, resumed = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4})
    assert resumed["running"] is True
    assert resumed["elapsed_ms"] >= banked
    assert resumed["elapsed_ms"] < banked + 250, "the time spent at HQ must not be counted"


def test_the_resume_endpoint_restarts_the_clock(client):
    _, data = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4})
    client("POST", "/api/series/r10-10x0-4/pause")
    status, resumed = client("POST", "/api/series/r10-10x0-4/resume")
    assert status == 200
    assert resumed["running"] is True


def test_the_clock_survives_the_app_being_closed(client, tmp_path):
    _, data = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4})
    time.sleep(0.2)
    _, paused = client("POST", "/api/series/r10-10x0-4/pause")

    reopened = Store(tmp_path / "data")
    restored = reopened.get("r10-10x0-4")
    assert restored is not None
    assert restored.elapsed_ms == paused["elapsed_ms"]
    assert restored.running is False, "a reloaded hunt is never mid-session"


def test_a_mastered_hunt_stops_and_reports_its_time(client):
    _, start = client("POST", "/api/series", {"m1": 6, "m2": 6, "s1": 0, "s2": 2})
    payload = solve_series(client, start)
    assert payload["running"] is False
    frozen = payload["elapsed_ms"]

    time.sleep(0.25)
    _, boot = client("GET", "/api/bootstrap")
    assert boot["series"][0]["elapsed_ms"] == frozen


def test_resume_does_not_restart_a_finished_hunt(client):
    _, start = client("POST", "/api/series", {"m1": 6, "m2": 6, "s1": 0, "s2": 2})
    solve_series(client, start)
    _, data = client("POST", "/api/series/r6-6x0-2/resume")
    assert data["running"] is False


def test_replaying_a_hunt_resets_its_clock(client):
    _, start = client("POST", "/api/series", {"m1": 6, "m2": 6, "s1": 0, "s2": 2})
    time.sleep(0.2)
    solve_series(client, start)

    _, replay = client("POST", "/api/series", {"m1": 6, "m2": 6, "s1": 0, "s2": 2})
    assert replay["elapsed_ms"] < 100, "a replay starts a fresh clock"
    assert replay["running"] is True


def test_pause_tolerates_a_body_from_sendbeacon(client):
    """navigator.sendBeacon may attach a payload; the connection must survive."""
    client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 4})
    status, data = client("POST", "/api/series/r10-10x0-4/pause", {"ignored": "beacon"})
    assert status == 200
    assert data["running"] is False
    # The next request on the same server must still work.
    assert client("GET", "/api/bootstrap")[0] == 200


# --- image packs -------------------------------------------------------------


def test_no_packs_are_reported_when_the_images_folder_is_empty(client):
    _, data = client("GET", "/api/bootstrap")
    assert data["packs"] == []
    assert data["pack"] is None


def test_packs_are_listed_with_their_images(client):
    make_pack(client.images_root, "kpop-demon-hunters", 3)
    make_pack(client.images_root, "space", 2)

    _, data = client("GET", "/api/bootstrap")
    by_name = {p["name"]: p for p in data["packs"]}
    assert set(by_name) == {"kpop-demon-hunters", "space"}
    assert by_name["kpop-demon-hunters"]["count"] == 3
    assert by_name["kpop-demon-hunters"]["images"] == [
        f"/pack/kpop-demon-hunters/{i:02d}-pic.png" for i in (1, 2, 3)
    ]


def test_pack_images_are_served(client):
    make_pack(client.images_root, "space", 1)
    status, content_type, body = client.raw("/pack/space/01-pic.png")
    assert status == 200
    assert content_type == "image/png"
    assert body == PNG_BYTES


def test_folders_without_images_are_not_offered_as_packs(client):
    (client.images_root / "empty").mkdir()
    (client.images_root / "notes").mkdir()
    (client.images_root / "notes" / "README.md").write_text("hi")

    _, data = client("GET", "/api/bootstrap")
    assert data["packs"] == []


def test_non_image_files_in_a_pack_are_neither_listed_nor_served(client):
    pack = make_pack(client.images_root, "space", 1)
    (pack / "notes.txt").write_text("secret")

    _, data = client("GET", "/api/bootstrap")
    assert data["packs"][0]["count"] == 1
    assert client.raw("/pack/space/notes.txt")[0] == 404


def test_the_launch_selected_pack_is_reported(client):
    make_pack(client.images_root, "kpop-demon-hunters", 2)
    client.server.default_pack = "kpop-demon-hunters"
    _, data = client("GET", "/api/bootstrap")
    assert data["pack"] == "kpop-demon-hunters"


def test_a_selected_pack_that_no_longer_exists_is_ignored(client):
    client.server.default_pack = "deleted-pack"
    _, data = client("GET", "/api/bootstrap")
    assert data["pack"] is None


AWKWARD_NAMES = [
    "Huntrix stage.jpg",       # space
    "saja-boys (1).png",       # parentheses
    "demon_king#2.png",        # would be read as a URL fragment
    "derpy&sussie.png",        # ampersand
    "rumi's sword.png",        # apostrophe
    "골든.png",                 # non-ASCII
    "poster.JPG",              # uppercase extension
]


def test_pictures_with_awkward_filenames_are_listed_and_served(client):
    """Regression: names like these come straight off a browser save and used
    to 404, so those problems showed no picture."""
    pack = client.images_root / "realistic"
    pack.mkdir()
    for name in AWKWARD_NAMES:
        (pack / name).write_bytes(PNG_BYTES)

    _, data = client("GET", "/api/bootstrap")
    urls = data["packs"][0]["images"]
    assert len(urls) == len(AWKWARD_NAMES)

    for url in urls:
        # The advertised URL must be safe to put in an href verbatim.
        assert " " not in url and "#" not in url
        status, _, body = client.raw(url)
        assert status == 200, f"{url} did not load"
        assert body == PNG_BYTES


def test_every_problem_in_a_pool_gets_a_working_picture(client):
    """End to end: no problem should be left without an image."""
    pack = client.images_root / "realistic"
    pack.mkdir()
    for name in AWKWARD_NAMES:
        (pack / name).write_bytes(PNG_BYTES)

    _, boot = client("GET", "/api/bootstrap")
    images = boot["packs"][0]["images"]
    _, series = client("POST", "/api/series", {"m1": 10, "m2": 10, "s1": 0, "s2": 9})

    # The client binds problem i to images[i % len(images)].
    for index, problem in enumerate(series["problems"]):
        url = images[index % len(images)]
        assert client.raw(url)[0] == 200, f"{problem['text']} -> {url}"


def test_percent_encoded_traversal_is_still_blocked(client):
    make_pack(client.images_root, "space", 1)
    assert client.raw("/pack/space/%2e%2e%2f%2e%2e%2fstorage.py")[0] in (400, 404)
    assert client.raw("/pack/%2e%2e/%2e%2e/etc/passwd")[0] in (400, 404)
    assert client.raw("/static/%2e%2e/storage.py")[0] in (400, 404)


def test_image_url_encoding():
    assert packs_mod.image_url("my pack", "a b#c.png") == "/pack/my%20pack/a%20b%23c.png"
    assert packs_mod.image_url("p", "골든.png").startswith("/pack/p/%EA%B3%A8")


def test_resolving_the_images_flag(tmp_path):
    root = tmp_path / "images"
    pack = make_pack(root, "kpop-demon-hunters", 2)

    assert packs_mod.resolve_selection(pack) == "kpop-demon-hunters"
    assert packs_mod.resolve_selection(None) is None

    with pytest.raises(FileNotFoundError):
        packs_mod.resolve_selection(root / "nope")

    (root / "empty").mkdir()
    with pytest.raises(ValueError):
        packs_mod.resolve_selection(root / "empty")
