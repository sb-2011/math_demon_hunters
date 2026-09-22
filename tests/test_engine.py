"""Tests for scoring rules and the rotation scheduler."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mathhunters.engine import (  # noqa: E402
    MASTERY_TARGET,
    REVIEW_GAP,
    REVIEW_MIN_STALENESS,
    TIMER_DEFAULT_SECONDS,
    TIMER_MAX_SECONDS,
    TIMER_MIN_SECONDS,
    WRONG_PENALTY,
    Series,
    SeriesError,
    choose_problem,
    clamp_timer_seconds,
    eligible_reviews,
    problem_weight,
)


def make(fixed: int = 10, t1: int = 0, t2: int = 9, vary: str = "subtrahend") -> Series:
    return Series.create(fixed, t1, t2, vary)


def ask(series: Series, v: int, *, correct: bool = True, elapsed_ms: int | None = 1000) -> dict:
    """Force a specific problem to be pending, then answer it."""
    series.current_v = v
    value = series.expected(v)
    return series.answer(value if correct else value + 7, elapsed_ms=elapsed_ms)


# --- pool construction -------------------------------------------------------


def test_fixed_minuend_pool_sweeps_the_subtrahend():
    series = make(10, 0, 9, "subtrahend")
    assert series.pool_size == 10
    assert [series.text(v) for v in range(0, 3)] == ["10 − 0", "10 − 1", "10 − 2"]
    assert series.expected(4) == 6
    assert series.label == "10 − [0…9]"
    assert series.id == "s10-0-9"


def test_fixed_subtrahend_pool_sweeps_the_minuend():
    series = make(3, 5, 12, "minuend")
    assert series.pool_size == 8
    assert [series.text(v) for v in (5, 6, 12)] == ["5 − 3", "6 − 3", "12 − 3"]
    assert series.expected(12) == 9
    assert series.label == "[5…12] − 3"
    assert series.id == "m3-5-12"


def test_the_two_orientations_are_separate_hunts():
    assert make(4, 0, 9, "subtrahend").id != make(4, 0, 9, "minuend").id


def test_single_problem_pool_is_allowed():
    series = make(5, 3, 3)
    assert series.pool_size == 1
    problem = series.next_problem()
    assert problem is not None and problem.v == 3


@pytest.mark.parametrize(
    "fixed, t1, t2",
    [(10, 5, 4), (-1, 0, 9), (10, 0, 1000), (1000, 0, 9), (10, 0, 60)],
)
def test_invalid_series_are_rejected(fixed, t1, t2):
    with pytest.raises(SeriesError):
        Series.create(fixed, t1, t2)


def test_unknown_orientation_is_rejected():
    with pytest.raises(SeriesError):
        Series.create(10, 0, 9, "sideways")


# --- scoring -----------------------------------------------------------------


def test_correct_answer_adds_one_point():
    series = make()
    result = ask(series, 4)
    assert result["correct"] is True
    assert result["delta"] == 1
    assert result["points"] == 1


def test_wrong_answer_subtracts_two_points():
    series = make()
    for _ in range(MASTERY_TARGET):
        ask(series, 4)
    assert series.problems[4].points == MASTERY_TARGET

    result = ask(series, 4, correct=False)
    assert result["correct"] is False
    assert result["points"] == MASTERY_TARGET - 2
    assert result["delta"] == -2


def test_points_never_drop_below_zero():
    series = make()
    for _ in range(4):
        ask(series, 2, correct=False)
    assert series.problems[2].points == 0


def test_points_are_capped_at_the_mastery_target():
    series = make()
    for _ in range(12):
        ask(series, 3)
    assert series.problems[3].points == MASTERY_TARGET


def test_series_is_mastered_only_when_every_problem_is_at_target():
    series = make(10, 0, 2)
    result = None
    for v in (0, 1, 2):
        for _ in range(MASTERY_TARGET):
            result = ask(series, v)
    assert series.is_mastered
    assert result["series_mastered"] is True
    assert series.completions == 1


def test_the_mastery_target_is_three_points():
    assert MASTERY_TARGET == 3


def test_mastery_needs_a_full_score_on_each_problem_even_after_a_miss():
    series = make(10, 0, 1)
    for v in (0, 1):
        for _ in range(MASTERY_TARGET):
            ask(series, v)
    assert series.is_mastered

    ask(series, 0, correct=False)  # drops by the wrong-answer penalty
    assert not series.is_mastered
    for _ in range(WRONG_PENALTY - 1):
        ask(series, 0)
        assert not series.is_mastered
    ask(series, 0)
    assert series.is_mastered


def test_missing_a_mastered_problem_breaks_its_seal():
    series = make()
    for _ in range(MASTERY_TARGET):
        ask(series, 5)
    assert series.problems[5].mastered

    result = ask(series, 5, correct=False)
    assert result["seal_broken"] is True
    assert series.problems[5].points == MASTERY_TARGET - WRONG_PENALTY
    assert not series.problems[5].mastered


def test_answering_without_a_pending_problem_raises():
    series = make()
    series.current_v = None
    with pytest.raises(SeriesError):
        series.answer(4)


def test_streaks_track_consecutive_correct_answers():
    series = make()
    for v in (0, 1, 2):
        ask(series, v)
    assert series.streak == 3
    assert series.best_streak == 3

    ask(series, 3, correct=False)
    assert series.streak == 0
    assert series.best_streak == 3


def test_negative_results_are_supported_when_the_subtrahend_exceeds_the_minuend():
    series = make(3, 0, 6, "subtrahend")
    result = ask(series, 6)
    assert result["expected"] == -3
    assert result["correct"] is True


# --- countdown ---------------------------------------------------------------


def test_the_countdown_is_off_by_default_at_ten_seconds():
    series = make()
    assert series.timer_enabled is False
    assert series.timer_seconds == TIMER_DEFAULT_SECONDS == 10


def test_running_out_of_time_scores_like_a_wrong_answer():
    series = make()
    ask(series, 4)
    ask(series, 4)
    assert series.problems[4].points == 2

    series.current_v = 4
    result = series.answer(None, elapsed_ms=10_000, timed_out=True)
    assert result["correct"] is False
    assert result["timed_out"] is True
    assert result["delta"] == -2
    assert result["given"] is None
    assert result["expected"] == 6, "the correct answer is still reported, to show the kid"


def test_a_timeout_breaks_a_seal_and_queues_a_relapse():
    series = make()
    for _ in range(MASTERY_TARGET):
        ask(series, 5)

    series.current_v = 5
    result = series.answer(None, timed_out=True)
    assert result["seal_broken"] is True
    assert series.problems[5].relapse_due is not None
    assert series.streak == 0


def test_a_timeout_cannot_be_credited_as_correct():
    """Even if the right value is somehow supplied, the clock ran out."""
    series = make()
    series.current_v = 4
    result = series.answer(6, timed_out=True)
    assert result["correct"] is False


def test_an_answer_of_none_without_a_timeout_is_rejected():
    series = make()
    series.current_v = 4
    with pytest.raises(SeriesError):
        series.answer(None)


@pytest.mark.parametrize(
    "value, expected",
    [
        (10, 10),
        (1, TIMER_MIN_SECONDS),
        (9999, TIMER_MAX_SECONDS),
        ("30", 30),
        ("nonsense", TIMER_DEFAULT_SECONDS),
        (None, TIMER_DEFAULT_SECONDS),
    ],
)
def test_timer_seconds_are_clamped_into_range(value, expected):
    assert clamp_timer_seconds(value) == expected


def test_timer_settings_survive_a_save_and_reload():
    series = make()
    series.timer_enabled = True
    series.timer_seconds = 25
    restored = Series.from_dict(series.to_dict())
    assert restored.timer_enabled is True
    assert restored.timer_seconds == 25


# --- rotation / freshness ----------------------------------------------------


def play(series: Series, turns: int, rng: random.Random, miss_every: int = 0) -> list[int]:
    """Play ``turns`` rounds, returning the order problems were asked in."""
    seen = []
    for i in range(turns):
        problem = series.next_problem(rng=rng)
        if problem is None:  # series mastered
            break
        seen.append(problem.v)
        value = series.expected(problem.v)
        missed = miss_every and (i + 1) % miss_every == 0
        series.answer(value + 7 if missed else value)
    return seen


def test_every_problem_is_introduced_before_anything_repeats():
    for seed in range(8):
        series = make(10, 0, 9)
        seen = play(series, series.pool_size, random.Random(seed), miss_every=3)
        assert sorted(seen) == list(range(10)), "the intro sweep must cover the whole pool exactly once"


def test_a_problem_missed_during_the_intro_sweep_is_prioritised_right_after_it():
    series = make(10, 0, 9)
    rng = random.Random(4)
    for _ in range(series.pool_size):
        problem = series.next_problem(rng=rng)
        # Miss b=7, answer everything else correctly.
        series.answer(series.expected(problem.v) + (7 if problem.v == 7 else 0))

    assert series.problems[7].points == 0
    assert 7 in play(series, 4, rng), "the missed problem should come back immediately after the sweep"


def test_the_same_problem_is_not_asked_twice_in_a_row():
    series = make(10, 0, 9)
    # Miss every third answer so the hunt runs long without reaching mastery.
    seen = play(series, 120, random.Random(11), miss_every=3)
    assert len(seen) == 120
    assert all(a != b for a, b in zip(seen, seen[1:])), "a problem should cool down before repeating"


def test_a_missed_problem_comes_back_within_a_couple_of_turns():
    """The relapse queue must be a guarantee, not a lucky weighted draw."""
    for seed in range(20):
        series = make(10, 0, 9)
        rng = random.Random(seed)
        play(series, 10, rng)  # introduce everything

        ask(series, 6, correct=False)
        missed_turn = series.turn

        seen = play(series, 3, rng)
        assert 6 in seen, f"seed {seed}: a missed problem must return quickly, saw {seen}"
        assert series.problems[6].last_seen_turn >= missed_turn


def test_a_repeatedly_missed_problem_keeps_coming_back():
    series = make(10, 0, 9)
    rng = random.Random(1)
    play(series, 10, rng)

    for _ in range(3):
        ask(series, 2, correct=False)
        assert 2 in play(series, 3, rng)


def test_answering_a_relapsed_problem_correctly_clears_the_queue():
    series = make(10, 0, 9)
    play(series, 10, random.Random(1))
    ask(series, 2, correct=False)
    assert series.problems[2].relapse_due is not None
    ask(series, 2)
    assert series.problems[2].relapse_due is None


def test_weight_rises_with_distance_from_mastery():
    series = make(10, 0, 9)
    for problem in series.problems.values():
        problem.last_seen_turn = 0
    series.turn = 5
    series.problems[0].points = 0
    series.problems[1].points = MASTERY_TARGET
    assert problem_weight(series.problems[0], series.turn) > problem_weight(series.problems[1], series.turn)


def test_weight_rises_the_longer_a_problem_goes_unseen():
    series = make(10, 0, 9)
    series.turn = 30
    fresh, stale = series.problems[0], series.problems[1]
    fresh.points = stale.points = MASTERY_TARGET
    fresh.last_seen_turn = 29
    stale.last_seen_turn = 2
    assert problem_weight(stale, series.turn) > problem_weight(fresh, series.turn)


def test_unfinished_work_outranks_sealed_problems():
    """Sealed demons come back for freshness, but never ahead of unfinished ones."""
    series = make(10, 0, 4)
    for v in range(4):
        series.problems[v].points = MASTERY_TARGET
        series.problems[v].wrong = 1  # all of them were fumbled at some point
        series.problems[v].last_seen_turn = 0
    series.problems[4].points = 2
    series.problems[4].last_seen_turn = 0
    series.turn = 40
    series.last_review_turn = 40  # a review just happened, so none is due

    rng = random.Random(5)
    picks = [choose_problem(series, rng=rng).v for _ in range(200)]
    assert set(picks) == {4}, "with a review not due, only the unfinished problem is asked"


def test_struggled_problems_are_asked_more_often():
    series = make(10, 0, 9)
    for problem in series.problems.values():
        problem.points = 2
        problem.last_seen_turn = 10
    series.turn = 12
    series.problems[7].heat = 3.0
    assert problem_weight(series.problems[7], series.turn) > problem_weight(series.problems[1], series.turn)


def test_slow_correct_answers_keep_the_problem_in_rotation():
    slow = make()
    slow_result = ask(slow, 8, elapsed_ms=20_000)

    fast = make()
    ask(fast, 8, elapsed_ms=400)

    assert slow_result["slow"] is True
    assert slow.problems[8].heat > fast.problems[8].heat
    assert slow.problems[8].cooldown_until <= fast.problems[8].cooldown_until


def test_scheduler_always_returns_a_problem_even_when_all_are_cooling_down():
    series = make(10, 0, 1)
    for problem in series.problems.values():
        problem.cooldown_until = 999
        problem.last_seen_turn = 0
    assert choose_problem(series, rng=random.Random(1)) is not None


def test_a_finished_series_stops_handing_out_problems():
    series = make(10, 0, 1)
    for v in (0, 1):
        for _ in range(MASTERY_TARGET):
            ask(series, v)
    assert series.next_problem() is None


# --- a clean run must not be padded ------------------------------------------


def test_a_perfect_run_asks_each_problem_exactly_the_target_number_of_times():
    """Regression: getting everything right must not earn extra repetitions."""
    for seed in range(30):
        series = make(10, 0, 9)
        rng = random.Random(seed)
        asks = {v: 0 for v in series.problems}
        while not series.is_mastered:
            problem = series.next_problem(rng=rng)
            asks[problem.v] += 1
            series.answer(series.expected(problem.v))

        assert set(asks.values()) == {MASTERY_TARGET}, f"seed {seed}: {asks}"
        assert series.total_asked == series.pool_size * MASTERY_TARGET


def test_a_sealed_problem_with_a_clean_record_is_not_asked_again():
    series = make(10, 0, 9)
    for problem in series.problems.values():
        problem.points = 1
        problem.last_seen_turn = 20
    clean = series.problems[4]
    clean.points, clean.wrong, clean.last_seen_turn = MASTERY_TARGET, 0, 5
    series.turn = 40

    rng = random.Random(0)
    picks = {choose_problem(series, rng=rng).v for _ in range(300)}
    assert 4 not in picks, "a problem never missed does not need re-testing"


def test_a_sealed_problem_that_was_missed_does_come_back():
    """The freshness rule still applies where it matters."""
    series = make(10, 0, 9)
    for problem in series.problems.values():
        problem.points = 1
        problem.last_seen_turn = 20
    shaky = series.problems[3]
    shaky.points, shaky.wrong, shaky.last_seen_turn = MASTERY_TARGET, 2, 5
    series.turn = 40

    assert [p.v for p in eligible_reviews(series, series.ordered_problems())] == [3]
    rng = random.Random(0)
    assert 3 in {choose_problem(series, rng=rng).v for _ in range(50)}


def test_a_freshly_seen_sealed_problem_is_not_reviewed_immediately():
    series = make(10, 0, 9)
    for problem in series.problems.values():
        problem.points = 1
        problem.last_seen_turn = 20
    shaky = series.problems[3]
    shaky.points, shaky.wrong = MASTERY_TARGET, 2
    shaky.last_seen_turn = 39  # only one turn ago
    series.turn = 40
    assert eligible_reviews(series, series.ordered_problems()) == []


def test_reviews_are_rate_limited():
    series = make(10, 0, 9)
    rng = random.Random(4)
    review_turns = []
    guard = 0
    while not series.is_mastered and guard < 600:
        guard += 1
        problem = series.next_problem(rng=rng)
        if problem.mastered:
            review_turns.append(series.turn)
        series.answer(series.expected(problem.v) + (7 if rng.random() < 0.3 else 0))

    gaps = [b - a for a, b in zip(review_turns, review_turns[1:])]
    assert gaps, "this run should have contained some reviews"
    assert all(gap >= REVIEW_GAP for gap in gaps), gaps


def test_unfinished_problems_are_never_passed_over_for_a_sealed_one():
    """With work left to do, a sealed problem may only be picked as a review."""
    series = make(10, 0, 9)
    rng = random.Random(2)
    guard = 0
    while not series.is_mastered and guard < 600:
        guard += 1
        problem = series.next_problem(rng=rng)
        if problem.mastered:
            assert problem.wrong > 0, "only previously-missed problems are reviewed"
            assert series.turn - problem.last_seen_turn >= REVIEW_MIN_STALENESS
        series.answer(series.expected(problem.v) + (7 if rng.random() < 0.25 else 0))


# --- lifecycle ---------------------------------------------------------------


def test_restart_clears_points_but_keeps_lifetime_stats():
    series = make(10, 0, 2)
    for v in (0, 1, 2):
        for _ in range(MASTERY_TARGET):
            ask(series, v)
    assert series.is_mastered

    series.restart()
    assert series.points_earned == 0
    assert not series.is_mastered
    assert series.completions == 1
    assert series.total_asked == 3 * MASTERY_TARGET
    assert series.best_streak == 3 * MASTERY_TARGET


@pytest.mark.parametrize("vary", ["subtrahend", "minuend"])
def test_round_trip_serialisation_preserves_progress(vary):
    series = make(12, 3, 8, vary)
    rng = random.Random(2)
    play(series, 20, rng)
    series.next_problem(rng=rng)

    restored = Series.from_dict(series.to_dict())
    assert restored.id == series.id
    assert restored.vary == series.vary
    assert restored.points_earned == series.points_earned
    assert restored.current_v == series.current_v
    assert restored.turn == series.turn
    assert [p.to_dict() for p in restored.ordered_problems()] == [p.to_dict() for p in series.ordered_problems()]


def test_from_dict_rebuilds_a_pool_that_does_not_match_the_range():
    payload = make(10, 0, 4).to_dict()
    payload["problems"] = payload["problems"][:2]  # simulate a hand-edited file
    restored = Series.from_dict(payload)
    assert sorted(restored.problems) == [0, 1, 2, 3, 4]


def test_from_dict_defaults_to_the_fixed_minuend_orientation():
    payload = make(10, 0, 4).to_dict()
    del payload["vary"]
    assert Series.from_dict(payload).vary == "subtrahend"
