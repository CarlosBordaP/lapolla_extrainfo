"""Persist reviewed predictions into the DB (idempotent).

Kept separate from the OCR call and the HTTP layer so it can be unit-tested with
a plain SQLite session. Re-running with the same match upserts rather than
duplicating — safe to confirm the same screenshot twice.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Match, MatchFile, MatchStatus, Participant, Prediction
from app.schemas import ConfirmIn, PredictionIn


def save_match_predictions(
    session: Session,
    match: Match,
    predictions: list[PredictionIn],
    upload_id: str | None = None,
) -> Match:
    """Upsert predictions for an EXISTING match, link the screenshot, lock the
    match (so it can't be re-uploaded), and commit. Shared by both upload paths."""
    now = dt.datetime.utcnow()
    for p in predictions:
        participant = session.get(Participant, p.username)
        if participant is None:
            participant = Participant(username=p.username, display_name=p.display_name)
            session.add(participant)
        else:
            participant.display_name = p.display_name

        pred = session.scalar(
            select(Prediction).where(
                Prediction.match_id == match.id,
                Prediction.username == p.username,
            )
        )
        if pred is None:
            session.add(
                Prediction(
                    match_id=match.id,
                    username=p.username,
                    pred_home=p.pred_home,
                    pred_away=p.pred_away,
                    modified_at=now,
                )
            )
        else:
            pred.pred_home = p.pred_home
            pred.pred_away = p.pred_away
            pred.modified_at = now

    if upload_id:
        mf = session.scalar(select(MatchFile).where(MatchFile.upload_id == upload_id))
        if mf is not None:
            mf.match_id = match.id

    if predictions:
        match.locked = True  # processed — no further uploads for this match

    session.commit()
    return match


def save_predictions(session: Session, payload: ConfirmIn) -> Match:
    """Find-or-create the match (from teams + kickoff), then save predictions.
    Used by the generic/admin path that creates the fixture from the screenshot."""
    match = session.scalar(
        select(Match).where(
            Match.home_team == payload.home_team,
            Match.away_team == payload.away_team,
            Match.kickoff_utc == payload.kickoff_utc,
        )
    )
    if match is None:
        match = Match(
            home_team=payload.home_team,
            away_team=payload.away_team,
            kickoff_utc=payload.kickoff_utc,
            stage=payload.stage,
            status=MatchStatus.SCHEDULED,
        )
        session.add(match)
        session.flush()  # assign match.id
    else:
        match.stage = payload.stage  # allow correcting the stage on re-confirm

    return save_match_predictions(session, match, payload.predictions, payload.upload_id)
