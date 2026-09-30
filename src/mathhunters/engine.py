"""Scoring and problem-rotation logic, shared by both trainers.

Two operations are supported -- subtraction (Math Demon Hunters) and
multiplication (Math Jewel Hunters).  Everything here is the same for both
except the handful of things gathered in ``Operation`` below: what a pair works
out to, which pairs belong in the pool, and how a problem reads.

A *series* is a range on each side of the operation:

  * left range  ``[m1, m2]`` -- the numbers started from, or the group counts
  * right range ``[s1, s2]`` -- the numbers taken away, or the group sizes

The pool is every pair drawn from the two ranges.  A side pinned to a single
number is just a range of width one, so the classic shapes still work:

  * ``10…10 − 0…9``  -> 10-0, 10-1, … 10-9   (one start number)
  * ``5…12 − 3…3``   -> 5-3, 6-3, … 12-3     (one take-away)
  * ``10…12 − 0…4``  -> 10-0 … 12-4          (both sides sweep)
  * ``3…3 × 1…10``   -> 3×1, 3×2, … 3×10     (the three times table)

Pairs that would go below zero are dropped from a subtraction pool unless
``allow_negative`` is set, so a wide pool stays inside what a kid has actually
been taught.  Multiplication keeps every pair -- none of them go anywhere
awkward -- but the ranges may not reach past what the answer pad can hold.

Each problem carries a point score in ``[0, MASTERY_TARGET]``:

  * correct answer -> ``+1``
  * wrong answer   -> ``-2`` (never below zero)

The series is mastered once every problem sits at ``MASTERY_TARGET``.

A missed problem is not swapped out: it stays up and is asked again until it is
answered correctly, so a round always ends on the right answer and the problem
starts climbing back immediately.  Once corrected it is still queued to come
round again shortly, so the fix has to hold on its own.

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
from typing import Any

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

# --- Session clock -----------------------------------------------------------

# Longest single stretch credited to a hunt's clock between two events.  The
# clock is re-anchored on every answer, so this only bites when nothing happens
# for a long time -- a kid wandering off, or a browser closed without going back
# to HQ.  It bounds how much dead time a crashed session can add.
MAX_CREDITED_STRETCH_S = 300

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
# Two ranges multiply out fast, so the cap is on the finished pool rather than
# on either range.  At three points per problem this is already a long hunt.
MAX_POOL_SIZE = 64

# A problem is identified by the pair it is built from.
ProblemKey = tuple[int, int]

MINUS = "−"  # typographic minus, so "10 − 4" lines up nicely
TIMES = "×"  # multiplication sign, never a lowercase x


class SeriesError(ValueError):
    """Raised when a requested series is out of bounds."""


# --- Operations --------------------------------------------------------------

SUB = "sub"
MUL = "mul"


@dataclass(frozen=True)
class Operation:
    """Everything that differs between the two trainers.

    ``id`` is what a saved hunt records, ``id_prefix`` opens its hunt id so the
    two trainers can never read each other's saves by accident, and ``labels``
    supply the wording for complaints about the forge.
    """

    id: str
    glyph: str
    id_prefix: str
    labels: dict[str, str]
    order_errors: tuple[str, str]  # "low to high" complaints, m side then s side
    supports_negative: bool = False

    def expected(self, m: int, s: int) -> int:
        raise NotImplementedError

    def in_pool(self, m: int, s: int, allow_negative: bool) -> bool:
        """Is this pair one a kid should be asked?"""
        return True

    def pool_size(self, m1: int, m2: int, s1: int, s2: int, allow_negative: bool) -> int:
        """Size of the pool without building it -- ranges multiply out fast."""
        return (m2 - m1 + 1) * (s2 - s1 + 1)

    def check_ranges(self, m1: int, m2: int, s1: int, s2: int, allow_negative: bool) -> None:
        """Raise ``SeriesError`` for limits that are this operation's own."""


class _Subtraction(Operation):
    def expected(self, m: int, s: int) -> int:
        return m - s

    def in_pool(self, m: int, s: int, allow_negative: bool) -> bool:
        return allow_negative or m >= s

    def pool_size(self, m1: int, m2: int, s1: int, s2: int, allow_negative: bool) -> int:
        if allow_negative:
            return super().pool_size(m1, m2, s1, s2, allow_negative)
        return sum(max(0, min(s2, m) - s1 + 1) for m in range(m1, m2 + 1))

    def check_ranges(self, m1: int, m2: int, s1: int, s2: int, allow_negative: bool) -> None:
        if self.pool_size(m1, m2, s1, s2, allow_negative) == 0:
            raise SeriesError(
                "every pair there goes below zero — raise the start numbers, "
                "lower the take-aways, or allow answers below zero"
            )


class _Multiplication(Operation):
    def expected(self, m: int, s: int) -> int:
        return m * s

    def check_ranges(self, m1: int, m2: int, s1: int, s2: int, allow_negative: bool) -> None:
        # The answer pad holds three digits, so a hunt whose biggest product runs
        # past that would contain problems that literally cannot be answered.
        biggest = m2 * s2
        if biggest > MAX_OPERAND:
            raise SeriesError(
                f"{m2} {self.glyph} {s2} is {biggest}, past the {MAX_OPERAND} the answer "
                "pad holds — lower the ranges"
            )


SUBTRACTION = _Subtraction(
    id=SUB,
    glyph=MINUS,
    id_prefix="r",
    labels={
        "m1": "the lowest start number",
        "m2": "the highest start number",
        "s1": "the smallest take-away",
        "s2": "the largest take-away",
    },
    order_errors=(
        "the start numbers must go from low to high",
        "the take-away numbers must go from low to high",
    ),
    supports_negative=True,
)

MULTIPLICATION = _Multiplication(
    id=MUL,
    glyph=TIMES,
    id_prefix="m",
    labels={
        "m1": "the smallest number of groups",
        "m2": "the largest number of groups",
        "s1": "the smallest group size",
        "s2": "the largest group size",
    },
    order_errors=(
        "the number of groups must go from low to high",
        "the group sizes must go from low to high",
    ),
)

OPERATIONS: dict[str, Operation] = {SUB: SUBTRACTION, MUL: MULTIPLICATION}


def operation(op: str | Operation = SUB) -> Operation:
    """The operation named ``op``; unknown names fall back to subtraction."""
    if isinstance(op, Operation):
        return op
    return OPERATIONS.get(op, SUBTRACTION)


@dataclass
class ProblemState:
    """Per-problem progress inside a series, keyed by its ``(m, s)`` pair."""

    m: int
    s: int
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
    # Which operation this pair is read under.  The series it belongs to sets it;
    # it is not saved, since the series already records the operation.
    rules: Operation = field(default=SUBTRACTION, repr=False, compare=False)

    @property
    def key(self) -> ProblemKey:
        return (self.m, self.s)

    @property
    def expected(self) -> int:
        return self.rules.expected(self.m, self.s)

    @property
    def text(self) -> str:
        return f"{self.m} {self.rules.glyph} {self.s}"

    @property
    def mastered(self) -> bool:
        return self.points >= MASTERY_TARGET

    def to_dict(self) -> dict[str, Any]:
        return {
            "m": self.m,
            "s": self.s,
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
            m=int(data["m"]),
            s=int(data["s"]),
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
    """One practice pool: a range on the left against a range on the right."""

    m1: int
    m2: int
    s1: int
    s2: int
    allow_negative: bool = False
    op: str = SUB  # which operation this hunt practises
    problems: dict[ProblemKey, ProblemState] = field(default_factory=dict)
    timer_enabled: bool = False
    timer_seconds: int = TIMER_DEFAULT_SECONDS
    turn: int = 0
    last_review_turn: int = -999
    current_key: ProblemKey | None = None
    # True while the pending problem is a re-ask after a miss: it stays up until
    # it is answered correctly.
    retrying: bool = False
    # Session clock: accumulated play time, plus the start of the stretch
    # currently in progress.  ``running_since`` is deliberately never saved --
    # a hunt cannot be running while the app is closed.
    elapsed_ms: int = 0
    running_since: float | None = None
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
    def make_id(
        m1: int, m2: int, s1: int, s2: int, allow_negative: bool = False, op: str = SUB
    ) -> str:
        # Allowing negatives changes which pairs are in the pool, so it belongs
        # in the identity; the countdown, which changes nothing about the pool,
        # does not.  The leading letter is the operation's, so a subtraction hunt
        # and a multiplication hunt over the same ranges never collide.
        return (
            f"{operation(op).id_prefix}{m1}-{m2}x{s1}-{s2}"
            + ("-neg" if allow_negative else "")
        )

    @property
    def operation(self) -> Operation:
        return operation(self.op)

    @property
    def id(self) -> str:
        return self.make_id(self.m1, self.m2, self.s1, self.s2, self.allow_negative, self.op)

    @property
    def label(self) -> str:
        return f"{_span(self.m1, self.m2)} {self.operation.glyph} {_span(self.s1, self.s2)}"

    @classmethod
    def create(
        cls,
        m1: int,
        m2: int,
        s1: int,
        s2: int,
        allow_negative: bool = False,
        op: str = SUB,
    ) -> "Series":
        rules = operation(op)
        allow_negative = allow_negative and rules.supports_negative
        validate_series(m1, m2, s1, s2, allow_negative, op=rules)
        series = cls(
            m1=m1, m2=m2, s1=s1, s2=s2, allow_negative=allow_negative, op=rules.id
        )
        series.problems = {
            key: ProblemState(m=key[0], s=key[1], rules=rules) for key in series.pool_keys()
        }
        return series

    # -- problem shape --------------------------------------------------------

    def pool_keys(self) -> list[ProblemKey]:
        """Every pair this series practises, in reading order."""
        return build_pool(self.m1, self.m2, self.s1, self.s2, self.allow_negative, op=self.op)

    def expected(self, key: ProblemKey) -> int:
        return self.operation.expected(*key)

    def text(self, key: ProblemKey) -> str:
        return f"{key[0]} {self.operation.glyph} {key[1]}"

    def problem_view(self, problem: ProblemState) -> dict[str, Any]:
        # "left" and "right" rather than minuend/subtrahend: the same view feeds
        # both trainers, and one of them is not subtracting anything.
        return {
            "left": problem.m,
            "right": problem.s,
            "text": problem.text,
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

    # -- session clock --------------------------------------------------------

    @property
    def running(self) -> bool:
        return self.running_since is not None

    def resume(self) -> None:
        """Start the clock, or pick it up again after a break at HQ."""
        self._bank_time()
        self.running_since = time.time()
        self.updated_at = time.time()

    def pause(self) -> None:
        """Stop the clock — going back to HQ, or finishing the hunt."""
        if not self.running:
            return
        self._bank_time()
        self.updated_at = time.time()

    def _bank_time(self) -> None:
        """Move the stretch in progress into the accumulated total."""
        if self.running_since is None:
            return
        stretch = max(0.0, time.time() - self.running_since)
        self.elapsed_ms += int(min(stretch, MAX_CREDITED_STRETCH_S) * 1000)
        self.running_since = None

    def elapsed_ms_now(self) -> int:
        """Total play time including the stretch currently in progress."""
        if self.running_since is None:
            return self.elapsed_ms
        stretch = max(0.0, time.time() - self.running_since)
        return self.elapsed_ms + int(min(stretch, MAX_CREDITED_STRETCH_S) * 1000)

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
        self.current_key = None
        self.retrying = False
        self.streak = 0
        # A replay is a fresh attempt, so its clock starts from zero.
        self.elapsed_ms = 0
        self.running_since = None
        self.updated_at = time.time()

    # -- gameplay -------------------------------------------------------------

    def next_problem(self, rng: random.Random | None = None) -> ProblemState | None:
        """Pick (and remember) the problem to ask next."""
        if self.is_mastered:
            self.current_key = None
            return None
        if self.current_key is not None and self.current_key in self.problems:
            return self.problems[self.current_key]
        chosen = choose_problem(self, rng=rng)
        self.current_key = chosen.key if chosen else None
        self.retrying = False
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

        A miss leaves the same problem pending, so the next round is another go
        at it; the series only moves on once it is answered correctly.
        """
        if self.current_key is None or self.current_key not in self.problems:
            raise SeriesError("no problem is currently pending")
        if value is None and not timed_out:
            raise SeriesError("an answer is required")

        problem = self.problems[self.current_key]
        expected = problem.expected
        correct = (not timed_out) and value == expected
        was_retry = self.retrying
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
            # A correction is not proof it stuck -- the right answer was on
            # screen a moment ago -- so the problem still comes back shortly to
            # be answered cold.
            problem.relapse_due = self.turn + LAPSE_GAP if was_retry else None
            if slow:
                problem.heat = min(problem.heat + HEAT_ON_SLOW, HEAT_MAX)
        else:
            problem.wrong += 1
            problem.points = max(problem.points - WRONG_PENALTY, MIN_POINTS)
            problem.heat = min(problem.heat + HEAT_ON_MISS, HEAT_MAX)
            problem.relapse_due = None
            self.streak = 0

        problem.cooldown_until = self.turn + self._gap_for(correct, problem, slow)
        if was_mastered:
            self.last_review_turn = self.turn
        self.turn += 1
        # Hold a missed problem in place: the next round is another attempt at
        # it, not a new problem.
        self.retrying = not correct
        self.current_key = self.current_key if self.retrying else None
        self.updated_at = time.time()

        series_mastered = self.is_mastered
        if series_mastered:
            self.completions += 1
            self.last_mastered_at = time.time()
            self.pause()  # the hunt is over; freeze the final time
        else:
            # Re-anchor the clock each answer so one long pause cannot be
            # credited as play time in bulk.
            self.resume()

        return {
            "correct": correct,
            "expected": expected,
            "given": None if timed_out else value,
            "timed_out": timed_out,
            "left": problem.m,
            "right": problem.s,
            "text": problem.text,
            "delta": problem.points - before,
            "points": problem.points,
            "slow": slow,
            "seal_broken": was_mastered and not correct,
            "problem_mastered": problem.mastered and not was_mastered,
            "series_mastered": series_mastered,
            "streak": self.streak,
            # The same problem is coming back for another try.
            "retry": self.retrying,
            # This answer was the fix for a problem just missed.
            "corrected": correct and was_retry,
        }

    def _gap_for(self, correct: bool, problem: ProblemState, slow: bool) -> int:
        """How many turns before this problem may be asked again."""
        cap = max(0, self.pool_size - 1)
        if not correct:
            # A miss holds the problem in place for another try, so this is only
            # a fallback for the pending problem being lost (a hand-edited save).
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
            "m1": self.m1,
            "m2": self.m2,
            "s1": self.s1,
            "s2": self.s2,
            "allow_negative": self.allow_negative,
            "op": self.op,
            "timer_enabled": self.timer_enabled,
            "timer_seconds": self.timer_seconds,
            "problems": [p.to_dict() for p in self.ordered_problems()],
            "turn": self.turn,
            "last_review_turn": self.last_review_turn,
            # Only the banked total is saved; a stretch in progress is closed
            # first, so a hunt always loads paused.
            "elapsed_ms": self.elapsed_ms_now(),
            "current_key": list(self.current_key) if self.current_key else None,
            "retrying": self.retrying,
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
        data = migrate_series(data)
        m1, m2 = int(data["m1"]), int(data["m2"])
        s1, s2 = int(data["s1"]), int(data["s2"])
        # A hunt saved before there was a second trainer is a subtraction hunt.
        rules = operation(str(data.get("op", SUB)))
        allow_negative = bool(data.get("allow_negative", False)) and rules.supports_negative
        validate_series(m1, m2, s1, s2, allow_negative, op=rules)
        series = cls(
            m1=m1,
            m2=m2,
            s1=s1,
            s2=s2,
            allow_negative=allow_negative,
            op=rules.id,
            timer_enabled=bool(data.get("timer_enabled", False)),
            timer_seconds=clamp_timer_seconds(data.get("timer_seconds", TIMER_DEFAULT_SECONDS)),
            turn=int(data.get("turn", 0)),
            last_review_turn=int(data.get("last_review_turn", -999)),
            elapsed_ms=max(0, int(data.get("elapsed_ms", 0))),
            streak=int(data.get("streak", 0)),
            best_streak=int(data.get("best_streak", 0)),
            total_asked=int(data.get("total_asked", 0)),
            total_correct=int(data.get("total_correct", 0)),
            completions=int(data.get("completions", 0)),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            last_mastered_at=data.get("last_mastered_at"),
        )
        stored: dict[ProblemKey, ProblemState] = {}
        for raw in data.get("problems", []):
            problem = ProblemState.from_dict(raw)
            stored[problem.key] = problem
        # Rebuild from the ranges so a hand-edited file can never desync the pool.
        series.problems = {
            key: stored.get(key, ProblemState(m=key[0], s=key[1], rules=rules))
            for key in series.pool_keys()
        }
        for problem in series.problems.values():
            problem.rules = rules
        series.current_key = _as_key(data.get("current_key"), series.problems)
        series.retrying = bool(data.get("retrying", False)) and series.current_key is not None
        return series

    def ordered_problems(self) -> list[ProblemState]:
        return [self.problems[key] for key in sorted(self.problems)]

    def summary(self) -> dict[str, Any]:
        """Compact view used by the home screen."""
        return {
            "id": self.id,
            "m1": self.m1,
            "m2": self.m2,
            "s1": self.s1,
            "s2": self.s2,
            "allow_negative": self.allow_negative,
            "op": self.op,
            "label": self.label,
            "timer_enabled": self.timer_enabled,
            "timer_seconds": self.timer_seconds,
            "elapsed_ms": self.elapsed_ms_now(),
            "running": self.running,
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
        data["retrying"] = self.retrying
        return data


def build_pool(
    m1: int, m2: int, s1: int, s2: int, allow_negative: bool, op: str | Operation = SUB
) -> list[ProblemKey]:
    """Every pair from the two ranges this operation keeps, in reading order."""
    rules = operation(op)
    return [
        (m, s)
        for m in range(m1, m2 + 1)
        for s in range(s1, s2 + 1)
        if rules.in_pool(m, s, allow_negative)
    ]


def pool_size_for(
    m1: int, m2: int, s1: int, s2: int, allow_negative: bool, op: str | Operation = SUB
) -> int:
    """Size of the pool without building it — ranges can multiply out to millions."""
    return operation(op).pool_size(m1, m2, s1, s2, allow_negative)


def validate_series(
    m1: int,
    m2: int,
    s1: int,
    s2: int,
    allow_negative: bool = False,
    op: str | Operation = SUB,
) -> None:
    rules = operation(op)
    for key, value in (("m1", m1), ("m2", m2), ("s1", s1), ("s2", s2)):
        if not isinstance(value, int) or isinstance(value, bool):
            raise SeriesError(f"{rules.labels[key]} must be a whole number")
        if not (0 <= value <= MAX_OPERAND):
            raise SeriesError(f"{rules.labels[key]} must be between 0 and {MAX_OPERAND}")
    if m1 > m2:
        raise SeriesError(rules.order_errors[0])
    if s1 > s2:
        raise SeriesError(rules.order_errors[1])

    # Whatever else this operation will not stand for: an empty subtraction pool,
    # a multiplication whose answers run off the pad.
    rules.check_ranges(m1, m2, s1, s2, allow_negative)
    size = rules.pool_size(m1, m2, s1, s2, allow_negative)
    if size > MAX_POOL_SIZE:
        raise SeriesError(
            f"those ranges make {size} problems — keep it to {MAX_POOL_SIZE} or fewer"
        )


def migrate_series(data: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a hunt saved before both sides could be ranges.

    The old shape pinned one side (``fixed``) and swept ``[t1, t2]`` over the
    other, naming the swept side in ``vary``.  Negatives were never filtered
    back then, so the converted hunt keeps ``allow_negative`` on and its pool
    comes back identical, progress and all.
    """
    if "fixed" not in data:
        return data

    fixed, t1, t2 = int(data["fixed"]), int(data["t1"]), int(data["t2"])
    varies_minuend = data.get("vary", "subtrahend") == "minuend"
    m1, m2, s1, s2 = (t1, t2, fixed, fixed) if varies_minuend else (fixed, fixed, t1, t2)

    dropped = ("fixed", "t1", "t2", "vary", "current_v")
    upgraded = {k: v for k, v in data.items() if k not in dropped}
    upgraded.update({"m1": m1, "m2": m2, "s1": s1, "s2": s2, "allow_negative": True})

    def pair(v: int) -> ProblemKey:
        """Where the swept value sat in the old one-sided pool."""
        return (v, fixed) if varies_minuend else (fixed, v)

    def upgrade_problem(raw: dict[str, Any]) -> dict[str, Any]:
        m, s = pair(int(raw["v"]))
        return {**{k: val for k, val in raw.items() if k != "v"}, "m": m, "s": s}

    upgraded["problems"] = [
        upgrade_problem(raw) for raw in data.get("problems", []) if "v" in raw
    ]
    current_v = data.get("current_v")
    upgraded["current_key"] = None if current_v is None else list(pair(int(current_v)))
    return upgraded


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


def _span(low: int, high: int) -> str:
    """How one side reads in a label: a single number, or a range."""
    return str(low) if low == high else f"[{low}…{high}]"


def _as_key(raw: Any, problems: dict[ProblemKey, ProblemState]) -> ProblemKey | None:
    """Read a stored ``current_key``, dropping anything not in the pool."""
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None
    try:
        key = (int(raw[0]), int(raw[1]))
    except (TypeError, ValueError):
        return None
    return key if key in problems else None


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))
