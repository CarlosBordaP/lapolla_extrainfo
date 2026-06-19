# Polla — World Cup live standings

Real-time standings table for a private family/friends World Cup 2026 prediction
game run on [Golpredictor](https://www.golpredictor.com). Golpredictor freezes
predictions 10 min before kickoff but does not show how the table moves **during**
a match — this app does.

**Core idea:** predictions are frozen at lock time, so the only live variable is
the real score. `live_standings = scoring_engine(frozen_predictions, live_score)`.

## Stack
- Python + **FastAPI**, **MySQL** (local for dev, dedicated server for prod)
- Prediction ingestion: **Claude vision OCR** of Golpredictor screenshots + confirm step
- Live scores: free APIs behind a swappable provider interface

## Scoring (validated vs Golpredictor)
Four independent additive components, per prediction (group / knockout):
result 5/10, home goals 2/4, away goals 2/4, goal difference 1/2 — max 10/20.
90 minutes only (no extra time / penalties). See `app/scoring.py`.

## Layout
```
app/
  scoring.py     # pure scoring engine (heart of the system)
  standings.py   # ranks participants live from predictions + scores
  ocr.py         # Claude vision → structured prediction table
  ingest.py      # idempotent save of reviewed predictions
  poller.py      # apply provider scores to matches (auto-links by team name)
  teams.py       # Spanish→English team aliases (Sudáfrica ↔ South Africa)
  analytics.py   # KPIs over finished matches (player/match/highlights)
  tracking.py    # page-access + time-on-page engagement
  schemas.py     # API request models
  models.py      # MySQL schema (participants / matches / predictions / page_visits)
  db.py config.py main.py
  scores/        # swappable live-score providers (base + scores365 + worldcup_free)
web/             # ingest.html, standings.html (/board), analytics.html (/insights), track.js
tests/           # scoring, standings, ingest, poller, analytics, tracking, HTTP integration

## Privacy note
Access tracking is first-party: a participant picks who they are (a cookie), and
page visits + active time-on-page are stored in `page_visits` for the pool's own
engagement stats. Worth telling the group it's on. Cookies: `polla_uid` (anonymous
device id) and `polla_user` (chosen handle).
```

## Develop
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # adjust DB credentials
pytest                        # run scoring tests (no DB needed)
uvicorn app.main:app --reload # needs a running MySQL
```

## Roadmap
- [x] **Phase 0** — scaffold + scoring engine + tests
- [x] **Phase 1** — OCR ingestion (Claude vision) + confirm/manual-entry UI
- [x] **Phase 2** — live score provider + background poller + manual override
- [x] **Phase 3** — live standings UI (`/board`, reorders as scores change)
- [x] **Phase 4** — analytics / KPIs (`/insights`) + access tracking

## See the live board without waiting for a real match
With the app running (`uvicorn app.main:app --reload`):
1. Open `/` and load a match's predictions (OCR or manual), or POST `/predictions/confirm`.
2. Open `/board` in another tab.
3. Drive the score and watch the table reorder live:
   ```bash
   curl -X POST localhost:8000/matches/1/score -H 'content-type: application/json' -d '{"home_score":1,"away_score":0}'
   curl -X POST localhost:8000/matches/1/score -H 'content-type: application/json' -d '{"home_score":2,"away_score":0,"finished":true}'
   ```
```
