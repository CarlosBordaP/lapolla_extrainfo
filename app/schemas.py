"""Pydantic request/response models for the API."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from app.scoring import Stage


class PredictionIn(BaseModel):
    username: str
    display_name: str
    pred_home: int = Field(ge=0)
    pred_away: int = Field(ge=0)


class ConfirmIn(BaseModel):
    """Reviewed predictions, ready to save. The kickoff time and stage are set by
    the human in the confirm step (not taken blindly from OCR)."""

    home_team: str
    away_team: str
    kickoff_utc: dt.datetime
    stage: Stage = Stage.GROUP
    predictions: list[PredictionIn]
    upload_id: str | None = None  # links the OCR screenshot to this match


class IdentifyIn(BaseModel):
    username: str


class ParticipantIn(BaseModel):
    username: str
    display_name: str
    registered_at: dt.datetime | None = None


class BulkParticipantsIn(BaseModel):
    participants: list[ParticipantIn]


class VisitStartIn(BaseModel):
    path: str


class VisitPingIn(BaseModel):
    visit_id: int
    seconds: int = Field(ge=0)


class ProviderLinkIn(BaseModel):
    """Manually link a match to a provider game id (for team pairs the alias map
    doesn't cover). After linking, polling updates that match by id."""

    provider_match_id: str


class FixtureIn(BaseModel):
    """Create a calendar match (fixture) ahead of time. Admin-only."""

    home_team: str
    away_team: str
    kickoff_utc: dt.datetime
    stage: Stage = Stage.GROUP


class BulkMatchesIn(BaseModel):
    """Load many fixtures at once (admin). Idempotent on home+away+kickoff."""

    matches: list[FixtureIn]


class MatchPredictionsIn(BaseModel):
    """Confirm predictions for an existing match (per-match upload flow)."""

    predictions: list[PredictionIn]
    upload_id: str | None = None


class UploadWindowIn(BaseModel):
    """Admin override to force a match's upload window open/closed."""

    open: bool


class PredictionEditIn(BaseModel):
    """Admin correction of a single user's prediction for a match (e.g. OCR error)."""

    username: str
    pred_home: int = Field(ge=0)
    pred_away: int = Field(ge=0)


class ManualScoreIn(BaseModel):
    """Manually set a match's live score (fallback when no API, or to test the
    live standings without waiting for a real match)."""

    home_score: int = Field(ge=0)
    away_score: int = Field(ge=0)
    finished: bool = False
