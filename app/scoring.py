"""Scoring engine for the Polla World Cup prediction game.

Replicates Golpredictor's official rules (https://www.golpredictor.com/regulation.aspx).
Predictions cover 90 minutes of play only (no extra time / penalties).

Each prediction earns points from four INDEPENDENT, ADDITIVE components:

    | Component                       | Group | Knockout |
    |---------------------------------|-------|----------|
    | Correct result (W / D / L)      |   5   |    10    |
    | Correct home goals              |   2   |     4    |
    | Correct away goals              |   2   |     4    |
    | Correct goal difference         |   1   |     2    |
    | Max (exact score)               |  10   |    20    |

Knockout values are exactly the group values multiplied by 2.

The goal-difference component uses the ABSOLUTE margin, so a wrong winner with the
right margin still earns it (real 2-1: predicting 1-2 earns the 1 GD point).

Validated against real data (México 2-0 Sudáfrica, group stage):
    2-0 -> 10 (exact)        1-0 -> 7  (result + away goals)
    3-1 -> 6  (result + GD)  1-1 -> 0  (nothing matches)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Stage(str, Enum):
    """Tournament phase. Drives the points multiplier."""

    GROUP = "group"
    KNOCKOUT = "knockout"

    @property
    def multiplier(self) -> int:
        return 2 if self is Stage.KNOCKOUT else 1


# Base point values for the GROUP stage. Knockout = these * Stage.multiplier.
RESULT_POINTS = 5
GOALS_PER_TEAM_POINTS = 2
GOAL_DIFFERENCE_POINTS = 1


def _sign(n: int) -> int:
    """-1 / 0 / +1 — the outcome (away win / draw / home win)."""
    return (n > 0) - (n < 0)


@dataclass(frozen=True)
class ScoreBreakdown:
    """Per-component breakdown so the UI can explain *why* a score was earned."""

    result: int
    home_goals: int
    away_goals: int
    goal_difference: int

    @property
    def total(self) -> int:
        return self.result + self.home_goals + self.away_goals + self.goal_difference


def score_prediction(
    pred_home: int,
    pred_away: int,
    actual_home: int,
    actual_away: int,
    stage: Stage = Stage.GROUP,
) -> ScoreBreakdown:
    """Score a single prediction against an (actual or live) result.

    Works equally for a final result or a live in-progress score, which is what
    makes the real-time standings table possible: re-call this every time the
    live score changes.
    """
    mult = stage.multiplier

    result = (
        RESULT_POINTS * mult
        if _sign(pred_home - pred_away) == _sign(actual_home - actual_away)
        else 0
    )
    home_goals = GOALS_PER_TEAM_POINTS * mult if pred_home == actual_home else 0
    away_goals = GOALS_PER_TEAM_POINTS * mult if pred_away == actual_away else 0
    # Goal difference is the ABSOLUTE margin (Golpredictor awards it even to a
    # wrong winner): predicting 1-2 for a real 2-1 still matches the 1-goal margin.
    goal_difference = (
        GOAL_DIFFERENCE_POINTS * mult
        if abs(pred_home - pred_away) == abs(actual_home - actual_away)
        else 0
    )

    return ScoreBreakdown(result, home_goals, away_goals, goal_difference)


def max_points(stage: Stage = Stage.GROUP) -> int:
    """Maximum achievable points for one prediction in the given stage (10 / 20)."""
    return (RESULT_POINTS + 2 * GOALS_PER_TEAM_POINTS + GOAL_DIFFERENCE_POINTS) * stage.multiplier
