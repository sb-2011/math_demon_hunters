"""Scoring and problem-rotation logic for Math Demon Hunters.

A *series* pins one side of the subtraction and sweeps a range over the other:

  * ``vary="subtrahend"`` -> ``fixed - v`` for every ``v`` in ``[t1, t2]``
    (e.g. fixed 10 over 0…9 gives 10-0, 10-1, … 10-9)
  * ``vary="minuend"``    -> ``v - fixed`` for every ``v`` in ``[t1, t2]``
    (e.g. fixed 3 over 5…12 gives 5-3, 6-3, … 12-3)

Exactly one side varies; the other is always a single number.

Each problem carries a point score in ``[0, MASTERY_TARGET]``:

  * correct answer -> ``+1``
  * wrong answer   -> ``-2`` (never below zero)

The series is mastered once every problem sits at ``MASTERY_TARGET``.

The scheduler deliberately keeps problems in rotation rather than drilling one
until it sticks and then dropping it forever.  Every problem is introduced once
before anything repeats; after that, three pressures decide what gets asked
next: how far a problem is from mastery, how long since it was last seen, and
how much recent trouble it has caused.  Mastered problems stay in the pool
at a low rate that climbs the longer they go unseen, so recall stays fresh -- and
if one is missed it drops back below the target and has to be re-earned.

A series can optionally run a per-problem countdown; letting it expire scores
the same as a wrong answer.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Literal

# --- Scoring rules -----------------------------------------------------------

MASTERY_TARGET = 3
CORRECT_POINTS = 1
WRONG_PENALTY = 2
MIN_POINTS = 0

# An answer slower than this still counts, but the problem is treated as
# "not yet fluent" -- it comes back sooner so recall keeps sharpening.
SLOW_ANSWER_MS = 6000

# --- Optional per-problem countdown ------------------------------------------

TIMER_DEFAULT_SECONDS = 10
TIMER_MIN_SECONDS = 3
TIMER_MAX_SECONDS = 120

# --- Scheduler tuning --------------------------------------------------------

UNSEEN_WEIGHT = 120.0  # make sure every problem gets introduced early
URGENCY_PER_POINT = 2.5  # distance from mastery dominates the ranking
STALENESS_PER_TURN = 0.35  # unseen-for-a-while problems drift back up
STALENESS_CAP = 12
HEAT_MULTIPLIER = 1.2  # recently-missed problems come back harder
HEAT_MAX = 3.0
HEAT_ON_MISS = 1.0
HEAT_ON_SLOW = 0.35
HEAT_DECAY_ON_CORRECT = 0.6

LAPSE_GAP = 2  # turns to wait before re-asking a missed problem
SLOW_GAP_CAP = 3  # a slow-but-correct answer returns within this many turns

# Review passes over *sealed* problems.  Only problems that have actually been
# missed or fumbled at some point are worth re-testing -- a problem answered
# correctly every time it was asked is genuinely known, and asking it a fourth
# time is padding, not practice.  These bound how often a review may happen.
REVIEW_GAP = 4  # minimum turns between two review picks
REVIEW_MIN_STALENESS = 5  # a sealed problem must be unseen this long to be reviewed

# --- Series limits -----------------------------------------------------------

MAX_OPERAND = 999
MAX_POOL_SIZE = 40

VaryingSide = Literal["minuend", "subtrahend"]
VARY_SIDES: tuple[VaryingSide, ...] = ("minuend", "subtrahend")

MINUS = "−"  # typographic minus, so "10 − 4" lines up nicely


class SeriesError(ValueError):
    """Raised when a requested series is out of bounds."""


@dataclass
class ProblemState:
    """Per-problem progress inside a series, keyed by the varying operand."""

    v: int
    points: int = 0
    asked: int = 0
    correct: int = 0
    wrong: int = 0
    heat: float = 0.0
    last_seen_turn: int = -1
    cooldown_until: int = 0
    relapse_due: int | None = None
    fastest_ms: int | None = None
    last_ms: int | None = None

    @property
    def mastered(self) -> bool:
        return self.points >= MASTERY_TARGET

    def to_dict(self) -> dict[str, Any]:
        return {
            "v": self.v,
            "points": self.points,
            "asked": self.asked,
            "correct": self.correct,
            "wrong": self.wrong,
            "heat": round(self.heat, 4),
            "last_seen_turn": self.last_seen_turn,
            "cooldown_until": self.cooldown_until,
            "relapse_due": self.relapse_due,
            "fastest_ms": self.fastest_ms,
            "last_ms": self.last_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProblemState":
        return cls(
            v=int(data["v"]),
            points=_clamp(int(data.get("points", 0)), MIN_POINTS, MASTERY_TARGET),
            asked=int(data.get("asked", 0)),
            correct=int(data.get("correct", 0)),
            wrong=int(data.get("wrong", 0)),
            heat=float(data.get("heat", 0.0)),
            last_seen_turn=int(data.get("last_seen_turn", -1)),
            cooldown_until=int(data.get("cooldown_until", 0)),
            relapse_due=data.get("relapse_due"),
            fastest_ms=data.get("fastest_ms"),
            last_ms=data.get("last_ms"),
        )


@dataclass
class Series:
    """One practice pool: one fixed operand against a range on the other side."""

    fixed: int
    t1: int
    t2: int
    vary: VaryingSide = "subtrahend"
    problems: dict[int, ProblemState] = field(default_factory=dict)
    timer_enabled: bool = False
    timer_seconds: int = TIMER_DEFAULT_SECONDS
    turn: int = 0
    last_review_turn: int = -999
    current_v: int | None = None
    streak: int = 0
    best_streak: int = 0
    total_asked: int = 0
    total_correct: int = 0
    completions: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_mastered_at: float | None = None

    # -- identity -------------------------------------------------------------

    @staticmethod
    def make_id(fixed: int, t1: int, t2: int, vary: VaryingSide) -> str:
        # The leading letter marks which side the range sweeps, so the two
        # orientations of the same numbers stay separate hunts.
        return f"{'m' if vary == 'minuend' else 's'}{fixed}-{t1}-{t2}"

    @property
    def id(self) -> str:
        return self.make_id(self.fixed, self.t1, self.t2, self.vary)

    @property
    def label(self) -> str:
        span = f"[{self.t1}…{self.t2}]"
        if self.vary == "minuend":
            return f"{span} {MINUS} {self.fixed}"
        return f"{self.fixed} {MINUS} {span}"

    @classmethod
    def create(cls, fixed: int, t1: int, t2: int, vary: VaryingSide = "subtrahend") -> "Series":
        validate_series(fixed, t1, t2, vary)
        series = cls(fixed=fixed, t1=t1, t2=t2, vary=vary)
        series.problems = {v: ProblemState(v=v) for v in range(t1, t2 + 1)}
        return series

    # -- problem shape --------------------------------------------------------

    def minuend(self, v: int) -> int:
        return v if self.vary == "minuend" else self.fixed

    def subtrahend(self, v: int) -> int:
        return self.fixed if self.vary == "minuend" else v

    def expected(self, v: int) -> int:
        return self.minuend(v) - self.subtrahend(v)

    def text(self, v: int) -> str:
        return f"{self.minuend(v)} {MINUS} {self.subtrahend(v)}"

    def problem_view(self, problem: ProblemState) -> dict[str, Any]:
        return {
            "v": problem.v,
            "minuend": self.minuend(problem.v),
            "subtrahend": self.subtrahend(problem.v),
            "text": self.text(problem.v),
            "points": problem.points,
            "asked": problem.asked,
            "correct": problem.correct,
            "wrong": problem.wrong,
            "mastered": problem.mastered,
            "fastest_ms": problem.fastest_ms,
        }

    # -- progress -------------------------------------------------------------

    @property
    def pool_size(self) -> int:
        return len(self.problems)

    @property
    def mastered_count(self) -> int:
        return sum(1 for p in self.problems.values() if p.mastered)

    @property
    def points_earned(self) -> int:
        return sum(p.points for p in self.problems.values())

    @property
    def points_possible(self) -> int:
        return self.pool_size * MASTERY_TARGET

    @property
    def is_mastered(self) -> bool:
        return self.pool_size > 0 and all(p.mastered for p in self.problems.values())

    def restart(self) -> None:
        """Wipe point progress for a replay, keeping lifetime stats."""
        for problem in self.problems.values():
            problem.points = 0
            problem.heat = 0.0
            problem.last_seen_turn = -1
            problem.cooldown_until = 0
            problem.relapse_due = None
        self.turn = 0
        self.last_review_turn = -999
        self.current_v = None
        self.streak = 0
        self.updated_at = time.time()

    # -- gameplay -------------------------------------------------------------

    def next_problem(self, rng: random.Random | None = None) -> ProblemState | None:
        """Pick (and remember) the problem to ask next."""
        if self.is_mastered:
            self.current_v = None
            return None
        if self.current_v is not None and self.current_v in self.problems:
            return self.problems[self.current_v]
        chosen = choose_problem(self, rng=rng)
        self.current_v = chosen.v if chosen else None
        return chosen

    def answer(
        self,
        value: int | None,
        elapsed_ms: int | None = None,
        timed_out: bool = False,
    ) -> dict[str, Any]:
        """Grade ``value`` against the pending problem and advance the series.

        A ``timed_out`` round scores exactly like a wrong answer -- the clock
        running out is the same signal as not knowing it yet.
        """
        if self.current_v is None or self.current_v not in self.problems:
            raise SeriesError("no problem is currently pending")
        if value is None and not timed_out:
            raise SeriesError("an answer is required")

        problem = self.problems[self.current_v]
        expected = self.expected(problem.v)
        correct = (not timed_out) and value == expected
        was_mastered = problem.mastered
        before = problem.points
        slow = bool(correct and elapsed_ms is not None and elapsed_ms > SLOW_ANSWER_MS)

        problem.asked += 1
        problem.last_seen_turn = self.turn
        problem.last_ms = elapsed_ms
        self.total_asked += 1

        if correct:
            problem.correct += 1
            problem.points = min(problem.points + CORRECT_POINTS, MASTERY_TARGET)
            problem.heat = problem.heat * HEAT_DECAY_ON_CORRECT
            self.total_correct += 1
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
            if elapsed_ms is not None:
                if problem.fastest_ms is None or elapsed_ms < problem.fastest_ms:
                    problem.fastest_ms = elapsed_ms
            problem.relapse_due = None
            if slow:
                problem.heat = min(problem.heat + HEAT_ON_SLOW, HEAT_MAX)
        else:
            problem.wrong += 1
            problem.points = max(problem.points - WRONG_PENALTY, MIN_POINTS)
            problem.heat = min(problem.heat + HEAT_ON_MISS, HEAT_MAX)
            # Come back to this one shortly, while the correction is still fresh.
            problem.relapse_due = self.turn + LAPSE_GAP
            self.streak = 0

        problem.cooldown_until = self.turn + self._gap_for(correct, problem, slow)
        if was_mastered:
            self.last_review_turn = self.turn
        self.turn += 1
        self.current_v = None
        self.updated_at = time.time()

        series_mastered = self.is_mastered
        if series_mastered:
            self.completions += 1
            self.last_mastered_at = time.time()

        return {
            "correct": correct,
            "expected": expected,
            "given": None if timed_out else value,
            "timed_out": timed_out,
            "v": problem.v,
            "minuend": self.minuend(problem.v),
            "subtrahend": self.subtrahend(problem.v),
            "text": self.text(problem.v),
            "delta": problem.points - before,
            "points": problem.points,
            "slow": slow,
            "seal_broken": was_mastered and not correct,
            "problem_mastered": problem.mastered and not was_mastered,
            "series_mastered": series_mastered,
            "streak": self.streak,
        }

    def _gap_for(self, correct: bool, problem: ProblemState, slow: bool) -> int:
        """How many turns before this problem may be asked again."""
        cap = max(0, self.pool_size - 1)
        if not correct:
            return min(LAPSE_GAP, cap)
        # Spacing widens as a problem approaches mastery, so late practice is
        # spread out rather than crammed -- unless the answer came in slowly.
        gap = 1 + problem.points
        if slow:
            gap = min(gap, SLOW_GAP_CAP)
        return min(gap, cap)

    # -- serialisation --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixed": self.fixed,
            "t1": self.t1,
            "t2": self.t2,
            "vary": self.vary,
            "timer_enabled": self.timer_enabled,
            "timer_seconds": self.timer_seconds,
            "problems": [p.to_dict() for p in self.ordered_problems()],
            "turn": self.turn,
            "last_review_turn": self.last_review_turn,
            "current_v": self.current_v,
            "streak": self.streak,
            "best_streak": self.best_streak,
            "total_asked": self.total_asked,
            "total_correct": self.total_correct,
            "completions": self.completions,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_mastered_at": self.last_mastered_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Series":
        fixed, t1, t2 = int(data["fixed"]), int(data["t1"]), int(data["t2"])
        vary = data.get("vary", "subtrahend")
        validate_series(fixed, t1, t2, vary)
        series = cls(
            fixed=fixed,
            t1=t1,
            t2=t2,
            vary=vary,
            timer_enabled=bool(data.get("timer_enabled", False)),
            timer_seconds=clamp_timer_seconds(data.get("timer_seconds", TIMER_DEFAULT_SECONDS)),
            turn=int(data.get("turn", 0)),
            last_review_turn=int(data.get("last_review_turn", -999)),
            streak=int(data.get("streak", 0)),
            best_streak=int(data.get("best_streak", 0)),
            total_asked=int(data.get("total_asked", 0)),
            total_correct=int(data.get("total_correct", 0)),
            completions=int(data.get("completions", 0)),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            last_mastered_at=data.get("last_mastered_at"),
        )
        stored: dict[int, ProblemState] = {}
        for raw in data.get("problems", []):
            problem = ProblemState.from_dict(raw)
            stored[problem.v] = problem
        # Rebuild from the range so a hand-edited file can never desync the pool.
        series.problems = {v: stored.get(v, ProblemState(v=v)) for v in range(t1, t2 + 1)}
        current_v = data.get("current_v")
        series.current_v = (
            int(current_v) if current_v is not None and int(current_v) in series.problems else None
        )
        return series

    def ordered_problems(self) -> list[ProblemState]:
        return [self.problems[v] for v in sorted(self.problems)]

    def summary(self) -> dict[str, Any]:
        """Compact view used by the home screen."""
        return {
            "id": self.id,
            "fixed": self.fixed,
            "t1": self.t1,
            "t2": self.t2,
            "vary": self.vary,
            "label": self.label,
            "timer_enabled": self.timer_enabled,
            "timer_seconds": self.timer_seconds,
            "pool_size": self.pool_size,
            "mastered_count": self.mastered_count,
            "points_earned": self.points_earned,
            "points_possible": self.points_possible,
            "is_mastered": self.is_mastered,
            "completions": self.completions,
            "best_streak": self.best_streak,
            "total_asked": self.total_asked,
            "total_correct": self.total_correct,
            "updated_at": self.updated_at,
            "last_mastered_at": self.last_mastered_at,
        }

    def detail(self) -> dict[str, Any]:
        """Full view used by the play screen."""
        data = self.summary()
        data["problems"] = [self.problem_view(p) for p in self.ordered_problems()]
        data["streak"] = self.streak
        data["turn"] = self.turn
        return data


def validate_series(fixed: int, t1: int, t2: int, vary: str = "subtrahend") -> None:
    if vary not in VARY_SIDES:
        raise SeriesError("the range must sweep either the minuend or the subtrahend")
    labels = {
        "fixed": "the fixed number",
        "t1": "the range start",
        "t2": "the range end",
    }
    for key, value in (("fixed", fixed), ("t1", t1), ("t2", t2)):
        if not isinstance(value, int) or isinstance(value, bool):
            raise SeriesError(f"{labels[key]} must be a whole number")
        if not (0 <= value <= MAX_OPERAND):
            raise SeriesError(f"{labels[key]} must be between 0 and {MAX_OPERAND}")
    if t1 > t2:
        raise SeriesError("the range start must not be greater than the range end")
    if (t2 - t1 + 1) > MAX_POOL_SIZE:
        raise SeriesError(f"that range makes more than {MAX_POOL_SIZE} problems — try a smaller one")


def clamp_timer_seconds(value: Any) -> int:
    """Coerce a stored or requested countdown into the supported range."""
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return TIMER_DEFAULT_SECONDS
    return _clamp(seconds, TIMER_MIN_SECONDS, TIMER_MAX_SECONDS)


def problem_weight(problem: ProblemState, turn: int) -> float:
    """Relative chance of ``problem`` being asked on ``turn``."""
    if problem.last_seen_turn < 0:
        return UNSEEN_WEIGHT

    need = MASTERY_TARGET - problem.points
    urgency = 1.0 + URGENCY_PER_POINT * need

    staleness = min(turn - problem.last_seen_turn, STALENESS_CAP)
    recency = 1.0 + STALENESS_PER_TURN * max(staleness, 0)

    struggle = 1.0 + HEAT_MULTIPLIER * problem.heat

    return urgency * recency * struggle


def eligible_reviews(series: Series, candidates: list[ProblemState]) -> list[ProblemState]:
    """Sealed problems that have earned another look.

    Only problems that were missed at some point during this run qualify.  A
    problem answered correctly every single time it was asked is known, and
    re-asking it just makes a perfect run longer for no benefit.
    """
    if series.turn - series.last_review_turn < REVIEW_GAP:
        return []
    return [
        p
        for p in candidates
        if p.mastered
        and p.wrong > 0
        and series.turn - p.last_seen_turn >= REVIEW_MIN_STALENESS
    ]


def choose_problem(series: Series, rng: random.Random | None = None) -> ProblemState | None:
    """Weighted pick of the next problem, respecting per-problem cooldowns."""
    rng = rng or random
    problems = series.ordered_problems()
    if not problems:
        return None

    # 1. Introduction sweep: while anything is still unseen, ask only unseen
    #    problems.  The kid meets every problem in the pool before any repeats,
    #    and no amount of struggle on an early problem can crowd the rest out.
    unseen = [p for p in problems if p.last_seen_turn < 0]
    if unseen:
        return rng.choice(unseen)

    oldest_first = lambda group: sorted(group, key=lambda p: p.last_seen_turn)  # noqa: E731
    due = [p for p in problems if p.cooldown_until <= series.turn]

    # 2. Relapse queue: a problem that was just missed gets re-asked once its
    #    short gap has passed, rather than waiting on a lucky weighted draw.
    relapsed = [p for p in due if p.relapse_due is not None and p.relapse_due <= series.turn]
    if relapsed:
        candidates = relapsed
    else:
        unsealed = [p for p in problems if not p.mastered]
        if unsealed:
            # 3. Bounded review of a sealed-but-previously-fumbled problem.
            reviews = eligible_reviews(series, due)
            if reviews:
                candidates = reviews
            else:
                # 4. Otherwise always an unfinished problem.  If they are all
                #    cooling down, take the least recently seen one -- padding
                #    with a sealed problem would just lengthen a clean run.
                candidates = [p for p in due if not p.mastered] or oldest_first(unsealed)[:1]
        else:
            candidates = due or oldest_first(problems)[:1]

    weights = [problem_weight(p, series.turn) for p in candidates]
    if sum(weights) <= 0:
        return rng.choice(candidates)
    return rng.choices(candidates, weights=weights, k=1)[0]


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))
