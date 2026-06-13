"""Tests for the persistence path (save_predictions), no OCR/network involved."""

import datetime as dt

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.ingest import save_predictions
from app.models import Base, Match, Prediction
from app.schemas import ConfirmIn, PredictionIn
from app.scoring import Stage


@pytest.fixture
def session():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, future=True)()
    yield s
    s.close()


def _payload(**overrides):
    base = dict(
        home_team="México",
        away_team="Sudáfrica",
        kickoff_utc=dt.datetime(2026, 6, 11, 19, 0),
        stage=Stage.GROUP,
        predictions=[
            PredictionIn(username="kevinb", display_name="Kevin Borda", pred_home=2, pred_away=0),
            PredictionIn(username="oasilv", display_name="Orlando Silva", pred_home=2, pred_away=0),
        ],
    )
    base.update(overrides)
    return ConfirmIn(**base)


def test_save_creates_match_participants_predictions(session):
    save_predictions(session, _payload())

    assert session.scalar(select(Match)) is not None
    preds = session.scalars(select(Prediction)).all()
    assert len(preds) == 2
    assert {p.username for p in preds} == {"kevinb", "oasilv"}


def test_reconfirm_is_idempotent_and_updates(session):
    save_predictions(session, _payload())
    # Re-confirm same match, but kevinb corrected to 3-1 and stage fixed to knockout.
    save_predictions(
        session,
        _payload(
            stage=Stage.KNOCKOUT,
            predictions=[
                PredictionIn(username="kevinb", display_name="Kevin Borda", pred_home=3, pred_away=1),
                PredictionIn(username="oasilv", display_name="Orlando Silva", pred_home=2, pred_away=0),
            ],
        ),
    )

    matches = session.scalars(select(Match)).all()
    assert len(matches) == 1  # no duplicate match
    assert matches[0].stage == Stage.KNOCKOUT
    preds = session.scalars(select(Prediction)).all()
    assert len(preds) == 2  # no duplicate predictions
    kevin = session.scalar(select(Prediction).where(Prediction.username == "kevinb"))
    assert (kevin.pred_home, kevin.pred_away) == (3, 1)
