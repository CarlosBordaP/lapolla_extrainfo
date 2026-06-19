"""Tests for the live-score loop: provider parsing + poll_once + standings update.

No network — a FakeProvider stands in for the real API.
"""

import datetime as dt

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import Base, Match, MatchStatus, Participant, Prediction
from app.poller import has_live_window, poll_once
from app.scoring import Stage
from app.scores.base import ProviderGame, normalize_team
from app.scores.scores365 import parse_games as parse_games_365
from app.scores.worldcup_free import parse_games
from app.standings import compute_standings


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    yield s
    s.close()


class FakeProvider:
    name = "fake"

    def __init__(self, games):
        self._games = games

    def fetch_games(self):
        return self._games


def _seed_mexico_match(session):
    match = Match(
        stage=Stage.GROUP,
        home_team="México",
        away_team="Sudáfrica",
        kickoff_utc=dt.datetime(2026, 6, 11, 19, 0),
        status=MatchStatus.SCHEDULED,
    )
    session.add(match)
    session.flush()
    # Two predictions: kevinb 2-0 (exact), fonserate 2-1 (result + home goals)
    for u, name, h, a in [("kevinb", "Kevin", 2, 0), ("fonserate", "Sandra", 2, 1)]:
        session.add(Participant(username=u, display_name=name))
        session.add(Prediction(match_id=match.id, username=u, pred_home=h, pred_away=a))
    session.commit()
    return match


# --- Parser ---------------------------------------------------------------

def test_parse_games_maps_api_shape():
    raw = [
        {
            "id": "1", "home_score": "2", "away_score": "0", "finished": "TRUE",
            "time_elapsed": "FT", "home_team_name_en": "Mexico",
            "away_team_name_en": "South Africa", "type": "group",
        },
        {
            "id": "2", "home_score": "0", "away_score": "0", "finished": "FALSE",
            "time_elapsed": "notstarted", "home_team_name_en": "Canada",
            "away_team_name_en": "Wales", "type": "group",
        },
    ]
    g1, g2 = parse_games(raw)
    assert (g1.provider_match_id, g1.home_score, g1.away_score) == ("1", 2, 0)
    assert g1.finished and g1.started
    assert g2.home_score == 0 and not g2.started and not g2.finished


def test_parse_games_365_maps_api_shape():
    raw = [
        {  # ended
            "id": 4627866, "statusGroup": 4, "gameTime": 90.0,
            "homeCompetitor": {"name": "Mexico", "score": 2.0},
            "awayCompetitor": {"name": "South Africa", "score": 0.0},
        },
        {  # scheduled — score and gameTime use -1 as the "not started" sentinel
            "id": 4627857, "statusGroup": 2, "gameTime": -1.0,
            "homeCompetitor": {"name": "USA", "score": -1.0},
            "awayCompetitor": {"name": "Australia", "score": -1.0},
        },
        {  # live
            "id": 4627900, "statusGroup": 1, "gameTime": 30.0,
            "homeCompetitor": {"name": "Brazil", "score": 1.0},
            "awayCompetitor": {"name": "Morocco", "score": 0.0},
        },
    ]
    g1, g2, g3 = parse_games_365(raw)
    assert (g1.provider_match_id, g1.home_score, g1.away_score, g1.minute) == ("4627866", 2, 0, 90)
    assert g1.finished and g1.started
    assert g2.home_score is None and g2.minute is None and not g2.started and not g2.finished
    assert (g3.home_score, g3.minute) == (1, 30)
    assert g3.started and not g3.finished


def test_team_aliases_match_scores365_naming():
    # Spanish names whose English form differs from a plain accent-strip — confirm
    # they resolve to exactly what 365scores reports (verified against the live API).
    assert normalize_team("Estados Unidos") == normalize_team("USA")
    assert normalize_team("Turquía") == normalize_team("Turkiye")
    assert normalize_team("República Checa") == normalize_team("Czechia")
    assert normalize_team("Bosnia y Herzegovina") == normalize_team("Bosnia & Herzegovina")


# --- poll_once: auto-link by name, set scores/status ----------------------

def test_poll_links_by_name_and_updates_live(session):
    match = _seed_mexico_match(session)
    provider = FakeProvider([
        # Accent/name mismatch on purpose: "Mexico" vs stored "México".
        ProviderGame("99", "Mexico", "South Africa", 1, 0, 30, started=True, finished=False),
    ])

    assert poll_once(session, provider) == 1
    session.refresh(match)
    assert match.provider_match_id == "99"  # linked
    assert (match.home_score, match.away_score) == (1, 0)
    assert match.status == MatchStatus.LIVE


def test_live_standings_change_then_finalize(session):
    _seed_mexico_match(session)

    # Live 1-0: kevinb(2-0) -> result 5 + away goals 2 = 7;
    #           fonserate(2-1) -> result 5 + goal difference 1 = 6.
    poll_once(session, FakeProvider([
        ProviderGame("99", "Mexico", "South Africa", 1, 0, 30, started=True, finished=False),
    ]))
    pts = {r.username: r.total_points for r in compute_standings(session)}
    assert pts == {"kevinb": 7, "fonserate": 6}

    # Final 2-0: kevinb exact -> 10; fonserate result+home -> 7.
    poll_once(session, FakeProvider([
        ProviderGame("99", "Mexico", "South Africa", 2, 0, 90, started=True, finished=True),
    ]))
    standings = compute_standings(session)
    assert [r.username for r in standings] == ["kevinb", "fonserate"]
    assert {r.username: r.total_points for r in standings} == {"kevinb": 10, "fonserate": 7}
    assert session.scalar(select(Match)).status == MatchStatus.FINISHED


# --- live window gate -----------------------------------------------------

def test_has_live_window(session):
    kickoff = dt.datetime(2026, 6, 11, 19, 0)
    session.add(Match(stage=Stage.GROUP, home_team="A", away_team="B",
                      kickoff_utc=kickoff, status=MatchStatus.SCHEDULED))
    session.commit()
    assert has_live_window(session, now=kickoff + dt.timedelta(hours=1)) is True   # mid-game
    assert has_live_window(session, now=kickoff + dt.timedelta(hours=5)) is False  # long over
    assert has_live_window(session, now=kickoff - dt.timedelta(hours=2)) is False  # too early
