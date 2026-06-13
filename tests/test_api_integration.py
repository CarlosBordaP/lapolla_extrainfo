"""End-to-end HTTP test through the real FastAPI app (SQLite-backed).

Covers the full Phase 1-3 spine: save predictions → set a live score → standings
recompute live → finalize → pages render.
"""

from fastapi.testclient import TestClient

from app.main import app

CONFIRM = {
    "home_team": "México",
    "away_team": "Sudáfrica",
    "kickoff_utc": "2026-06-11T19:00:00",
    "stage": "group",
    "predictions": [
        {"username": "kevinb", "display_name": "Kevin", "pred_home": 2, "pred_away": 0},
        {"username": "fonserate", "display_name": "Sandra", "pred_home": 2, "pred_away": 1},
    ],
}


def _points(client):
    return {r["username"]: r["points"] for r in client.get("/standings").json()}


def test_full_flow_predictions_to_live_board():
    with TestClient(app) as c:
        assert c.get("/health").json()["status"] == "ok"

        match_id = c.post("/predictions/confirm", json=CONFIRM).json()["match_id"]

        # No score yet → nobody on the board.
        assert c.get("/standings").json() == []

        # Live 1-0: kevinb result+away = 7, fonserate result+GD = 6.
        c.post(f"/matches/{match_id}/score", json={"home_score": 1, "away_score": 0})
        assert _points(c) == {"kevinb": 7, "fonserate": 6}
        assert c.get("/matches").json()[0]["status"] == "live"

        # Final 2-0: kevinb exact = 10, fonserate result+home = 7.
        c.post(
            f"/matches/{match_id}/score",
            json={"home_score": 2, "away_score": 0, "finished": True},
        )
        standings = c.get("/standings").json()
        assert [r["username"] for r in standings] == ["kevinb", "fonserate"]
        assert _points(c) == {"kevinb": 10, "fonserate": 7}
        assert c.get("/matches").json()[0]["status"] == "finished"

        # Match detail: predictions carry points now that the match is scored.
        detail = c.get(f"/matches/{match_id}").json()
        assert detail["match"]["status"] == "finished"
        pts = {p["username"]: p["points"] for p in detail["predictions"]}
        assert pts == {"kevinb": 10, "fonserate": 7}

        # /me before identifying: anonymous. Only match is finished → no spotlight.
        anon = c.get("/me").json()
        assert anon["identified"] is False and anon["is_admin"] is False
        assert anon["spotlight"] is None

        # Identify as the admin user → rank card + admin flag + analytics access.
        c.post("/track/identify", json={"username": "kevinb"})
        me = c.get("/me").json()
        assert me["identified"] and me["is_admin"] and me["rank"] == 1 and me["points"] == 10
        assert c.get("/analytics").status_code == 200

        # Evolution history: one finished match, cumulative = match points.
        hist = c.get("/me/history").json()
        assert hist["identified"] and len(hist["points"]) == 1
        pt = hist["points"][0]
        assert pt["match_points"] == 10 and pt["cumulative"] == 10
        assert pt["rank"] == 1 and pt["players"] == 2  # kevinb leads fonserate

        # UI pages render.
        for path in ("/", "/board", "/calendar", "/upload", "/match", "/insights"):
            assert c.get(path).status_code == 200
