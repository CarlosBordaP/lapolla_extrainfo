"""Tests for analytics KPIs over finished matches."""

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.analytics import compute_highlights, compute_match_stats, compute_player_stats
from app.models import Base, Match, MatchStatus, Participant, Prediction
from app.scoring import Stage


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    yield s
    s.close()


def _match(session, home, away, hs, as_, status=MatchStatus.FINISHED, stage=Stage.GROUP):
    m = Match(stage=stage, home_team=home, away_team=away,
              kickoff_utc=dt.datetime(2026, 6, 11, 19, 0), status=status,
              home_score=hs, away_score=as_)
    session.add(m)
    session.flush()
    return m


def _pred(session, m, user, name, h, a):
    if session.get(Participant, user) is None:
        session.add(Participant(username=user, display_name=name))
    session.add(Prediction(match_id=m.id, username=user, pred_home=h, pred_away=a))


def test_only_finished_matches_count(session):
    live = _match(session, "A", "B", 1, 0, status=MatchStatus.LIVE)
    _pred(session, live, "kevinb", "Kevin", 1, 0)
    session.commit()
    assert compute_player_stats(session) == []  # live match ignored


def test_player_stats_two_matches(session):
    # Match 1: México 2-0. kevinb 2-0 (exact=10), fonse 2-1 (result+home=7).
    m1 = _match(session, "México", "Sudáfrica", 2, 0)
    _pred(session, m1, "kevinb", "Kevin", 2, 0)
    _pred(session, m1, "fonse", "Sandra", 2, 1)
    # Match 2: Canadá 1-1. kevinb 0-0 (result draw=5 + GD=1 =6), fonse 1-1 (exact=10).
    m2 = _match(session, "Canadá", "Gales", 1, 1)
    _pred(session, m2, "kevinb", "Kevin", 0, 0)
    _pred(session, m2, "fonse", "Sandra", 1, 1)
    session.commit()

    stats = {s.username: s for s in compute_player_stats(session)}
    kevin, fonse = stats["kevinb"], stats["fonse"]

    assert kevin.played == 2 and kevin.points == 16  # 10 + 6
    assert kevin.exact == 1 and kevin.correct_result == 2 and kevin.best == 10
    assert fonse.played == 2 and fonse.points == 17  # 7 + 10
    assert fonse.exact == 1 and fonse.correct_result == 2 and fonse.best == 10

    # fonse leads (17 > 16) so is first.
    assert [s.username for s in compute_player_stats(session)] == ["fonse", "kevinb"]


def test_match_stats_and_highlights(session):
    m1 = _match(session, "México", "Sudáfrica", 2, 0)
    _pred(session, m1, "kevinb", "Kevin", 2, 0)   # 10
    _pred(session, m1, "fonse", "Sandra", 2, 1)   # 7
    session.commit()

    ms = compute_match_stats(session)
    assert len(ms) == 1
    assert ms[0].predictors == 2 and ms[0].exact_count == 1
    assert ms[0].avg_points == 8.5  # (10 + 7) / 2
    assert ms[0].score == "2-0"

    h = compute_highlights(session)
    assert h["finished_matches"] == 1
    assert h["leader"]["username"] == "kevinb" and h["leader"]["value"] == 10
    assert h["best_single_match"]["value"] == 10


def test_highlights_empty_when_no_finished(session):
    assert compute_highlights(session) == {"finished_matches": 0, "predictions_scored": 0}
