"""Free World Cup 2026 score provider (worldcup26.ir).

Talks to the documented free API (https://worldcup26.ir). Free registration gives
a JWT; set it as SCORE_API_TOKEN. The endpoint returns all matches in one call,
which suits our low-volume polling.

Documented match shape:
    {"id":"1","home_score":"0","away_score":"0","finished":"FALSE",
     "time_elapsed":"notstarted","home_team_name_en":"Mexico",
     "away_team_name_en":"South Africa","local_date":"06/11/2026 13:00","type":"group"}

If the API is flaky or the shape drifts, fall back to manual score entry
(POST /matches/{id}/score) — the rest of the system doesn't care which path set
the score.
"""

from __future__ import annotations

import httpx

from app.config import get_settings
from app.scores.base import ProviderGame, register


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_minute(time_elapsed) -> int | None:
    # "notstarted" / "HT" / "FT" / "45" / "90+2" -> best-effort minute.
    if not time_elapsed:
        return None
    digits = "".join(c for c in str(time_elapsed) if c.isdigit())
    return int(digits) if digits else None


def parse_games(raw: list[dict]) -> list[ProviderGame]:
    """Map the API's raw match dicts to ProviderGame. Pure — unit-tested directly."""
    games: list[ProviderGame] = []
    for m in raw:
        finished = str(m.get("finished", "")).strip().upper() == "TRUE"
        elapsed = str(m.get("time_elapsed", "")).strip().lower()
        started = finished or (elapsed not in ("", "notstarted"))
        games.append(
            ProviderGame(
                provider_match_id=str(m.get("id")),
                home_team=m.get("home_team_name_en", ""),
                away_team=m.get("away_team_name_en", ""),
                home_score=_to_int(m.get("home_score")),
                away_score=_to_int(m.get("away_score")),
                minute=_parse_minute(m.get("time_elapsed")),
                started=started,
                finished=finished,
            )
        )
    return games


class WorldCupFreeProvider:
    name = "worldcup_free"

    def fetch_games(self) -> list[ProviderGame]:
        settings = get_settings()
        headers = {}
        if settings.score_api_token:
            headers["Authorization"] = f"Bearer {settings.score_api_token}"
        url = settings.score_api_base_url.rstrip("/") + "/get/games"
        resp = httpx.get(url, headers=headers, timeout=10.0)
        resp.raise_for_status()
        payload = resp.json()
        # Endpoint wraps the list as {"games": [...]} (also tolerate "data" or a bare list).
        if isinstance(payload, dict):
            raw = payload.get("games") or payload.get("data") or []
        else:
            raw = payload
        return parse_games(raw)


register(WorldCupFreeProvider())
