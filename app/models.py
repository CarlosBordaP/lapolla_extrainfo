"""SQLAlchemy ORM models / MySQL schema.

Note: per-prediction POINTS are deliberately NOT stored. They are derived on the
fly by app.scoring from (prediction, match score), which is exactly what lets the
standings recompute live every time the score changes. We only persist the raw
inputs: participants, matches (with current score), and predictions.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.scoring import Stage


class Base(DeclarativeBase):
    pass


class MatchStatus(str, __import__("enum").Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"


class Participant(Base):
    __tablename__ = "participants"

    # Golpredictor handle (Usuario) — the stable unique key. NOT the display name,
    # which collides (multiple Valderrama / Borda Penagos in the group).
    username: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    # Golpredictor sign-up time (UTC). Extra signal for analytics; Golpredictor uses
    # it as a tiebreaker (earlier registration ranks higher).
    registered_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    predictions: Mapped[list["Prediction"]] = relationship(back_populates="participant")


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stage: Mapped[Stage] = mapped_column(Enum(Stage), default=Stage.GROUP)
    home_team: Mapped[str] = mapped_column(String(64))
    away_team: Mapped[str] = mapped_column(String(64))
    kickoff_utc: Mapped[dt.datetime] = mapped_column(DateTime)
    status: Mapped[MatchStatus] = mapped_column(Enum(MatchStatus), default=MatchStatus.SCHEDULED)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # When the score was last read from the provider (UTC) — freshness reference.
    score_updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    # Maps this match to the live-score provider's id (Phase 2).
    provider_match_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # True once a predictions screenshot has been processed — blocks further uploads.
    locked: Mapped[bool] = mapped_column(default=False)
    # Admin override: force the upload window open regardless of time (for tests/fixes).
    force_upload: Mapped[bool] = mapped_column(default=False)

    predictions: Mapped[list["Prediction"]] = relationship(back_populates="match")


class MatchFile(Base):
    """A screenshot uploaded for OCR, kept so the match detail can show its source.

    Created at ingest time with match_id NULL (the match doesn't exist yet); linked
    to the match on confirm via upload_id.
    """

    __tablename__ = "match_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"), nullable=True, index=True)
    upload_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    original_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    content_type: Mapped[str] = mapped_column(String(64), default="image/jpeg")
    stored_path: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


class PageVisit(Base):
    """One page visit, for engagement analytics. `client_id` comes from a cookie
    (anonymous device id); `username` is filled once the person self-identifies.
    `seconds` is active time-on-page, reported by the browser and updated in place.
    Not FK on username so anonymous visits and renamed users don't break inserts.
    """

    __tablename__ = "page_visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    path: Mapped[str] = mapped_column(String(128))
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    last_seen: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    seconds: Mapped[int] = mapped_column(Integer, default=0)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (UniqueConstraint("match_id", "username", name="uq_match_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    username: Mapped[str] = mapped_column(ForeignKey("participants.username"))
    pred_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pred_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    modified_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    match: Mapped["Match"] = relationship(back_populates="predictions")
    participant: Mapped["Participant"] = relationship(back_populates="predictions")
