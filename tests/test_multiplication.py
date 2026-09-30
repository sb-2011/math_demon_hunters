"""The multiplication trainer: Math Jewel Hunters.

The scoring rules, the scheduler and the hunt clock are the same code for both
trainers and are covered in test_engine.py.  What is tested here is everything
the second game changes: how a pair works out and reads, what the forge will
accept, that the two games keep their hunts and their progress apart, and that
the browser is handed this game's skin.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from helpers import answer_correctly, solve_series  # noqa: E402
from mathhunters import games as games_mod  # noqa: E402
from mathhunters.engine import (  # noqa: E402
    MASTERY_TARGET,
    MAX_OPERAND,
    MAX_POOL_SIZE,
    MUL,
    SUB,
    Series,
    SeriesError,
    operation,
)
from mathhunters.storage import Store, default_data_dir  # noqa: E402


# --- the operation -----------------------------------------------------------


def test_a_pair_multiplies_and_reads_with_a_times_sign():
    series = Series.create(3, 3, 1, 10, op=MUL)
    problem = series.problems[3, 7]
    assert problem.expected == 21
    assert problem.text == "3 × 7"
    assert series.label == "3 × [1…10]"


def test_the_pool_is_every_pair_in_the_two_ranges():
    series = Series.create(2, 4, 0, 3, op=MUL)
    assert [p.key for p in series.ordered_problems()] == [
        (m, s) for m in (2, 3, 4) for s in (0, 1, 2, 3)
    ]
    assert series.pool_size == 12


def test_nothing_is_dropped_for_going_below_zero():
    """The subtraction rule has no business here: 2 × 9 is fine."""
    series = Series.create(2, 2, 0, 9, op=MUL)
    assert series.pool_size == 10
    assert series.problems[2, 9].expected == 18


def test_allowing_answers_below_zero_is_not_a_thing_here():
    series = Series.create(3, 3, 1, 4, allow_negative=True, op=MUL)
    assert series.allow_negative is False
    assert operation(MUL).supports_negative is False
    assert "-neg" not in series.id


def test_a_hunt_whose_answers_run_off_the_pad_is_refused():
    """The keypad holds three digits, so a bigger product is unanswerable."""
    with pytest.raises(SeriesError) as exc:
        Series.create(30, 30, 40, 40, op=MUL)
    assert str(MAX_OPERAND) in str(exc.value)

    # Right up to the limit is still allowed.
    assert Series.create(9, 9, 111, 111, op=MUL).problems[9, 111].expected == 999


def test_the_whole_times_table_is_too_big_for_one_hunt():
    with pytest.raises(SeriesError) as exc:
        Series.create(1, 10, 1, 10, op=MUL)
    assert f"keep it to {MAX_POOL_SIZE}" in str(exc.value)


def test_the_forge_complains_in_this_game_s_own_words():
    with pytest.raises(SeriesError) as exc:
        Series.create(5, 2, 1, 3, op=MUL)
    assert "groups" in str(exc.value)
    with pytest.raises(SeriesError) as exc:
        Series.create(2, 5, 3, 1, op=MUL)
    assert "group sizes" in str(exc.value)


# --- telling the two games apart ---------------------------------------------


def test_the_two_games_never_share_a_hunt_id():
    same_ranges = dict(m1=10, m2=10, s1=1, s2=9)
    subtraction = Series.create(**same_ranges, op=SUB)
    multiplication = Series.create(**same_ranges, op=MUL)
    assert subtraction.id != multiplication.id
    assert subtraction.id.startswith("r") and multiplication.id.startswith("m")


def test_a_saved_hunt_remembers_its_operation():
    series = Series.create(4, 4, 2, 6, op=MUL)
    series.answer(series.next_problem().expected)
    restored = Series.from_dict(series.to_dict())
    assert restored.op == MUL
    assert restored.id == series.id
    assert restored.problems[4, 5].expected == 20
    assert restored.problems[4, 5].text == "4 × 5"


def test_a_hunt_saved_before_there_were_two_games_is_a_subtraction_hunt():
    saved = Series.create(10, 10, 0, 9).to_dict()
    del saved["op"]
    restored = Series.from_dict(saved)
    assert restored.op == SUB
    assert restored.problems[10, 4].expected == 6


def test_each_game_saves_somewhere_of_its_own():
    subtraction, multiplication = games_mod.get("subtraction"), games_mod.get("multiplication")
    assert default_data_dir(subtraction) != default_data_dir(multiplication)
    assert subtraction.port != multiplication.port


def test_a_store_ignores_the_other_game_s_hunts(tmp_path):
    """Even pointed at one folder, neither game can lose the other's progress."""
    shared = tmp_path / "both"
    jewels = Store(shared, game="multiplication")
    jewels.get_or_create(3, 3, 1, 4)
    jewels.save()

    demons = Store(shared, game="subtraction")
    assert demons.all_series() == [], "a subtraction store must not adopt × hunts"
    demons.get_or_create(10, 10, 0, 4)
    demons.save()

    assert [s.id for s in Store(shared, game="multiplication").all_series()] == ["m3-3x1-4"]
    assert [s.id for s in Store(shared, game="subtraction").all_series()] == ["r10-10x0-4"]
    assert demons.path != jewels.path


def test_the_store_creates_hunts_for_its_own_game(tmp_path):
    store = Store(tmp_path / "data", game="multiplication")
    series = store.get_or_create(2, 5, 1, 6)
    assert series.op == MUL
    assert store.get_or_create(2, 5, 1, 6) is series


def test_an_unknown_game_is_rejected():
    with pytest.raises(ValueError, match="unknown game"):
        games_mod.get("division")


# --- over the wire -----------------------------------------------------------


def test_the_browser_is_handed_the_jewel_skin(jewel_client):
    status, content_type, body = jewel_client.raw("/")
    assert status == 200
    page = body.decode()
    assert "MATH JEWEL HUNTERS" in page
    assert "×" in page and "How many groups" in page
    assert 'id="negative-toggle"' not in page, "nothing here goes below zero"

    # The skin and the strategy come from this game's folder; app.js is shared.
    for path, needle in (
        ("/static/skin.css", "grp__shard"),
        ("/static/game.js", '"multiplication"'),
        ("/static/strategies.js", "equal-groups"),
        ("/static/app.js", "MathHunterGame"),
        ("/static/theme.css", "--aura"),
    ):
        status, _, body = jewel_client.raw(path)
        assert status == 200, path
        assert needle in body.decode(), path


def test_one_game_will_not_serve_the_other_s_skin(jewel_client):
    """Each server is one game's; the folder next door is not reachable."""
    assert jewel_client.raw("/static/subtraction/index.html")[0] == 404
    assert jewel_client.raw("/static/subtraction/game.js")[0] == 404


def test_bootstrap_names_the_game(jewel_client):
    status, data = jewel_client("GET", "/api/bootstrap")
    assert status == 200
    assert data["game"] == {
        "id": "multiplication",
        "op": "mul",
        "title": "MATH JEWEL HUNTERS",
        "glyph": "×",
    }


def test_a_times_table_hunt_can_be_forged_and_played(jewel_client):
    status, data = jewel_client("POST", "/api/series", {"m1": 3, "m2": 3, "s1": 1, "s2": 10})
    assert status == 200
    assert data["id"] == "m3-3x1-10"
    assert data["label"] == "3 × [1…10]"
    assert data["pool_size"] == 10
    assert data["question"]["left"] == 3

    question = data["question"]
    status, data = jewel_client(
        "POST",
        "/api/series/m3-3x1-10/answer",
        {"answer": question["left"] * question["right"], "elapsed_ms": 400},
    )
    assert data["result"]["correct"] is True
    assert data["result"]["delta"] == 1


def test_a_wrong_answer_reports_the_product(jewel_client):
    _, data = jewel_client("POST", "/api/series", {"m1": 4, "m2": 4, "s1": 2, "s2": 5})
    question = data["question"]
    _, data = jewel_client("POST", "/api/series/m4-4x2-5/answer", {"answer": 1})
    assert data["result"]["correct"] is False
    assert data["result"]["expected"] == question["left"] * question["right"]
    # And, as in the other trainer, the same problem stays up until it is right.
    assert data["question"]["text"] == question["text"]
    assert data["retrying"] is True


def test_a_hunt_runs_to_mastery_and_lands_in_history(jewel_client):
    _, data = jewel_client("POST", "/api/series", {"m1": 2, "m2": 3, "s1": 1, "s2": 4})
    final = solve_series(jewel_client, data)
    assert final["is_mastered"] is True
    assert final["mastered_count"] == final["pool_size"] == 8
    assert final["total_asked"] == 8 * MASTERY_TARGET

    _, boot = jewel_client("GET", "/api/bootstrap")
    assert [s["id"] for s in boot["series"]] == ["m2-3x1-4"]
    assert boot["series"][0]["op"] == "mul"


def test_the_forge_refuses_answers_the_pad_cannot_hold(jewel_client):
    status, data = jewel_client("POST", "/api/series", {"m1": 30, "m2": 30, "s1": 40, "s2": 40})
    assert status == 400
    assert "999" in data["error"]


def test_a_subtraction_hunt_id_is_not_found_here(jewel_client):
    """The games run separate servers over separate stores."""
    _, data = jewel_client("POST", "/api/series", {"m1": 3, "m2": 3, "s1": 1, "s2": 4})
    assert jewel_client("POST", "/api/series/r3-3x1-4/answer", {"answer": 1})[0] == 404


def test_progress_survives_a_restart_of_the_store(jewel_client, tmp_path):
    _, data = jewel_client("POST", "/api/series", {"m1": 6, "m2": 6, "s1": 1, "s2": 5})
    _, data = answer_correctly(jewel_client, data)
    assert data["points_earned"] == 1

    reopened = Store(tmp_path / "data", game="multiplication")
    series = reopened.get("m6-6x1-5")
    assert series is not None
    assert series.points_earned == 1
    assert series.op == MUL
