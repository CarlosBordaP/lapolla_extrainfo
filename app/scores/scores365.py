"""365scores.com live-score provider (undocumented public API used by their own
website widgets — no auth/registration required, unlike worldcup26.ir).

Documented match shape (subset of fields we use):
    {"id": 4627866, "statusGroup": 4, "gameTime": 90.0,
     "homeCompetitor": {"name": "Mexico", "score": 2.0},
     "awayCompetitor": {"name": "South Africa", "score": 0.0}}

statusGroup: 2 = scheduled, 1 = live, 4 = ended. Both `score` and `gameTime` use
-1 as a "not started yet" sentinel instead of null.

If this endpoint changes shape or gets blocked, fall back to manual score entry
(POST /matches/{id}/score) — the rest of the system doesn't care which path set
the score.
"""

from __future__ import annotations

import datetime as dt

import httpx

from app.scores.base import ProviderGame, register

_URL = "https://webws.365scores.com/web/games/current/"
_PARAMS = {
    "appTypeId": "5",
    "langId": "1",
    "timezoneName": "America/Bogota",
    "userCountryId": "109",
    "competitions": "5930",  # FIFA World Cup 2026
    "showOdds": "true",
    "includeTopBettingOpportunity": "1",
    "topBookmaker": "4",
}
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:151.0) Gecko/20100101 Firefox/151.0",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.365scores.com/",
    "Origin": "https://www.365scores.com",
}

_ENDED, _LIVE = 4, 1


def _non_negative_int(value) -> int | None:
    """365scores uses -1 (not 0/null) as the 'not started' sentinel for both
    scores and elapsed minutes."""
    if value is None or value < 0:
        return None
    return int(value)


def _parse_start_time(value: str | None) -> dt.datetime | None:
    """Parse 365scores ISO-8601 startTime (e.g. '2026-06-27T18:30:00-05:00') to
    naive UTC. Python 3.11+ handles the offset in fromisoformat()."""
    if not value:
        return None
    try:
        aware = dt.datetime.fromisoformat(value)
        return aware.astimezone(dt.timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def parse_games(raw: list[dict]) -> list[ProviderGame]:
    """Map 365scores' raw game dicts to ProviderGame. Pure — unit-tested directly."""
    games: list[ProviderGame] = []
    for g in raw:
        home, away = g.get("homeCompetitor") or {}, g.get("awayCompetitor") or {}
        status_group = g.get("statusGroup")
        finished = status_group == _ENDED
        home_score = _non_negative_int(home.get("score"))
        started = finished or status_group == _LIVE or home_score is not None
        games.append(
            ProviderGame(
                provider_match_id=str(g.get("id")),
                home_team=home.get("name", ""),
                away_team=away.get("name", ""),
                home_score=home_score,
                away_score=_non_negative_int(away.get("score")),
                minute=_non_negative_int(g.get("gameTime")),
                started=started,
                finished=finished,
                kickoff_utc=_parse_start_time(g.get("startTime")),
                stage_num=g.get("stageNum"),
            )
        )
    return games


class Scores365Provider:
    name = "scores365"

    def fetch_games(self) -> list[ProviderGame]:
        resp = httpx.get(_URL, params=_PARAMS, headers=_HEADERS, timeout=10.0)
        resp.raise_for_status()
        return parse_games(resp.json().get("games", []))


register(Scores365Provider())
