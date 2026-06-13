"""Page-access / engagement tracking.

A device gets an anonymous `client_id` cookie; when the person picks who they are,
a `username` cookie is added and attached to their visits. The browser reports
active time-on-page, which we store per visit. Pure-ish functions (take a Session)
so they're unit-testable.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PageVisit


def start_visit(
    session: Session,
    client_id: str,
    username: str | None,
    path: str,
    user_agent: str | None,
) -> PageVisit:
    visit = PageVisit(
        client_id=client_id,
        username=username,
        path=path[:128],
        user_agent=(user_agent or "")[:256] or None,
    )
    session.add(visit)
    session.commit()
    return visit


def ping_visit(session: Session, visit_id: int, seconds: int) -> bool:
    """Update active time-on-page. Idempotent: keeps the largest reported value
    (beacons can arrive out of order or be retried)."""
    visit = session.get(PageVisit, visit_id)
    if visit is None:
        return False
    visit.seconds = max(visit.seconds, seconds)
    visit.last_seen = dt.datetime.utcnow()
    session.commit()
    return True


def compute_engagement(session: Session) -> list[dict]:
    """Per-identity engagement: visits, total + average active seconds, last seen.
    Anonymous visits (no username yet) are grouped under 'anónimo'."""
    rows = session.execute(
        select(
            PageVisit.username,
            func.count(PageVisit.id),
            func.coalesce(func.sum(PageVisit.seconds), 0),
            func.max(PageVisit.last_seen),
        ).group_by(PageVisit.username)
    ).all()

    out = []
    for username, visits, total_seconds, last_seen in rows:
        total_seconds = int(total_seconds)
        out.append(
            {
                "username": username or "anónimo",
                "visits": visits,
                "total_seconds": total_seconds,
                "avg_seconds": round(total_seconds / visits, 1) if visits else 0.0,
                "last_seen": (last_seen.isoformat() + "Z") if last_seen else None,
            }
        )
    return sorted(out, key=lambda r: r["total_seconds"], reverse=True)
