"""FastAPI application entrypoint.

Phase 0: health + live standings.
Phase 1: prediction ingestion — OCR a screenshot, confirm/edit, save.
Phase 2: live scores — provider + background poller + manual override.
Phase 3 will add the live standings UI.
"""

from __future__ import annotations

import datetime as dt
import difflib
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.scores.worldcup_free  # noqa: F401 — registers the provider
from app.analytics import compute_highlights, compute_match_stats, compute_player_stats
from app.config import get_settings
from app.db import SessionLocal, get_session, init_db
from app.ingest import save_match_predictions, save_predictions
from app.matching import match_and_validate
from app.models import Match, MatchFile, MatchStatus, Participant, Prediction
from app.ocr import extract_predictions, extract_standings
from app.poller import has_live_window, poll_once
from app.schemas import (
    BulkMatchesIn,
    BulkParticipantsIn,
    ConfirmIn,
    FixtureIn,
    IdentifyIn,
    ManualScoreIn,
    MatchPredictionsIn,
    PredictionEditIn,
    ProviderLinkIn,
    UploadWindowIn,
    VisitPingIn,
    VisitStartIn,
)
from app.scores.base import get_provider
from app.scoring import score_prediction
from app.standings import assign_ranks, compute_live_board, compute_standings
from app.storage import save_prediction_files, save_upload_file
from app.tracking import compute_engagement, ping_visit, start_visit

_UID_COOKIE = "polla_uid"
_USER_COOKIE = "polla_user"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 180  # 180 days
LOCK_MINUTES = 10   # Golpredictor: predictions lock 10 min before kickoff
MATCH_MINUTES = 140  # wall-clock cap to consider an unscored match "ended"


def _current_user(request: Request) -> str | None:
    return request.cookies.get(_USER_COOKIE)


def _is_admin(request: Request) -> bool:
    user = _current_user(request)
    return bool(user and user in get_settings().admin_user_set)


def _as_naive_utc(d: dt.datetime) -> dt.datetime:
    """Normalize any datetime to naive UTC so comparisons never mix aware/naive."""
    if d.tzinfo is not None:
        d = d.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return d


def _iso_utc(d: dt.datetime) -> str:
    """Serialize a naive-UTC datetime WITH an explicit 'Z' so the browser parses
    it as UTC (without Z, JS reads it as local time and shows the wrong hour)."""
    return _as_naive_utc(d).isoformat() + "Z"


def _upload_state(m: Match, now: dt.datetime | None = None):
    """Upload window for a match: open from 10 min before kickoff UNTIL the match
    ends (status finished, or ~MATCH_MINUTES after kickoff as a safety cap).
    Returns (can_upload, open_at, state) where state is locked|early|open|closed."""
    now = now or dt.datetime.utcnow()
    kickoff = _as_naive_utc(m.kickoff_utc)
    open_at = kickoff - dt.timedelta(minutes=LOCK_MINUTES)
    ended = m.status == MatchStatus.FINISHED or now >= kickoff + dt.timedelta(minutes=MATCH_MINUTES)
    if m.locked:
        state = "locked"
    elif m.force_upload:  # admin override — open regardless of time
        state = "open"
    elif now < open_at:
        state = "early"
    elif ended:
        state = "closed"
    else:
        state = "open"
    return state == "open", open_at, state


def _ensure_upload_open(m: Match) -> None:
    """Raise the right HTTP error if the per-match upload window isn't open."""
    _, open_at, state = _upload_state(m)
    if state == "locked":
        raise HTTPException(status_code=409, detail="Este partido ya fue procesado.")
    if state == "early":
        raise HTTPException(
            status_code=403,
            detail=f"La subida se habilita 10 minutos antes del partido (a las {open_at.isoformat()}Z).",
        )
    if state == "closed":
        raise HTTPException(
            status_code=403,
            detail="La ventana de subida ya cerró (el partido ya terminó).",
        )


def _match_brief(m: Match, kind: str | None = None) -> dict:
    can_upload, open_at, upload_state = _upload_state(m)
    return {
        "kind": kind,
        "id": m.id,
        "home_team": m.home_team,
        "away_team": m.away_team,
        "stage": m.stage.value,
        "status": m.status.value,
        "home_score": m.home_score,
        "away_score": m.away_score,
        "kickoff_utc": _iso_utc(m.kickoff_utc),
        "score_updated_at": _iso_utc(m.score_updated_at) if m.score_updated_at else None,
        "locked": m.locked,
        "can_upload": can_upload,
        "upload_open_at": _iso_utc(open_at),
        "upload_state": upload_state,
    }

log = logging.getLogger("polla")

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
_scheduler: BackgroundScheduler | None = None


def _scheduled_poll() -> None:
    """Background job: pull live scores only during the live window around a match.
    The scheduler always fires every score_poll_seconds, but the API is only called
    when a match is within PRE_KICKOFF..POST_KICKOFF of now — protecting free-tier limits."""
    session = SessionLocal()
    try:
        if not has_live_window(session):
            return  # no match nearby — skip API call
        settings = get_settings()
        provider = get_provider(settings.score_provider)
        updated = poll_once(session, provider)
        log.info("poll: updated %d matches", updated)
    except Exception:  # never let a poll failure kill the scheduler
        log.exception("score poll failed")
    finally:
        session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    init_db()  # local-dev convenience; production uses migrations
    settings = get_settings()
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(_scheduled_poll, "interval", seconds=settings.score_poll_seconds)
    _scheduler.start()
    try:
        yield
    finally:
        _scheduler.shutdown(wait=False)


app = FastAPI(title="Polla — World Cup live standings", lifespan=lifespan)


@app.middleware("http")
async def ensure_device_id(request: Request, call_next):
    """Assign an anonymous device id cookie so we can group a person's visits."""
    uid = request.cookies.get(_UID_COOKIE)
    is_new = uid is None
    if is_new:
        uid = uuid.uuid4().hex
    request.state.uid = uid
    response = await call_next(request)
    if is_new:
        response.set_cookie(
            _UID_COOKIE, uid, max_age=_COOKIE_MAX_AGE, samesite="lax", httponly=True
        )
    # Always serve fresh UI/JS/CSS — avoids stale pages from browser caching.
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# --- Access tracking (engagement analytics) ----------------------------------

@app.get("/track/participants")
def track_participants(session: Session = Depends(get_session)) -> list[dict]:
    """Roster for the 'who are you?' picker."""
    rows = session.scalars(select(Participant).order_by(Participant.display_name)).all()
    return [
        {
            "username": p.username,
            "display_name": p.display_name,
            "registered_at": _iso_utc(p.registered_at) if p.registered_at else None,
        }
        for p in rows
    ]


@app.post("/participants/bulk")
def bulk_participants(
    payload: BulkParticipantsIn, request: Request, session: Session = Depends(get_session)
) -> dict:
    """Preload the pool's participants (admin). Idempotent: upserts display names."""
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="admin only")
    created = updated = 0
    for p in payload.participants:
        reg = _as_naive_utc(p.registered_at) if p.registered_at else None
        existing = session.get(Participant, p.username)
        if existing is None:
            session.add(
                Participant(username=p.username, display_name=p.display_name, registered_at=reg)
            )
            created += 1
        else:
            existing.display_name = p.display_name
            if reg is not None:
                existing.registered_at = reg
            updated += 1
    session.commit()
    return {"created": created, "updated": updated, "total": created + updated}


@app.post("/track/identify")
def track_identify(
    payload: IdentifyIn, response: Response, session: Session = Depends(get_session)
) -> dict:
    """Bind this device to a participant (sets the readable polla_user cookie)."""
    if session.get(Participant, payload.username) is None:
        raise HTTPException(status_code=404, detail="unknown participant")
    response.set_cookie(_USER_COOKIE, payload.username, max_age=_COOKIE_MAX_AGE, samesite="lax")
    return {"username": payload.username}


@app.post("/track/visit/start")
def track_visit_start(
    payload: VisitStartIn, request: Request, session: Session = Depends(get_session)
) -> dict:
    visit = start_visit(
        session,
        client_id=request.state.uid,
        username=request.cookies.get(_USER_COOKIE),
        path=payload.path,
        user_agent=request.headers.get("user-agent"),
    )
    return {"visit_id": visit.id}


@app.post("/track/visit/ping")
def track_visit_ping(payload: VisitPingIn, session: Session = Depends(get_session)) -> dict:
    ok = ping_visit(session, payload.visit_id, payload.seconds)
    return {"ok": ok}


# --- Prediction ingestion (Phase 1) -----------------------------------------

@app.post("/predictions/ingest")
async def ingest(
    file: UploadFile = File(...), session: Session = Depends(get_session)
) -> dict:
    image_bytes = await file.read()
    media_type = file.content_type or "image/jpeg"
    try:
        parsed = extract_predictions(image_bytes, media_type=media_type)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        log.exception("OCR inesperado: %s", e)
        raise HTTPException(status_code=503, detail=f"OCR falló: {type(e).__name__}: {e}")

    # Persist the screenshot (linked to the match later, on confirm via upload_id).
    upload_id, stored_path = save_upload_file(image_bytes, media_type)
    session.add(
        MatchFile(
            upload_id=upload_id,
            original_name=file.filename,
            content_type=media_type,
            stored_path=stored_path,
        )
    )
    session.commit()

    result = parsed.to_dict()
    result["upload_id"] = upload_id
    return result


@app.post("/predictions/confirm")
def confirm(payload: ConfirmIn, session: Session = Depends(get_session)) -> dict:
    match = save_predictions(session, payload)
    return {"match_id": match.id, "saved": len(payload.predictions)}


# --- Live scores (Phase 2) ---------------------------------------------------

@app.get("/matches")
def list_matches(session: Session = Depends(get_session)) -> list[dict]:
    return [
        {**_match_brief(m), "provider_match_id": m.provider_match_id}
        for m in session.scalars(select(Match).order_by(Match.kickoff_utc)).all()
    ]


@app.post("/matches")
def create_fixture(
    payload: FixtureIn, request: Request, session: Session = Depends(get_session)
) -> dict:
    """Create a calendar fixture ahead of time (admin-only)."""
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="admin only")
    m = Match(
        home_team=payload.home_team,
        away_team=payload.away_team,
        kickoff_utc=_as_naive_utc(payload.kickoff_utc),
        stage=payload.stage,
        status=MatchStatus.SCHEDULED,
    )
    session.add(m)
    session.commit()
    return _match_brief(m)


@app.post("/matches/bulk")
def bulk_create_fixtures(
    payload: BulkMatchesIn, request: Request, session: Session = Depends(get_session)
) -> dict:
    """Load many fixtures at once (admin). Skips matches that already exist
    (same home + away + kickoff), so it's safe to re-run."""
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="admin only")
    created = skipped = 0
    for fx in payload.matches:
        ko = _as_naive_utc(fx.kickoff_utc)
        exists = session.scalar(
            select(Match).where(
                Match.home_team == fx.home_team,
                Match.away_team == fx.away_team,
                Match.kickoff_utc == ko,
            )
        )
        if exists is not None:
            skipped += 1
            continue
        session.add(
            Match(
                home_team=fx.home_team,
                away_team=fx.away_team,
                kickoff_utc=ko,
                stage=fx.stage,
                status=MatchStatus.SCHEDULED,
            )
        )
        created += 1
    session.commit()
    return {"created": created, "skipped": skipped, "total": created + skipped}


@app.post("/matches/{match_id}/upload-window")
def set_upload_window(
    match_id: int, payload: UploadWindowIn, request: Request,
    session: Session = Depends(get_session),
) -> dict:
    """Admin override to force a match's upload window open (e.g. to test, or to
    re-enable a closed match)."""
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="admin only")
    match = session.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="match not found")
    match.force_upload = payload.open
    session.commit()
    return _match_brief(match)


@app.post("/matches/{match_id}/predictions/ingest")
async def match_predictions_ingest(
    match_id: int,
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict:
    """OCR a predictions screenshot for a specific match. Enforces the 10-min
    window and the single-processing lock before spending any OCR. Matches each
    row to a stored participant and validates against the full roster."""
    match = session.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="match not found")
    _ensure_upload_open(match)

    image_bytes = await file.read()
    media_type = file.content_type or "image/jpeg"
    try:
        parsed = extract_predictions(image_bytes, media_type=media_type)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        log.exception("OCR inesperado: %s", e)
        raise HTTPException(status_code=503, detail=f"OCR falló: {type(e).__name__}: {e}")

    # Save the screenshot AND the OCR CSV into uploads/<id>.<Home>-<Away>/.
    upload_id, image_path, _csv_path = save_prediction_files(
        match, image_bytes, media_type, parsed.raw
    )
    session.add(
        MatchFile(
            match_id=match.id,
            upload_id=upload_id,
            original_name=file.filename,
            content_type=media_type,
            stored_path=image_path,
        )
    )
    session.commit()

    # Match rows to the roster + validate completeness + attribute the uploader's top.
    participants = [
        (p.username, p.display_name)
        for p in session.scalars(select(Participant).order_by(Participant.display_name)).all()
    ]
    top = (
        {"pred_home": parsed.top_home, "pred_away": parsed.top_away}
        if parsed.top_home is not None
        else None
    )
    matched = match_and_validate(parsed.predictions, top, participants, _current_user(request))

    return {
        "home_team": parsed.home_team,
        "away_team": parsed.away_team,
        "kickoff_text": parsed.kickoff_text,
        "raw_csv": parsed.raw,
        "upload_id": upload_id,
        **matched,  # predictions (resolved), top, validation
    }


@app.post("/matches/{match_id}/predictions/confirm")
def match_predictions_confirm(
    match_id: int, payload: MatchPredictionsIn, session: Session = Depends(get_session)
) -> dict:
    """Save reviewed predictions for a match and lock it (no further uploads)."""
    match = session.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="match not found")
    _ensure_upload_open(match)
    save_match_predictions(session, match, payload.predictions, payload.upload_id)
    return {"match_id": match.id, "saved": len(payload.predictions), "locked": match.locked}


@app.get("/matches/files/{file_id}")
def match_file(file_id: int, session: Session = Depends(get_session)) -> FileResponse:
    """Serve a stored OCR screenshot. (Declared before /matches/{id} so 'files'
    isn't parsed as a match id.)"""
    mf = session.get(MatchFile, file_id)
    if mf is None or not os.path.exists(mf.stored_path):
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(mf.stored_path, media_type=mf.content_type)


@app.get("/matches/{match_id}")
def match_detail(match_id: int, request: Request, session: Session = Depends(get_session)) -> dict:
    """Full detail for one match: result, source OCR images, and every prediction
    (with points once the match has a score)."""
    m = session.get(Match, match_id)
    if m is None:
        raise HTTPException(status_code=404, detail="match not found")

    scored = m.home_score is not None and m.away_score is not None
    preds_by_user = {
        p.username: p
        for p in session.scalars(select(Prediction).where(Prediction.match_id == match_id)).all()
    }
    all_participants = session.scalars(select(Participant).order_by(Participant.display_name)).all()

    # Cumulative points per participant through this match (inclusive), for the
    # "Acumulado" audit column — only meaningful once the match is finished.
    cumulative_by_user: dict[str, int] = {}
    if m.status == MatchStatus.FINISHED:
        earlier_matches = [
            em for em in session.scalars(
                select(Match)
                .where(Match.status == MatchStatus.FINISHED, Match.kickoff_utc <= m.kickoff_utc)
                .order_by(Match.kickoff_utc)
            ).all()
            if em.home_score is not None and em.away_score is not None
        ]
        preds_by_match: dict[int, list[Prediction]] = {}
        for p in session.scalars(
            select(Prediction).where(Prediction.match_id.in_([em.id for em in earlier_matches]))
        ).all():
            preds_by_match.setdefault(p.match_id, []).append(p)
        for em in earlier_matches:
            for p in preds_by_match.get(em.id, []):
                pts = score_prediction(p.pred_home, p.pred_away, em.home_score, em.away_score, em.stage).total
                cumulative_by_user[p.username] = cumulative_by_user.get(p.username, 0) + pts

    preds = []
    for participant in all_participants:
        p = preds_by_user.get(participant.username)
        if p is not None:
            pts = (
                score_prediction(p.pred_home, p.pred_away, m.home_score, m.away_score, m.stage).total
                if scored
                else None
            )
            preds.append({
                "username": p.username,
                "display_name": participant.display_name,
                "pred_home": p.pred_home,
                "pred_away": p.pred_away,
                "points": pts,
                "cumulative": cumulative_by_user.get(participant.username),
                "has_prediction": True,
            })
        else:
            preds.append({
                "username": participant.username,
                "display_name": participant.display_name,
                "pred_home": None,
                "pred_away": None,
                "points": None,
                "cumulative": cumulative_by_user.get(participant.username),
                "has_prediction": False,
            })

    preds.sort(key=lambda x: (
        0 if x["has_prediction"] else 1,
        -(x["points"] if x["points"] is not None else -1) if x["has_prediction"] else 0,
        x["display_name"],
    ))

    files = session.scalars(select(MatchFile).where(MatchFile.match_id == match_id)).all()
    return {
        "match": _match_brief(m),
        "files": [
            {"id": f.id, "url": f"/matches/files/{f.id}", "content_type": f.content_type,
             "original_name": f.original_name}
            for f in files
        ],
        "predictions": preds,
        "prediction_count": sum(1 for p in preds if p["has_prediction"]),
        "participant_count": len(preds),
        "is_admin": _is_admin(request),
        "manual_score_enabled": get_settings().manual_score_enabled,
    }


@app.post("/matches/{match_id}/prediction-edit")
def edit_prediction(
    match_id: int, payload: PredictionEditIn, request: Request,
    session: Session = Depends(get_session),
) -> dict:
    """Admin correction of one user's prediction (e.g. OCR misread). Works even on
    a locked match."""
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="admin only")
    if session.get(Match, match_id) is None:
        raise HTTPException(status_code=404, detail="match not found")
    if session.get(Participant, payload.username) is None:
        raise HTTPException(status_code=404, detail="unknown participant")

    pred = session.scalar(
        select(Prediction).where(
            Prediction.match_id == match_id, Prediction.username == payload.username
        )
    )
    now = dt.datetime.utcnow()
    if pred is None:
        session.add(Prediction(
            match_id=match_id, username=payload.username,
            pred_home=payload.pred_home, pred_away=payload.pred_away, modified_at=now,
        ))
    else:
        pred.pred_home = payload.pred_home
        pred.pred_away = payload.pred_away
        pred.modified_at = now
    session.commit()
    return {
        "match_id": match_id, "username": payload.username,
        "pred_home": payload.pred_home, "pred_away": payload.pred_away,
    }


@app.post("/matches/{match_id}/score")
def set_score(
    match_id: int, payload: ManualScoreIn, request: Request,
    session: Session = Depends(get_session),
) -> dict:
    """Manual score override — admin only, requires MANUAL_SCORE_ENABLED=true."""
    if not get_settings().manual_score_enabled:
        raise HTTPException(status_code=403, detail="Entrada manual de marcadores deshabilitada.")
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="admin only")
    match = session.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="match not found")
    match.home_score = payload.home_score
    match.away_score = payload.away_score
    match.status = MatchStatus.FINISHED if payload.finished else MatchStatus.LIVE
    match.score_updated_at = dt.datetime.utcnow()
    session.commit()
    return {"match_id": match.id, "status": match.status.value}


@app.post("/matches/{match_id}/link")
def link_match(
    match_id: int, payload: ProviderLinkIn, session: Session = Depends(get_session)
) -> dict:
    """Manually link a match to a provider game id (covers untranslated team pairs)."""
    match = session.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="match not found")
    match.provider_match_id = payload.provider_match_id
    session.commit()
    return {"match_id": match.id, "provider_match_id": match.provider_match_id}


@app.get("/scores/games")
def provider_games() -> list[dict]:
    """List the provider's current games — use to pick an id for manual linking."""
    settings = get_settings()
    try:
        provider = get_provider(settings.score_provider)
        games = provider.fetch_games()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"provider error: {e}")
    return [
        {
            "provider_match_id": g.provider_match_id,
            "home_team": g.home_team,
            "away_team": g.away_team,
            "home_score": g.home_score,
            "away_score": g.away_score,
            "minute": g.minute,
            "started": g.started,
            "finished": g.finished,
        }
        for g in games
    ]


@app.post("/scores/refresh")
def refresh_scores(session: Session = Depends(get_session)) -> dict:
    """Trigger one poll now (also auto-links matches to provider IDs by team name)."""
    settings = get_settings()
    try:
        provider = get_provider(settings.score_provider)
        updated = poll_once(session, provider)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"provider error: {e}")
    return {"updated": updated}


# --- Standings + UI ----------------------------------------------------------

@app.get("/standings")
def standings(session: Session = Depends(get_session)) -> list[dict]:
    rows = compute_standings(session)
    ranks = assign_ranks([r.total_points for r in rows])  # ties share a position
    return [
        {
            "rank": ranks[i],
            "username": r.username,
            "display_name": r.display_name,
            "points": r.total_points,
            "matches_scored": r.matches_scored,
            "per_match": r.per_match,
        }
        for i, r in enumerate(rows)
    ]


@app.get("/live")
def live_board(session: Session = Depends(get_session)) -> dict:
    """Rich live standings: totals, movement vs pre-live baseline, and each user's
    prediction + live points for the current live match."""
    return compute_live_board(session)


@app.get("/me")
def me(request: Request, session: Session = Depends(get_session)) -> dict:
    """Home-card data for the identified user: their rank/points + the live-or-next
    match shortcut. Drives the personalized landing page."""
    username = _current_user(request)
    standings = compute_standings(session)
    ranks = assign_ranks([r.total_points for r in standings])  # ties share a position

    rank = points = None
    display_name = None
    if username:
        for i, r in enumerate(standings):
            if r.username == username:
                rank, points, display_name = ranks[i], r.total_points, r.display_name
                break
        if display_name is None:
            p = session.get(Participant, username)
            display_name = p.display_name if p else username

    leader_points = standings[0].total_points if standings else None
    points_behind_leader = (
        max(0, leader_points - points) if points is not None and leader_points is not None else None
    )

    # Spotlight: a live match if any, else the next upcoming (or any not-finished).
    now = dt.datetime.utcnow()
    spot = session.scalar(
        select(Match).where(Match.status == MatchStatus.LIVE).order_by(Match.kickoff_utc)
    )
    kind = "live" if spot else None
    if spot is None:
        spot = session.scalar(
            select(Match)
            .where(Match.status == MatchStatus.SCHEDULED, Match.kickoff_utc >= now)
            .order_by(Match.kickoff_utc)
        ) or session.scalar(
            select(Match).where(Match.status != MatchStatus.FINISHED).order_by(Match.kickoff_utc)
        )
        kind = "next" if spot else None

    # Last finished match + the user's own prediction/points on it, for the home card.
    last_match = None
    if username:
        lm = session.scalar(
            select(Match)
            .where(Match.status == MatchStatus.FINISHED)
            .order_by(Match.kickoff_utc.desc())
        )
        if lm is not None and lm.home_score is not None and lm.away_score is not None:
            pred = session.scalar(
                select(Prediction).where(Prediction.match_id == lm.id, Prediction.username == username)
            )
            last_match = {
                **_match_brief(lm),
                "pred_home": pred.pred_home if pred else None,
                "pred_away": pred.pred_away if pred else None,
                "match_points": (
                    score_prediction(pred.pred_home, pred.pred_away, lm.home_score, lm.away_score, lm.stage).total
                    if pred is not None
                    else None
                ),
            }

    return {
        "identified": username is not None,
        "username": username,
        "display_name": display_name,
        "is_admin": _is_admin(request),
        "rank": rank,
        "points": points,
        "players": len(standings),
        "points_behind_leader": points_behind_leader,
        "spotlight": _match_brief(spot, kind) if spot else None,
        "last_match": last_match,
    }


@app.get("/me/history")
def me_history(request: Request, session: Session = Depends(get_session)) -> dict:
    """Cumulative points of the identified user across finished matches (chronological),
    for the evolution chart on the home page."""
    username = _current_user(request)
    if not username:
        return {"identified": False, "points": []}

    matches = [
        m
        for m in session.scalars(
            select(Match).where(Match.status == MatchStatus.FINISHED).order_by(Match.kickoff_utc)
        ).all()
        if m.home_score is not None and m.away_score is not None
    ]

    # All predictions for those matches, grouped, to rank everyone after each match.
    by_match: dict[int, list[Prediction]] = {}
    if matches:
        for p in session.scalars(
            select(Prediction).where(Prediction.match_id.in_([m.id for m in matches]))
        ).all():
            by_match.setdefault(p.match_id, []).append(p)

    cum: dict[str, int] = {}  # username -> cumulative points so far
    points = []
    for m in matches:
        target_pred = None
        for p in by_match.get(m.id, []):
            pts = score_prediction(
                p.pred_home, p.pred_away, m.home_score, m.away_score, m.stage
            ).total
            cum[p.username] = cum.get(p.username, 0) + pts
            if p.username == username:
                target_pred = p

        mp = (
            score_prediction(
                target_pred.pred_home, target_pred.pred_away, m.home_score, m.away_score, m.stage
            ).total
            if target_pred is not None
            else 0
        )
        # Position after this match (1 = best, ties shared), among players so far.
        if username in cum:
            order = sorted(cum.items(), key=lambda kv: (-kv[1], kv[0]))
            ranks = assign_ranks([v for _, v in order])
            rank = ranks[[u for u, _ in order].index(username)]
            points_behind_leader = max(cum.values()) - cum[username]
        else:
            rank = None
            points_behind_leader = None
        points.append(
            {
                "match_id": m.id,
                "home_team": m.home_team,
                "away_team": m.away_team,
                "score": f"{m.home_score}-{m.away_score}",
                "kickoff_utc": _iso_utc(m.kickoff_utc),
                "match_points": mp,
                "cumulative": cum.get(username, 0),
                "rank": rank,
                "players": len(cum),
                "played": target_pred is not None,
                "points_behind_leader": points_behind_leader,
            }
        )

    return {"identified": True, "username": username, "points": points}


@app.get("/analytics")
def analytics(request: Request, session: Session = Depends(get_session)) -> dict:
    """KPIs over finished matches. Admin-only (not in the regular user views)."""
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="admin only")
    return {
        "highlights": compute_highlights(session),
        "players": [p.to_dict() for p in compute_player_stats(session)],
        "matches": [m.to_dict() for m in compute_match_stats(session)],
        "engagement": compute_engagement(session),
    }


@app.post("/admin/audit")
async def admin_audit(
    request: Request, file: UploadFile = File(...), session: Session = Depends(get_session)
) -> dict:
    """Admin: OCR a Golpredictor standings screenshot and compare its points to
    our current standings. Returns only the discrepancies."""
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="admin only")
    image_bytes = await file.read()
    try:
        audit_rows = extract_standings(image_bytes)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    ours = {r.username: r.total_points for r in compute_standings(session)}
    roster = {p.username: p.display_name for p in session.scalars(select(Participant)).all()}
    keys_lower = {k.lower(): k for k in roster}

    seen, mismatches, unknown = set(), [], []
    for row in audit_rows:
        u, pts = row["username"], row["points"]
        ru = keys_lower.get(u.lower())
        if ru is None:  # OCR typo in the audit username -> fuzzy match to roster
            close = difflib.get_close_matches(u.lower(), list(keys_lower), n=1, cutoff=0.8)
            ru = keys_lower[close[0]] if close else None
        if ru is None:
            unknown.append({"audit_username": u, "points": pts})
            continue
        seen.add(ru)
        if ru in ours and ours[ru] != pts:
            mismatches.append(
                {"username": ru, "display_name": roster[ru], "ours": ours[ru], "golpredictor": pts}
            )

    not_read = [{"username": u, "display_name": roster[u]} for u in roster if u not in seen]
    return {
        "audit_rows": len(audit_rows),
        "compared": len(seen),
        "mismatches": mismatches,
        "not_read": not_read,
        "unknown": unknown,
    }


# --- Pages -------------------------------------------------------------------

def _page(name: str) -> FileResponse:
    return FileResponse(_WEB_DIR / name)


@app.get("/")
def page_home() -> FileResponse:
    return _page("home.html")


@app.get("/upload")
def page_upload() -> FileResponse:
    return _page("upload.html")


@app.get("/calendar")
def page_calendar() -> FileResponse:
    return _page("calendar.html")


@app.get("/match")
def page_match() -> FileResponse:
    return _page("match.html")  # reads ?id= client-side


@app.get("/board")
def page_board() -> FileResponse:
    return _page("standings.html")


@app.get("/insights")
def page_insights() -> FileResponse:
    return _page("analytics.html")  # data is admin-gated server-side


@app.get("/audit-view")
def page_audit() -> FileResponse:
    return _page("audit.html")  # data is admin-gated server-side


app.mount("/web", StaticFiles(directory=_WEB_DIR), name="web")
