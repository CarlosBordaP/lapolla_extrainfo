"""Tests for access tracking: device cookie, identify, visit start/ping, engagement."""

from fastapi.testclient import TestClient

from app.main import app

CONFIRM = {
    "home_team": "México", "away_team": "Sudáfrica",
    "kickoff_utc": "2026-06-11T19:00:00", "stage": "group",
    "predictions": [{"username": "kevinb", "display_name": "Kevin", "pred_home": 2, "pred_away": 0}],
}


def test_tracking_flow_end_to_end():
    with TestClient(app) as c:
        c.post("/predictions/confirm", json=CONFIRM)

        # Device cookie is assigned on first response.
        r = c.get("/health")
        assert "polla_uid" in r.cookies or c.cookies.get("polla_uid")

        # Roster for the picker includes our participant.
        names = [p["username"] for p in c.get("/track/participants").json()]
        assert "kevinb" in names

        # Unknown participant is rejected.
        assert c.post("/track/identify", json={"username": "nobody"}).status_code == 404

        # Identify, then a visit attributes to that user.
        assert c.post("/track/identify", json={"username": "kevinb"}).status_code == 200
        visit_id = c.post("/track/visit/start", json={"path": "/board"}).json()["visit_id"]

        # Report 42s, then a stale 30s beacon must not lower it.
        assert c.post("/track/visit/ping", json={"visit_id": visit_id, "seconds": 42}).json()["ok"]
        c.post("/track/visit/ping", json={"visit_id": visit_id, "seconds": 30})

        eng = {e["username"]: e for e in c.get("/analytics").json()["engagement"]}
        assert eng["kevinb"]["visits"] == 1
        assert eng["kevinb"]["total_seconds"] == 42  # kept the max, not the stale 30


def test_ping_unknown_visit_is_false():
    with TestClient(app) as c:
        assert c.post("/track/visit/ping", json={"visit_id": 999999, "seconds": 5}).json()["ok"] is False
