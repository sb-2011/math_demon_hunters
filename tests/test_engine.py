"""Tests for scoring rules and the rotation scheduler."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mathhunters import engine  # noqa: E402
from mathhunters.engine import (  # noqa: E402
    MASTERY_TARGET,
    MAX_POOL_SIZE,
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
    migrate_series,
    problem_weight,
)


class _FakeClock:
    """Stand-in for ``time.time`` so clock tests are exact and instant."""

    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make(m1: int = 10, m2: int = 10, s1: int = 0, s2: int = 9, allow_negative: bool = False) -> Series:
    """A hunt — by default the classic one-start-number shape, 10 − [0…9]."""
    return Series.create(m1, m2, s1, s2, allow_negative)


def ask(series: Series, key: tuple[int, int], *, correct: bool = True, elapsed_ms: int | None = 1000) -> dict:
    """Force a specific problem to be pending, then answer it."""
    series.current_key = key
    value = series.expected(key)
    return series.answer(value if correct else value + 7, elapsed_ms=elapsed_ms)


# --- pool construction -------------------------------------------------------


def test_one_start_number_sweeps_the_take_aways():
    series = make(10, 10, 0, 9)
    assert series.pool_size == 10
    assert [series.text((10, s)) for s in range(0, 3)] == ["10 − 0", "10 − 1", "10 − 2"]
    assert series.expected((10, 4)) == 6
    assert series.label == "10 − [0…9]"
    assert series.id == "r10-10x0-9"


def test_one_take_away_sweeps_the_start_numbers():
    series = make(5, 12, 3, 3)
    assert series.pool_size == 8
    assert [series.text((m, 3)) for m in (5, 6, 12)] == ["5 − 3", "6 − 3", "12 − 3"]
    assert series.expected((12, 3)) == 9
    assert series.label == "[5…12] − 3"
    assert series.id == "r5-12x3-3"


def test_both_sides_can_be_ranges():
    series = make(10, 12, 0, 4)
    assert series.pool_size == 3 * 5
    assert series.label == "[10…12] − [0…4]"
    assert series.id == "r10-12x0-4"
    assert [p.text for p in series.ordered_problems()][:6] == [
        "10 − 0", "10 − 1", "10 − 2", "10 − 3", "10 − 4", "11 − 0",
    ]


def test_a_single_pair_is_a_pool_of_one():
    series = make(9, 9, 4, 4)
    assert series.pool_size == 1
    assert series.label == "9 − 4"
    problem = series.next_problem()
    assert problem is not None and problem.key == (9, 4)


def test_pairs_that_go_below_zero_are_left_out():
    series = make(3, 5, 0, 9)
    assert [p.text for p in series.ordered_problems()] == [
        "3 − 0", "3 − 1", "3 − 2", "3 − 3",
        "4 − 0", "4 − 1", "4 − 2", "4 − 3", "4 − 4",
        "5 − 0", "5 − 1", "5 − 2", "5 − 3", "5 − 4", "5 − 5",
    ]
    assert all(p.expected >= 0 for p in series.problems.values())


def test_below_zero_pairs_are_kept_when_asked_for():
    series = make(3, 3, 0, 9, allow_negative=True)
    assert series.pool_size == 10
    assert series.problems[3, 9].expected == -6
    assert series.id == "r3-3x0-9-neg"


def test_the_below_zero_setting_makes_a_separate_hunt():
    assert make(3, 5, 0, 9).id != make(3, 5, 0, 9, allow_negative=True).id


def test_the_cap_counts_the_pairs_that_survive_the_filter():
    assert make(0, 7, 0, 7).pool_size == 36  # of 64 pairs, only 36 stay at or above zero
    assert make(0, 7, 0, 7, allow_negative=True).pool_size == MAX_POOL_SIZE
    with pytest.raises(SeriesError, match="64 or fewer"):
        make(0, 8, 0, 8, allow_negative=True)


@pytest.mark.parametrize(
    "ranges",
    [
        (10, 5, 0, 9),      # start numbers out of order
        (10, 10, 9, 0),     # take-aways out of order
        (-1, 5, 0, 9),      # below zero
        (10, 10, 0, 1000),  # past the operand ceiling
        (0, 40, 0, 40),     # far too many problems
        (0, 3, 5, 9),       # every pair would go below zero
    ],
)
def test_invalid_series_are_rejected(ranges):
    with pytest.raises(SeriesError):
        Series.create(*ranges)


# --- scoring -----------------------------------------------------------------


def test_correct_answer_adds_one_point():
    series = make()
    result = ask(series, (10, 4))
    assert result["correct"] is True
    assert result["delta"] == 1
    assert result["points"] == 1


def test_wrong_answer_subtracts_two_points():
    series = make()
    for _ in range(MASTERY_TARGET):
        ask(series, (10, 4))
    assert series.problems[10, 4].points == MASTERY_TARGET

    result = ask(series, (10, 4), correct=False)
    assert result["correct"] is False
    assert result["points"] == MASTERY_TARGET - 2
    assert result["delta"] == -2


def test_points_never_drop_below_zero():
    series = make()
    for _ in range(4):
        ask(series, (10, 2), correct=False)
    assert series.problems[10, 2].points == 0


def test_points_are_capped_at_the_mastery_target():
    series = make()
    for _ in range(12):
        ask(series, (10, 3))
    assert series.problems[10, 3].points == MASTERY_TARGET


def test_series_is_mastered_only_when_every_problem_is_at_target():
    series = make(10, 10, 0, 2)
    result = None
    for v in (0, 1, 2):
        for _ in range(MASTERY_TARGET):
            result = ask(series, (10, v))
    assert series.is_mastered
    assert result["series_mastered"] is True
    assert series.completions == 1


def test_the_mastery_target_is_three_points():
    assert MASTERY_TARGET == 3


def test_mastery_needs_a_full_score_on_each_problem_even_after_a_miss():
    series = make(10, 10, 0, 1)
    for v in (0, 1):
        for _ in range(MASTERY_TARGET):
            ask(series, (10, v))
    assert series.is_mastered

    ask(series, (10, 0), correct=False)  # drops by the wrong-answer penalty
    assert not series.is_mastered
    for _ in range(WRONG_PENALTY - 1):
        ask(series, (10, 0))
        assert not series.is_mastered
    ask(series, (10, 0))
    assert series.is_mastered


def test_missing_a_mastered_problem_breaks_its_seal():
    series = make()
    for _ in range(MASTERY_TARGET):
        ask(series, (10, 5))
    assert series.problems[10, 5].mastered

    result = ask(series, (10, 5), correct=False)
    assert result["seal_broken"] is True
    assert series.problems[10, 5].points == MASTERY_TARGET - WRONG_PENALTY
    assert not series.problems[10, 5].mastered


def test_answering_without_a_pending_problem_raises():
    series = make()
    series.current_key = None
    with pytest.raises(SeriesError):
        series.answer(4)


def test_streaks_track_consecutive_correct_answers():
    series = make()
    for v in (0, 1, 2):
        ask(series, (10, v))
    assert series.streak == 3
    assert series.best_streak == 3

    ask(series, (10, 3), correct=False)
    assert series.streak == 0
    assert series.best_streak == 3


def test_negative_results_are_supported_when_the_take_away_is_bigger():
    series = make(3, 3, 0, 6, allow_negative=True)
    result = ask(series, (3, 6))
    assert result["expected"] == -3
    assert result["correct"] is True


# --- countdown ---------------------------------------------------------------


def test_the_countdown_is_off_by_default_at_ten_seconds():
    series = make()
    assert series.timer_enabled is False
    assert series.timer_seconds == TIMER_DEFAULT_SECONDS == 10


def test_running_out_of_time_scores_like_a_wrong_answer():
    series = make()
    ask(series, (10, 4))
    ask(series, (10, 4))
    assert series.problems[10, 4].points == 2

    series.current_key = (10, 4)
    result = series.answer(None, elapsed_ms=10_000, timed_out=True)
    assert result["correct"] is False
    assert result["timed_out"] is True
    assert result["delta"] == -2
    assert result["given"] is None
    assert result["expected"] == 6, "the correct answer is still reported, to show the kid"


def test_a_timeout_breaks_a_seal_and_queues_a_relapse():
    series = make()
    for _ in range(MASTERY_TARGET):
        ask(series, (10, 5))

    series.current_key = (10, 5)
    result = series.answer(None, timed_out=True)
    assert result["seal_broken"] is True
    assert series.problems[10, 5].relapse_due is not None
    assert series.streak == 0


def test_a_timeout_cannot_be_credited_as_correct():
    """Even if the right value is somehow supplied, the clock ran out."""
    series = make()
    series.current_key = (10, 4)
    result = series.answer(6, timed_out=True)
    assert result["correct"] is False


def test_an_answer_of_none_without_a_timeout_is_rejected():
    series = make()
    series.current_key = (10, 4)
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


# --- session clock -----------------------------------------------------------


def test_a_new_hunt_starts_with_a_stopped_clock_at_zero():
    series = make()
    assert series.elapsed_ms == 0
    assert series.running is False


def test_the_clock_accumulates_while_running(monkeypatch):
    series = make()
    clock = _FakeClock(1000.0)
    monkeypatch.setattr(engine.time, "time", clock)

    series.resume()
    clock.advance(4.0)
    assert 3900 <= series.elapsed_ms_now() <= 4100

    series.pause()
    assert 3900 <= series.elapsed_ms <= 4100
    assert series.running is False


def test_a_paused_clock_does_not_advance(monkeypatch):
    series = make()
    clock = _FakeClock(1000.0)
    monkeypatch.setattr(engine.time, "time", clock)

    series.resume()
    clock.advance(5.0)
    series.pause()
    banked = series.elapsed_ms

    clock.advance(600.0)  # ten minutes away at HQ
    assert series.elapsed_ms_now() == banked


def test_resuming_continues_from_where_it_stopped(monkeypatch):
    series = make()
    clock = _FakeClock(1000.0)
    monkeypatch.setattr(engine.time, "time", clock)

    series.resume()
    clock.advance(6.0)
    series.pause()

    clock.advance(300.0)  # time at HQ is not counted
    series.resume()
    clock.advance(4.0)
    series.pause()

    assert 9900 <= series.elapsed_ms <= 10_100, "6s + 4s of play, not the gap between"


def test_pausing_an_already_paused_hunt_is_harmless(monkeypatch):
    series = make()
    clock = _FakeClock(1000.0)
    monkeypatch.setattr(engine.time, "time", clock)

    series.resume()
    clock.advance(3.0)
    series.pause()
    banked = series.elapsed_ms
    series.pause()
    series.pause()
    assert series.elapsed_ms == banked


def test_a_single_stretch_is_capped(monkeypatch):
    """A browser closed without going back to HQ must not bank hours."""
    series = make()
    clock = _FakeClock(1000.0)
    monkeypatch.setattr(engine.time, "time", clock)

    series.resume()
    clock.advance(10 * 3600)  # left running overnight
    series.pause()
    assert series.elapsed_ms == engine.MAX_CREDITED_STRETCH_S * 1000


def test_finishing_a_hunt_stops_the_clock(monkeypatch):
    series = make(10, 10, 0, 1)
    clock = _FakeClock(1000.0)
    monkeypatch.setattr(engine.time, "time", clock)
    series.resume()

    for v in (0, 1):
        for _ in range(MASTERY_TARGET):
            clock.advance(2.0)
            ask(series, (10, v))

    assert series.is_mastered
    assert series.running is False, "a finished hunt should not keep counting"
    frozen = series.elapsed_ms
    clock.advance(1000.0)
    assert series.elapsed_ms_now() == frozen


def test_the_clock_survives_a_save_and_reload_but_loads_paused(monkeypatch):
    series = make()
    clock = _FakeClock(1000.0)
    monkeypatch.setattr(engine.time, "time", clock)

    series.resume()
    clock.advance(7.0)
    # Saved mid-hunt, while still running.
    restored = Series.from_dict(series.to_dict())

    assert 6900 <= restored.elapsed_ms <= 7100, "time played is kept"
    assert restored.running is False, "a hunt cannot be running while the app is closed"


def test_replaying_a_hunt_resets_its_clock(monkeypatch):
    series = make()
    clock = _FakeClock(1000.0)
    monkeypatch.setattr(engine.time, "time", clock)

    series.resume()
    clock.advance(30.0)
    series.pause()
    assert series.elapsed_ms > 0

    series.restart()
    assert series.elapsed_ms == 0
    assert series.running is False


# --- rotation / freshness ----------------------------------------------------


def play(series: Series, turns: int, rng: random.Random, miss_every: int = 0) -> list[tuple[int, int]]:
    """Play ``turns`` rounds, returning the order problems were asked in."""
    seen = []
    for i in range(turns):
        problem = series.next_problem(rng=rng)
        if problem is None:  # series mastered
            break
        seen.append(problem.key)
        value = series.expected(problem.key)
        missed = miss_every and (i + 1) % miss_every == 0
        series.answer(value + 7 if missed else value)
    return seen


def test_every_problem_is_introduced_before_anything_repeats():
    for seed in range(8):
        series = make(10, 10, 0, 9)
        seen = play(series, series.pool_size, random.Random(seed), miss_every=3)
        assert sorted(seen) == [(10, s) for s in range(10)], "the intro sweep must cover the whole pool exactly once"


def test_a_problem_missed_during_the_intro_sweep_is_prioritised_right_after_it():
    series = make(10, 10, 0, 9)
    rng = random.Random(4)
    for _ in range(series.pool_size):
        problem = series.next_problem(rng=rng)
        # Miss b=7, answer everything else correctly.
        series.answer(series.expected(problem.key) + (7 if problem.key == (10, 7) else 0))

    assert series.problems[10, 7].points == 0
    assert (10, 7) in play(series, 4, rng), "the missed problem should come back immediately after the sweep"


def test_the_same_problem_is_not_asked_twice_in_a_row():
    series = make(10, 10, 0, 9)
    # Miss every third answer so the hunt runs long without reaching mastery.
    seen = play(series, 120, random.Random(11), miss_every=3)
    assert len(seen) == 120
    assert all(a != b for a, b in zip(seen, seen[1:])), "a problem should cool down before repeating"


def test_a_missed_problem_comes_back_within_a_couple_of_turns():
    """The relapse queue must be a guarantee, not a lucky weighted draw."""
    for seed in range(20):
        series = make(10, 10, 0, 9)
        rng = random.Random(seed)
        play(series, 10, rng)  # introduce everything

        ask(series, (10, 6), correct=False)
        missed_turn = series.turn

        seen = play(series, 3, rng)
        assert (10, 6) in seen, f"seed {seed}: a missed problem must return quickly, saw {seen}"
        assert series.problems[10, 6].last_seen_turn >= missed_turn


def test_a_repeatedly_missed_problem_keeps_coming_back():
    series = make(10, 10, 0, 9)
    rng = random.Random(1)
    play(series, 10, rng)

    for _ in range(3):
        ask(series, (10, 2), correct=False)
        assert (10, 2) in play(series, 3, rng)


def test_answering_a_relapsed_problem_correctly_clears_the_queue():
    series = make(10, 10, 0, 9)
    play(series, 10, random.Random(1))
    ask(series, (10, 2), correct=False)
    assert series.problems[10, 2].relapse_due is not None
    ask(series, (10, 2))
    assert series.problems[10, 2].relapse_due is None


def test_weight_rises_with_distance_from_mastery():
    series = make(10, 10, 0, 9)
    for problem in series.problems.values():
        problem.last_seen_turn = 0
    series.turn = 5
    series.problems[10, 0].points = 0
    series.problems[10, 1].points = MASTERY_TARGET
    assert problem_weight(series.problems[10, 0], series.turn) > problem_weight(series.problems[10, 1], series.turn)


def test_weight_rises_the_longer_a_problem_goes_unseen():
    series = make(10, 10, 0, 9)
    series.turn = 30
    fresh, stale = series.problems[10, 0], series.problems[10, 1]
    fresh.points = stale.points = MASTERY_TARGET
    fresh.last_seen_turn = 29
    stale.last_seen_turn = 2
    assert problem_weight(stale, series.turn) > problem_weight(fresh, series.turn)


def test_unfinished_work_outranks_sealed_problems():
    """Sealed demons come back for freshness, but never ahead of unfinished ones."""
    series = make(10, 10, 0, 4)
    for v in range(4):
        series.problems[10, v].points = MASTERY_TARGET
        series.problems[10, v].wrong = 1  # all of them were fumbled at some point
        series.problems[10, v].last_seen_turn = 0
    series.problems[10, 4].points = 2
    series.problems[10, 4].last_seen_turn = 0
    series.turn = 40
    series.last_review_turn = 40  # a review just happened, so none is due

    rng = random.Random(5)
    picks = [choose_problem(series, rng=rng).key for _ in range(200)]
    assert set(picks) == {(10, 4)}, "with a review not due, only the unfinished problem is asked"


def test_struggled_problems_are_asked_more_often():
    series = make(10, 10, 0, 9)
    for problem in series.problems.values():
        problem.points = 2
        problem.last_seen_turn = 10
    series.turn = 12
    series.problems[10, 7].heat = 3.0
    assert problem_weight(series.problems[10, 7], series.turn) > problem_weight(series.problems[10, 1], series.turn)


def test_slow_correct_answers_keep_the_problem_in_rotation():
    slow = make()
    slow_result = ask(slow, (10, 8), elapsed_ms=20_000)

    fast = make()
    ask(fast, (10, 8), elapsed_ms=400)

    assert slow_result["slow"] is True
    assert slow.problems[10, 8].heat > fast.problems[10, 8].heat
    assert slow.problems[10, 8].cooldown_until <= fast.problems[10, 8].cooldown_until


def test_scheduler_always_returns_a_problem_even_when_all_are_cooling_down():
    series = make(10, 10, 0, 1)
    for problem in series.problems.values():
        problem.cooldown_until = 999
        problem.last_seen_turn = 0
    assert choose_problem(series, rng=random.Random(1)) is not None


def test_a_finished_series_stops_handing_out_problems():
    series = make(10, 10, 0, 1)
    for v in (0, 1):
        for _ in range(MASTERY_TARGET):
            ask(series, (10, v))
    assert series.next_problem() is None


# --- a clean run must not be padded ------------------------------------------


@pytest.mark.parametrize("ranges", [(10, 10, 0, 9), (4, 8, 0, 3), (11, 14, 2, 5)])
def test_a_perfect_run_asks_each_problem_exactly_the_target_number_of_times(ranges):
    """Regression: getting everything right must not earn extra repetitions."""
    for seed in range(30):
        series = Series.create(*ranges)
        rng = random.Random(seed)
        asks = {v: 0 for v in series.problems}
        while not series.is_mastered:
            problem = series.next_problem(rng=rng)
            asks[problem.key] += 1
            series.answer(series.expected(problem.key))

        assert set(asks.values()) == {MASTERY_TARGET}, f"seed {seed}: {asks}"
        assert series.total_asked == series.pool_size * MASTERY_TARGET


def test_a_sealed_problem_with_a_clean_record_is_not_asked_again():
    series = make(10, 10, 0, 9)
    for problem in series.problems.values():
        problem.points = 1
        problem.last_seen_turn = 20
    clean = series.problems[10, 4]
    clean.points, clean.wrong, clean.last_seen_turn = MASTERY_TARGET, 0, 5
    series.turn = 40

    rng = random.Random(0)
    picks = {choose_problem(series, rng=rng).key for _ in range(300)}
    assert (10, 4) not in picks, "a problem never missed does not need re-testing"


def test_a_sealed_problem_that_was_missed_does_come_back():
    """The freshness rule still applies where it matters."""
    series = make(10, 10, 0, 9)
    for problem in series.problems.values():
        problem.points = 1
        problem.last_seen_turn = 20
    shaky = series.problems[10, 3]
    shaky.points, shaky.wrong, shaky.last_seen_turn = MASTERY_TARGET, 2, 5
    series.turn = 40

    assert [p.key for p in eligible_reviews(series, series.ordered_problems())] == [(10, 3)]
    rng = random.Random(0)
    assert (10, 3) in {choose_problem(series, rng=rng).key for _ in range(50)}


def test_a_freshly_seen_sealed_problem_is_not_reviewed_immediately():
    series = make(10, 10, 0, 9)
    for problem in series.problems.values():
        problem.points = 1
        problem.last_seen_turn = 20
    shaky = series.problems[10, 3]
    shaky.points, shaky.wrong = MASTERY_TARGET, 2
    shaky.last_seen_turn = 39  # only one turn ago
    series.turn = 40
    assert eligible_reviews(series, series.ordered_problems()) == []


def test_reviews_are_rate_limited():
    series = make(10, 10, 0, 9)
    rng = random.Random(4)
    review_turns = []
    guard = 0
    while not series.is_mastered and guard < 600:
        guard += 1
        problem = series.next_problem(rng=rng)
        if problem.mastered:
            review_turns.append(series.turn)
        series.answer(series.expected(problem.key) + (7 if rng.random() < 0.3 else 0))

    gaps = [b - a for a, b in zip(review_turns, review_turns[1:])]
    assert gaps, "this run should have contained some reviews"
    assert all(gap >= REVIEW_GAP for gap in gaps), gaps


def test_unfinished_problems_are_never_passed_over_for_a_sealed_one():
    """With work left to do, a sealed problem may only be picked as a review."""
    series = make(10, 10, 0, 9)
    rng = random.Random(2)
    guard = 0
    while not series.is_mastered and guard < 600:
        guard += 1
        problem = series.next_problem(rng=rng)
        if problem.mastered:
            assert problem.wrong > 0, "only previously-missed problems are reviewed"
            assert series.turn - problem.last_seen_turn >= REVIEW_MIN_STALENESS
        series.answer(series.expected(problem.key) + (7 if rng.random() < 0.25 else 0))


# --- lifecycle ---------------------------------------------------------------


def test_restart_clears_points_but_keeps_lifetime_stats():
    series = make(10, 10, 0, 2)
    for v in (0, 1, 2):
        for _ in range(MASTERY_TARGET):
            ask(series, (10, v))
    assert series.is_mastered

    series.restart()
    assert series.points_earned == 0
    assert not series.is_mastered
    assert series.completions == 1
    assert series.total_asked == 3 * MASTERY_TARGET
    assert series.best_streak == 3 * MASTERY_TARGET


@pytest.mark.parametrize("ranges", [(12, 12, 3, 8), (3, 8, 2, 2), (10, 13, 0, 5), (2, 4, 0, 9)])
def test_round_trip_serialisation_preserves_progress(ranges):
    series = Series.create(*ranges, allow_negative=ranges == (2, 4, 0, 9))
    rng = random.Random(2)
    play(series, 20, rng)
    series.next_problem(rng=rng)

    restored = Series.from_dict(series.to_dict())
    assert restored.id == series.id
    assert restored.allow_negative == series.allow_negative
    assert sorted(restored.problems) == sorted(series.problems)
    assert restored.points_earned == series.points_earned
    assert restored.current_key == series.current_key
    assert restored.turn == series.turn
    assert [p.to_dict() for p in restored.ordered_problems()] == [p.to_dict() for p in series.ordered_problems()]


def test_from_dict_rebuilds_a_pool_that_does_not_match_the_ranges():
    payload = make(10, 10, 0, 4).to_dict()
    payload["problems"] = payload["problems"][:2]  # simulate a hand-edited file
    restored = Series.from_dict(payload)
    assert sorted(restored.problems) == [(10, s) for s in range(5)]


def test_from_dict_defaults_to_leaving_below_zero_pairs_out():
    payload = make(10, 10, 0, 4).to_dict()
    del payload["allow_negative"]
    assert Series.from_dict(payload).allow_negative is False


# --- hunts saved before both sides could be ranges ---------------------------


def _legacy(fixed: int, t1: int, t2: int, vary: str) -> dict:
    """A profile entry in the shape the app used to save."""
    return {
        "fixed": fixed,
        "t1": t1,
        "t2": t2,
        "vary": vary,
        "problems": [{"v": v, "points": 2, "asked": 3, "correct": 2, "wrong": 1} for v in range(t1, t2 + 1)],
        "current_v": t1,
        "turn": 9,
        "total_asked": 12,
        "completions": 1,
    }


def test_an_old_fixed_minuend_hunt_loads_as_a_one_sided_range():
    series = Series.from_dict(_legacy(10, 0, 9, "subtrahend"))
    assert series.id == "r10-10x0-9-neg"
    assert series.label == "10 − [0…9]"
    assert sorted(series.problems) == [(10, s) for s in range(10)]
    assert series.current_key == (10, 0)


def test_an_old_fixed_subtrahend_hunt_loads_as_a_one_sided_range():
    series = Series.from_dict(_legacy(3, 5, 12, "minuend"))
    assert series.id == "r5-12x3-3-neg"
    assert series.label == "[5…12] − 3"
    assert sorted(series.problems) == [(m, 3) for m in range(5, 13)]


def test_an_old_hunt_keeps_its_progress_and_every_problem_it_had():
    """Its pool included pairs below zero, and those must survive the upgrade."""
    series = Series.from_dict(_legacy(3, 0, 6, "subtrahend"))
    assert series.allow_negative is True, "filtering now would silently delete practice"
    assert series.pool_size == 7
    assert series.points_earned == 7 * 2
    assert series.problems[3, 6].wrong == 1
    assert series.turn == 9 and series.completions == 1


def test_migrating_a_hunt_twice_changes_nothing():
    once = migrate_series(_legacy(10, 0, 9, "subtrahend"))
    assert migrate_series(once) == once


def test_a_modern_hunt_is_left_alone_by_the_migration():
    payload = make(10, 12, 0, 4).to_dict()
    assert migrate_series(payload) == payload
