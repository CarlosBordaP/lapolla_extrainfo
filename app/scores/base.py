"""Live-score provider interface (Phase 2).

Every score source implements ScoreProvider so the rest of the app never depends
on a specific API. Swap providers via the `score_provider` setting / get_provider().

A provider returns full ProviderGame objects (not just scores) so the poller can
both update scores AND auto-link our matches to provider IDs by team name.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Protocol

from app.teams import TEAM_ALIASES


@dataclass(frozen=True)
class ProviderGame:
    provider_match_id: str
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    minute: int | None  # in-game minute, if reported
    started: bool
    finished: bool


class ScoreProvider(Protocol):
    name: str

    def fetch_games(self) -> list[ProviderGame]:
        """Return current state for all known games (live, finished, scheduled)."""
        ...


def normalize_team(name: str) -> str:
    """Canonical team key for matching across language + accents.

    México/Mexico collapse via accent-stripping; Sudáfrica/South Africa collapse
    via the Spanish→English alias map (app/teams.py).
    """
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)
    )
    base = stripped.lower().strip()
    return TEAM_ALIASES.get(base, base)


_REGISTRY: dict[str, ScoreProvider] = {}


def register(provider: ScoreProvider) -> None:
    _REGISTRY[provider.name] = provider


def get_provider(name: str) -> ScoreProvider:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown score provider {name!r}. Registered: {list(_REGISTRY)}")
    return _REGISTRY[name]
