"""Live-score polling: apply a provider's game state to our matches.

`poll_once` is pure-ish (takes a session + provider), so it's unit-tested with a
fake provider and no network. The scheduler wrapper (started from main.py) calls
it on an interval, but only inside a live window to respect free-API rate limits.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Match, MatchStatus
from app.scores.base import ScoreProvider, normalize_team

log = logging.getLogger("polla.poller")

# How wide a window around kickoff counts as "worth polling".
PRE_KICKOFF = dt.timedelta(minutes=15)
POST_KICKOFF = dt.timedelta(hours=3)


def poll_once(session: Session, provider: ScoreProvider) -> int:
    """Fetch provider games and update matching DB matches. Returns # updated.

    Matches are linked by stored provider_match_id, or auto-linked by team-name
    pair the first time (and the id is persisted so later polls are direct).
    """
    games = provider.fetch_games()
    by_id = {g.provider_match_id: g for g in games}
    by_name = {(normalize_team(g.home_team), normalize_team(g.away_team)): g for g in games}

    updated = 0
    for match in session.scalars(select(Match)).all():
        game = None
        if match.provider_match_id and match.provider_match_id in by_id:
            game = by_id[match.provider_match_id]
        else:
            game = by_name.get((normalize_team(match.home_team), normalize_team(match.away_team)))
            if game is not None:
                match.provider_match_id = game.provider_match_id  # persist the link

        if game is None:
            continue
        if not (game.started or game.finished):
            continue  # not started yet — keep it scheduled, don't write a 0-0

        match.home_score = game.home_score
        match.away_score = game.away_score
        match.status = MatchStatus.FINISHED if game.finished else MatchStatus.LIVE
        match.score_updated_at = dt.datetime.utcnow()
        updated += 1

    session.commit()
    return updated


def has_live_window(session: Session, now: dt.datetime | None = None) -> bool:
    """True if any non-finished match is near kickoff — gate to avoid idle polling."""
    now = now or dt.datetime.utcnow()
    lo, hi = now - POST_KICKOFF, now + PRE_KICKOFF
    match = session.scalar(
        select(Match).where(
            Match.status != MatchStatus.FINISHED,
            Match.kickoff_utc >= lo,
            Match.kickoff_utc <= hi,
        )
    )
    return match is not None
