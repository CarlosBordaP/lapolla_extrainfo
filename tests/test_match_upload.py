"""Per-match prediction upload: 10-minute window + single-processing lock."""

import datetime as dt

from fastapi.testclient import TestClient

from app.main import app

PREDS = [
    {"username": "kevinb", "display_name": "Kevin", "pred_home": 2, "pred_away": 0},
    {"username": "fonse", "display_name": "Sandra", "pred_home": 1, "pred_away": 1},
]


def _fixture(c, kickoff: dt.datetime):
    r = c.post(
        "/matches",
        json={
            "home_team": "México", "away_team": "Sudáfrica",
            "kickoff_utc": kickoff.isoformat(), "stage": "group",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_upload_window_and_lock():
    with TestClient(app) as c:
        c.cookies.set("polla_user", "kevinb")  # admin (ADMIN_USERS=kevinb in conftest)

        now = dt.datetime.utcnow()
        open_match = _fixture(c, now + dt.timedelta(minutes=5))    # 10-min window, before kickoff
        future_match = _fixture(c, now + dt.timedelta(hours=5))    # too early
        live_match = _fixture(c, now - dt.timedelta(minutes=20))   # in progress -> still open
        old_match = _fixture(c, now - dt.timedelta(minutes=200))   # long over -> closed by time

        assert open_match["upload_state"] == "open" and open_match["can_upload"] is True
        assert future_match["upload_state"] == "early" and future_match["can_upload"] is False
        assert live_match["upload_state"] == "open"                # open during the match
        assert old_match["upload_state"] == "closed"               # past the safety cap

        # A finished match closes the window even if recent.
        recent = _fixture(c, now - dt.timedelta(minutes=30))
        c.post(f"/matches/{recent['id']}/score", json={"home_score": 1, "away_score": 0, "finished": True})
        fm = next(m for m in c.get("/matches").json() if m["id"] == recent["id"])
        assert fm["upload_state"] == "closed"

        # Too-early upload is blocked.
        r = c.post(f"/matches/{future_match['id']}/predictions/confirm", json={"predictions": PREDS})
        assert r.status_code == 403 and "10 minutos" in r.json()["detail"]

        # Ended match: window closed.
        r = c.post(f"/matches/{old_match['id']}/predictions/confirm", json={"predictions": PREDS})
        assert r.status_code == 403 and "cerró" in r.json()["detail"]

        # Open match: first confirm saves and locks.
        r = c.post(f"/matches/{open_match['id']}/predictions/confirm", json={"predictions": PREDS})
        assert r.status_code == 200 and r.json()["saved"] == 2 and r.json()["locked"] is True

        # Second upload is rejected — already processed.
        r2 = c.post(f"/matches/{open_match['id']}/predictions/confirm", json={"predictions": PREDS})
        assert r2.status_code == 409 and "procesado" in r2.json()["detail"]

        # The match now reports locked / not uploadable in the list.
        m = next(m for m in c.get("/matches").json() if m["id"] == open_match["id"])
        assert m["locked"] is True and m["can_upload"] is False


def test_create_fixture_requires_admin():
    with TestClient(app) as c:
        # No admin cookie → forbidden.
        r = c.post(
            "/matches",
            json={"home_team": "A", "away_team": "B",
                  "kickoff_utc": dt.datetime.utcnow().isoformat(), "stage": "group"},
        )
        assert r.status_code == 403
