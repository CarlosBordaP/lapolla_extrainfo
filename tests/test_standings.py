"""End-to-end test of compute_standings using an in-memory SQLite DB.

Uses real predictions from the México 2-0 Sudáfrica match to prove the full path
(predictions + match score -> ranked standings) matches Golpredictor's points.
"""

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Match, MatchStatus, Participant, Prediction
from app.scoring import Stage
from app.standings import assign_ranks, compute_live_board, compute_standings


def test_assign_ranks_shares_positions_on_ties():
    # user1=20, user2=20, user3=16 -> positions 1, 1, 3.
    assert assign_ranks([20, 20, 16]) == [1, 1, 3]
    assert assign_ranks([30, 20, 20, 20, 10]) == [1, 2, 2, 2, 5]
    assert assign_ranks([10]) == [1]
    assert assign_ranks([]) == []


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    yield s
    s.close()


# (username, display_name, pred_home, pred_away, expected_points) — actual 2-0.
ROWS = [
    ("sjnietor", "Steffen Nieto", 2, 0, 10),
    ("oasilv", "Orlando Silva", 2, 0, 10),
    ("fonserate", "Sandra Fonseca", 2, 1, 7),
    ("tomasamaya", "Tomas Amaya", 3, 1, 6),
    ("mayeli", "Claudia Mayeli Guerrero", 1, 2, 0),
]


def test_standings_ranks_real_match(session):
    match = Match(
        stage=Stage.GROUP,
        home_team="México",
        away_team="Sudáfrica",
        kickoff_utc=dt.datetime(2026, 6, 11, 19, 0),
        status=MatchStatus.FINISHED,
        home_score=2,
        away_score=0,
    )
    session.add(match)
    session.flush()
    for username, name, ph, pa, _ in ROWS:
        session.add(Participant(username=username, display_name=name))
        session.add(Prediction(match_id=match.id, username=username, pred_home=ph, pred_away=pa))
    session.commit()

    standings = compute_standings(session)

    # Correct points per user.
    by_user = {r.username: r.total_points for r in standings}
    assert by_user == {u: pts for u, _, _, _, pts in ROWS}

    # Correctly ranked (highest first, stable tie-break by username).
    assert [r.username for r in standings] == [
        "oasilv", "sjnietor", "fonserate", "tomasamaya", "mayeli"
    ]


def _add(session, m, user, name, h, a):
    if session.get(Participant, user) is None:
        session.add(Participant(username=user, display_name=name))
    session.add(Prediction(match_id=m.id, username=user, pred_home=h, pred_away=a))


def test_live_board_movement_and_live_points(session):
    # Finished match (2-0): alice 2-0 -> 10, bob 2-1 -> 7. Baseline: alice #1, bob #2.
    fin = Match(stage=Stage.GROUP, home_team="A", away_team="B",
                kickoff_utc=dt.datetime(2026, 6, 11, 19, 0),
                status=MatchStatus.FINISHED, home_score=2, away_score=0)
    session.add(fin); session.flush()
    _add(session, fin, "alice", "Alice", 2, 0)
    _add(session, fin, "bob", "Bob", 2, 1)
    # Live match (1-0): alice 0-0 -> 2 (away), bob 1-0 -> 10. bob overtakes.
    liv = Match(stage=Stage.GROUP, home_team="C", away_team="D",
                kickoff_utc=dt.datetime(2026, 6, 12, 19, 0),
                status=MatchStatus.LIVE, home_score=1, away_score=0)
    session.add(liv); session.flush()
    _add(session, liv, "alice", "Alice", 0, 0)
    _add(session, liv, "bob", "Bob", 1, 0)
    session.commit()

    board = compute_live_board(session)
    assert board["match"]["home_team"] == "C"  # the single live match
    rows = {r["username"]: r for r in board["rows"]}

    # Totals: bob 7+10=17 (#1), alice 10+2=12 (#2).
    assert rows["bob"]["rank"] == 1 and rows["bob"]["points"] == 17
    assert rows["alice"]["rank"] == 2 and rows["alice"]["points"] == 12
    # Movement vs pre-live baseline (alice #1, bob #2): bob +1, alice -1.
    assert rows["bob"]["delta"] == 1 and rows["alice"]["delta"] == -1
    # Live points (from the live match only) + prediction shown.
    assert rows["bob"]["live_points"] == 10 and (rows["bob"]["pred_home"], rows["bob"]["pred_away"]) == (1, 0)
    assert rows["alice"]["live_points"] == 2 and (rows["alice"]["pred_home"], rows["alice"]["pred_away"]) == (0, 0)


def test_live_board_uses_last_finished_match_when_no_live(session):
    # Two finished matches, none live: the board shows movement from match 1 -> 2.
    m1 = Match(stage=Stage.GROUP, home_team="A", away_team="B",
               kickoff_utc=dt.datetime(2026, 6, 11, 19, 0),
               status=MatchStatus.FINISHED, home_score=2, away_score=0)
    m2 = Match(stage=Stage.GROUP, home_team="C", away_team="D",
               kickoff_utc=dt.datetime(2026, 6, 12, 19, 0),
               status=MatchStatus.FINISHED, home_score=1, away_score=0)
    session.add_all([m1, m2]); session.flush()
    # m1 (2-0): alice 2-1 -> 7, bob 1-1 -> 0.  m2 (1-0): alice 0-0 -> 2, bob 1-0 -> 10.
    _add(session, m1, "alice", "Alice", 2, 1)
    _add(session, m1, "bob", "Bob", 1, 1)
    _add(session, m2, "alice", "Alice", 0, 0)
    _add(session, m2, "bob", "Bob", 1, 0)
    session.commit()

    board = compute_live_board(session)
    assert board["match"]["home_team"] == "C"  # reference = last finished match
    rows = {r["username"]: r for r in board["rows"]}
    # Totals: alice 9, bob 10. Movement vs before m2 (alice 7 #1, bob 0 #2): bob overtakes.
    assert rows["alice"]["points"] == 9 and rows["bob"]["points"] == 10
    assert rows["bob"]["delta"] == 1 and rows["alice"]["delta"] == -1
    assert rows["bob"]["live_points"] == 10 and rows["alice"]["live_points"] == 2


def test_no_scored_matches_returns_empty(session):
    session.add(Participant(username="a", display_name="A"))
    session.add(
        Match(
            stage=Stage.GROUP,
            home_team="X",
            away_team="Y",
            kickoff_utc=dt.datetime(2026, 6, 11, 19, 0),
            status=MatchStatus.SCHEDULED,
        )
    )
    session.commit()
    assert compute_standings(session) == []
