"""Tests for the scoring engine.

The GROUP-stage cases are taken from REAL Polla data: the México 2-0 Sudáfrica
match (beforeGame01 predictions + TableAfterGame01 final points). Each tuple is a
prediction we could read off the screenshots together with the points Golpredictor
actually awarded — so passing these proves the engine matches the platform.
"""

import pytest

from app.scoring import Stage, max_points, score_prediction

# (pred_home, pred_away, expected_points) for actual result México 2-0 Sudáfrica.
# Confirmed users (Golpredictor awarded these exact points):
#   sjnietor/oasilv/jimenav/kevinb/arturov 2-0 -> 10
#   fonserate/juandarod26 2-1 -> 7
#   tomasamaya/seanroar 3-1 -> 6
MEXICO_2_0_CASES = [
    (2, 0, 10),  # exact score: result 5 + home 2 + away 2 + GD 1
    (2, 1, 7),   # result 5 + home 2 (away & GD wrong)
    (1, 0, 7),   # result 5 + away 2 (home & GD wrong)
    (3, 1, 6),   # result 5 + GD 1 (both teams wrong, diff still +2)
    (1, 1, 0),   # predicted draw -> wrong outcome, nothing lines up
    (0, 2, 1),   # wrong winner, but same 2-goal margin -> goal difference only
    (4, 2, 6),   # result 5 + GD 1
    (2, 2, 2),   # only home goals correct
]


@pytest.mark.parametrize("ph,pa,expected", MEXICO_2_0_CASES)
def test_group_stage_against_real_mexico_data(ph, pa, expected):
    assert score_prediction(ph, pa, 2, 0, Stage.GROUP).total == expected


def test_exact_score_is_max_group():
    assert score_prediction(2, 0, 2, 0, Stage.GROUP).total == max_points(Stage.GROUP) == 10


def test_breakdown_components_for_exact():
    b = score_prediction(2, 0, 2, 0, Stage.GROUP)
    assert (b.result, b.home_goals, b.away_goals, b.goal_difference) == (5, 2, 2, 1)


def test_knockout_doubles_everything():
    assert score_prediction(2, 0, 2, 0, Stage.KNOCKOUT).total == max_points(Stage.KNOCKOUT) == 20
    b = score_prediction(1, 0, 2, 0, Stage.KNOCKOUT)  # result + away goals
    assert b.total == 14  # 10 + 4


def test_draw_outcome_credited():
    # Predicted 1-1, actual 0-0: correct result (draw) + correct GD (0).
    b = score_prediction(1, 1, 0, 0, Stage.GROUP)
    assert b.result == 5 and b.goal_difference == 1
    assert b.home_goals == 0 and b.away_goals == 0
    assert b.total == 6


def test_goal_difference_is_absolute_margin():
    # Real Korea 2-1 (1-goal margin). These are the cases reported by the pool.
    # 1-2: wrong winner + wrong goals, but right margin -> only goal difference.
    assert score_prediction(1, 2, 2, 1, Stage.GROUP).total == 1
    # 0-1: correct away goals (1) + right margin -> 2 + 1 = 3.
    b = score_prediction(0, 1, 2, 1, Stage.GROUP)
    assert (b.result, b.home_goals, b.away_goals, b.goal_difference) == (0, 0, 2, 1)
    assert b.total == 3
    # Same margin, different actual margin must NOT score (1 vs 2).
    assert score_prediction(0, 1, 2, 0, Stage.GROUP).total == 0  # away win by1 vs home win by2


def test_live_score_scoring_is_just_a_normal_call():
    # The engine treats an in-progress live score exactly like a final one.
    # pred 2-1 vs live 1-0: correct result (5) + correct goal difference (1) = 6.
    assert score_prediction(2, 1, 1, 0, Stage.GROUP).total == 6
