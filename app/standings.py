"""Standings computation — ties the scoring engine to stored data.

This is what the live table calls. Because points are computed here (not stored),
calling it again after the live score updates yields the new standings for free.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Match, MatchStatus, Prediction
from app.scoring import score_prediction


@dataclass
class StandingRow:
    username: str
    display_name: str
    total_points: int = 0
    matches_scored: int = 0
    # Points earned per match id, so the UI can show a live delta per game.
    per_match: dict[int, int] = field(default_factory=dict)


def assign_ranks(points_desc: list[int]) -> list[int]:
    """Competition ranking (1-2-2-4 style): equal points share the same position,
    and the next distinct value skips accordingly. e.g. [20,20,16] -> [1,1,3]."""
    ranks: list[int] = []
    for i, p in enumerate(points_desc):
        if i > 0 and p == points_desc[i - 1]:
            ranks.append(ranks[-1])
        else:
            ranks.append(i + 1)
    return ranks


def compute_standings(
    session: Session,
    statuses: set[MatchStatus] | None = None,
    exclude_match_ids: set[int] | None = None,
) -> list[StandingRow]:
    """Return participants ranked by total points. By default counts every scored
    match (LIVE or FINISHED); pass `statuses={FINISHED}` for the pre-live baseline.
    Ties are broken by username for stability.
    """
    include = statuses or {MatchStatus.LIVE, MatchStatus.FINISHED}
    exclude = exclude_match_ids or set()
    matches = {
        m.id: m
        for m in session.scalars(select(Match)).all()
        if m.status in include
        and m.home_score is not None
        and m.away_score is not None
        and m.id not in exclude
    }
    if not matches:
        return []

    rows: dict[str, StandingRow] = {}
    predictions = session.scalars(
        select(Prediction).where(Prediction.match_id.in_(matches.keys()))
    ).all()

    for pred in predictions:
        match = matches[pred.match_id]
        pts = score_prediction(
            pred.pred_home, pred.pred_away, match.home_score, match.away_score, match.stage
        ).total

        row = rows.get(pred.username)
        if row is None:
            row = StandingRow(
                username=pred.username,
                display_name=pred.participant.display_name,
            )
            rows[pred.username] = row
        row.total_points += pts
        row.matches_scored += 1
        row.per_match[pred.match_id] = pts

    return sorted(rows.values(), key=lambda r: (-r.total_points, r.username))


def compute_live_board(session: Session) -> dict:
    """Standings with movement caused by the LAST match (live or, if none is live,
    the most recent finished one): each row carries total points, position change
    from before that match to now, the user's prediction for it, and the points it
    contributed. This is the same info shown live, generalized to "since the
    previous match → the last one".
    """
    current = compute_standings(session)  # all scored (live + finished)
    if not current:
        return {"match": None, "rows": []}

    scored = [
        m
        for m in session.scalars(select(Match)).all()
        if m.status in (MatchStatus.LIVE, MatchStatus.FINISHED)
        and m.home_score is not None
        and m.away_score is not None
    ]
    reference = max(scored, key=lambda m: m.kickoff_utc) if scored else None

    # Points each user earned in the reference (last) match, and their prediction.
    ref_points: dict[str, int] = {}
    pred_map: dict[str, Prediction] = {}
    if reference is not None:
        for p in session.scalars(
            select(Prediction).where(Prediction.match_id == reference.id)
        ).all():
            ref_points[p.username] = score_prediction(
                p.pred_home, p.pred_away, reference.home_score, reference.away_score, reference.stage
            ).total
            pred_map[p.username] = p

    # Current ranks, and baseline ranks as if the reference match hadn't happened.
    cur_ranks = assign_ranks([r.total_points for r in current])
    current_rank = {r.username: cur_ranks[i] for i, r in enumerate(current)}

    baseline_order = sorted(
        current, key=lambda r: (-(r.total_points - ref_points.get(r.username, 0)), r.username)
    )
    base_ranks = assign_ranks(
        [r.total_points - ref_points.get(r.username, 0) for r in baseline_order]
    )
    baseline_rank = {r.username: base_ranks[i] for i, r in enumerate(baseline_order)}

    rows = []
    for r in current:
        cur_rank = current_rank[r.username]
        prev_rank = baseline_rank[r.username]
        pred = pred_map.get(r.username)
        rows.append(
            {
                "rank": cur_rank,
                "prev_rank": prev_rank,
                "delta": prev_rank - cur_rank,  # >0 subió, <0 bajó, 0 se mantiene
                "username": r.username,
                "display_name": r.display_name,
                "points": r.total_points,
                "live_points": ref_points.get(r.username, 0),
                "pred_home": pred.pred_home if pred else None,
                "pred_away": pred.pred_away if pred else None,
            }
        )

    match_brief = None
    if reference is not None:
        match_brief = {
            "id": reference.id,
            "home_team": reference.home_team,
            "away_team": reference.away_team,
            "home_score": reference.home_score,
            "away_score": reference.away_score,
            "status": reference.status.value,
        }
    return {"match": match_brief, "rows": rows}
