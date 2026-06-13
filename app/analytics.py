"""Analytics / KPIs over accumulated data.

Computed only over FINISHED matches (settled results), so figures don't flicker
during live games. Everything is derived from the same scoring engine, so the
numbers always agree with the standings.

Pure functions (take a Session) — unit-tested with SQLite, no network.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Match, MatchStatus, Prediction
from app.scoring import score_prediction


def _finished_matches(session: Session) -> dict[int, Match]:
    return {
        m.id: m
        for m in session.scalars(select(Match).where(Match.status == MatchStatus.FINISHED)).all()
        if m.home_score is not None and m.away_score is not None
    }


@dataclass
class PlayerStats:
    username: str
    display_name: str
    played: int = 0
    points: int = 0
    exact: int = 0            # predicted the exact score
    correct_result: int = 0   # got the W/D/L outcome right
    best: int = 0             # most points in a single match
    from_result: int = 0      # points attributable to each component
    from_goals: int = 0
    from_gd: int = 0
    _per_match: list[int] = field(default_factory=list, repr=False)

    @property
    def avg(self) -> float:
        return round(self.points / self.played, 2) if self.played else 0.0

    @property
    def exact_rate(self) -> float:
        return round(self.exact / self.played, 3) if self.played else 0.0

    @property
    def result_rate(self) -> float:
        return round(self.correct_result / self.played, 3) if self.played else 0.0

    @property
    def consistency(self) -> float:
        """Std-dev of per-match points (lower = steadier). 0 with <2 matches."""
        return round(statistics.pstdev(self._per_match), 2) if len(self._per_match) > 1 else 0.0

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "display_name": self.display_name,
            "played": self.played,
            "points": self.points,
            "avg": self.avg,
            "exact": self.exact,
            "exact_rate": self.exact_rate,
            "correct_result": self.correct_result,
            "result_rate": self.result_rate,
            "best": self.best,
            "from_result": self.from_result,
            "from_goals": self.from_goals,
            "from_gd": self.from_gd,
            "consistency": self.consistency,
        }


def compute_player_stats(session: Session) -> list[PlayerStats]:
    matches = _finished_matches(session)
    if not matches:
        return []

    stats: dict[str, PlayerStats] = {}
    preds = session.scalars(
        select(Prediction).where(Prediction.match_id.in_(matches.keys()))
    ).all()

    for pred in preds:
        m = matches[pred.match_id]
        b = score_prediction(pred.pred_home, pred.pred_away, m.home_score, m.away_score, m.stage)
        s = stats.get(pred.username)
        if s is None:
            s = PlayerStats(pred.username, pred.participant.display_name)
            stats[pred.username] = s
        s.played += 1
        s.points += b.total
        s.from_result += b.result
        s.from_goals += b.home_goals + b.away_goals
        s.from_gd += b.goal_difference
        s.best = max(s.best, b.total)
        s._per_match.append(b.total)
        if pred.pred_home == m.home_score and pred.pred_away == m.away_score:
            s.exact += 1
        if b.result > 0:
            s.correct_result += 1

    return sorted(stats.values(), key=lambda s: (-s.points, s.username))


@dataclass
class MatchStats:
    match_id: int
    label: str
    score: str
    stage: str
    predictors: int
    avg_points: float
    exact_count: int

    def to_dict(self) -> dict:
        return self.__dict__


def compute_match_stats(session: Session) -> list[MatchStats]:
    matches = _finished_matches(session)
    out: list[MatchStats] = []
    for m in matches.values():
        preds = session.scalars(
            select(Prediction).where(Prediction.match_id == m.id)
        ).all()
        if not preds:
            continue
        totals = [
            score_prediction(p.pred_home, p.pred_away, m.home_score, m.away_score, m.stage).total
            for p in preds
        ]
        exact = sum(
            1 for p in preds if p.pred_home == m.home_score and p.pred_away == m.away_score
        )
        out.append(
            MatchStats(
                match_id=m.id,
                label=f"{m.home_team} vs {m.away_team}",
                score=f"{m.home_score}-{m.away_score}",
                stage=m.stage.value,
                predictors=len(preds),
                avg_points=round(sum(totals) / len(totals), 2),
                exact_count=exact,
            )
        )
    return sorted(out, key=lambda x: x.match_id)


def compute_highlights(session: Session) -> dict:
    """Headline KPIs. Returns an empty-ish dict when there's no settled data yet."""
    players = compute_player_stats(session)
    matches = compute_match_stats(session)
    if not players:
        return {"finished_matches": 0, "predictions_scored": 0}

    finished = len(matches)
    # Accuracy/consistency leaders need enough games to be meaningful.
    min_played = max(1, finished // 2)
    eligible = [p for p in players if p.played >= min_played] or players

    sharpest = max(eligible, key=lambda p: (p.exact_rate, p.played))
    steady_pool = [p for p in eligible if p.played > 1]
    most_consistent = (
        min(steady_pool, key=lambda p: (p.consistency, -p.avg)) if steady_pool else None
    )
    best_single = max(players, key=lambda p: p.best)
    toughest = min(matches, key=lambda m: m.avg_points) if matches else None
    easiest = max(matches, key=lambda m: m.avg_points) if matches else None

    def player_card(p: PlayerStats, value) -> dict:
        return {"username": p.username, "display_name": p.display_name, "value": value}

    return {
        "finished_matches": finished,
        "predictions_scored": sum(p.played for p in players),
        "leader": player_card(players[0], players[0].points),
        "sharpest": player_card(sharpest, sharpest.exact_rate),
        "most_consistent": (
            player_card(most_consistent, most_consistent.consistency) if most_consistent else None
        ),
        "best_single_match": player_card(best_single, best_single.best),
        "toughest_match": toughest.to_dict() if toughest else None,
        "easiest_match": easiest.to_dict() if easiest else None,
    }
