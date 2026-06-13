# Polla — Project Handoff & Reference

Complete reference for the **Polla** app: a real-time standings board for a private
family/friends World Cup 2026 prediction game played on the
[Golpredictor](https://www.golpredictor.com) platform. Read this first if you (or
another session / another AI) are picking the project up. **For deploying, see
`DEPLOY.md`.**

## Current state (overrides older sections below where they conflict)
- **OCR engine: Google Gemini** (`gemini-2.5-flash`, free tier) via `google-genai`;
  configurable with `OCR_PROVIDER=gemini|claude`. Returns the prediction table as CSV.
- **Calendar loaded:** 72 group-stage fixtures (`scripts/load_wc2026_groups.py`); times
  shown in **America/Bogota**. **52 participants** loaded (`scripts/load_participants.py`)
  with a `registered_at` field.
- **Admin** = `ADMIN_USERS` env (currently `kliche` = Carlos Mario Borda Penagos).
- **Upload flow is per-match from the calendar**, gated to a 10-min-before → match-end
  window (`force_upload` admin override exists). OCR result is matched to the roster
  (exact→fuzzy→name), validates completeness vs 52, and attributes the uploader's "top"
  prediction. Files saved to `uploads/<id>.<Home>-<Away>/` (image + CSV).
- **Live scores:** `worldcup26.ir` (no token needed), polled every `SCORE_POLL_SECONDS`
  (120s); matches auto-link by team name via the Spanish→English alias map.
- **Goal-difference scoring uses the ABSOLUTE margin** (Golpredictor rule).
- **New endpoints:** `POST /matches/{id}/prediction-edit` (admin correction),
  `POST /matches/{id}/upload-window` (admin force-open), `POST /matches/bulk`,
  `POST /participants/bulk`, `POST /admin/audit` (compare a Golpredictor screenshot to
  our standings), `GET /live` (board with movement vs the last match).
- **New pages:** `/audit-view` (admin), identity typeahead modal in `nav.js`,
  calendar tabs, compact upload table, top-10 + pinned-user standings.
- **38 tests passing.**

---

## 1. The problem & the core idea

The group predicts match scores on Golpredictor. Golpredictor **locks predictions
10 minutes before kickoff** and awards points after each game, but it does **not**
show how the standings move **during** a match. The group follows along over
WhatsApp by sharing screenshots. Polla fills that gap with a live standings table.

**Key architectural insight that makes this tractable:**

> Predictions are **frozen** at lock time, so the only variable that moves during a
> game is the **real score**.
>
> `live_standings = scoring_engine(frozen_predictions, current_live_score)`

This cleanly splits the system into two pipelines:
1. **Predictions in** (once per match, via OCR of a Golpredictor screenshot).
2. **Live score in** (polled during the match from a free API, or set manually).

The standings are *computed on read* from those two inputs — never stored — so they
recompute instantly whenever the live score changes.

---

## 2. Scoring rules (validated against real data)

Source: <https://www.golpredictor.com/regulation.aspx>. Predictions cover **90
minutes only** (no extra time / penalties). Each prediction earns points from
**four independent, additive components**:

| Component                     | Group stage | Knockout |
|-------------------------------|:-----------:|:--------:|
| Correct result (W / D / L)    | 5           | 10       |
| Correct home goals            | 2           | 4        |
| Correct away goals            | 2           | 4        |
| Correct goal difference       | 1           | 2        |
| **Max (exact score)**         | **10**      | **20**   |

Knockout = group values × 2. Implemented in `app/scoring.py` and **validated
against the real México 2–0 Sudáfrica match**: `2-0`→10 (exact), `1-0`→7
(result+away goals), `3-1`→6 (result+goal-difference), `0-2`→0 (wrong winner).

---

## 3. Tech stack

| Layer            | Choice |
|------------------|--------|
| Language         | Python 3.11 |
| Web framework    | FastAPI (+ Uvicorn) |
| ORM / DB         | SQLAlchemy 2.0 → **MySQL** (PyMySQL) in prod; SQLite for tests/dev via `DB_URL` |
| Config           | pydantic-settings (`.env`) |
| OCR              | **Anthropic Claude vision** (`claude-opus-4-8`) with structured-output JSON schema |
| Live scores      | Free HTTP API behind a swappable provider interface (httpx) |
| Background jobs  | APScheduler (in-process `BackgroundScheduler`) |
| Frontend         | Plain HTML + vanilla JS (no build step) |
| Tests            | pytest (28 tests, all on SQLite, no network) |

Deployment target: the user's **own dedicated server with MySQL** (not yet deployed).

---

## 4. Phases (all built & tested)

| Phase | What | Key files |
|-------|------|-----------|
| **0 — Foundation** | Scoring engine + standings + schema + tests | `scoring.py`, `standings.py`, `models.py` |
| **1 — Ingestion** | OCR a Golpredictor screenshot → human review/edit → save | `ocr.py`, `ingest.py`, `web/ingest.html` |
| **2 — Live scores** | Provider interface + real free API + background poller + manual override | `scores/`, `poller.py`, `teams.py` |
| **3 — Live board** | Standings UI that reorders during a match | `web/standings.html` (`/board`) |
| **4 — Analytics + tracking** | KPIs over finished matches + page-access engagement | `analytics.py`, `tracking.py`, `web/analytics.html` (`/insights`), `web/track.js` |

---

## 5. Data model (`app/models.py`)

- **`participants`** — `username` (PK, the Golpredictor handle — the stable unique
  key; **not** the display name, which collides), `display_name`, `created_at`.
- **`matches`** — `id`, `stage` (`group`/`knockout`), `home_team`, `away_team`,
  `kickoff_utc`, `status` (`scheduled`/`live`/`finished`), `home_score`,
  `away_score`, `provider_match_id` (link to the score API).
- **`predictions`** — `id`, `match_id`→matches, `username`→participants,
  `pred_home`, `pred_away`, `modified_at`. `UNIQUE(match_id, username)`.
- **`page_visits`** — `id`, `client_id` (anon device cookie), `username` (nullable,
  filled on self-identify), `path`, `started_at`, `last_seen`, `seconds` (active
  time-on-page), `user_agent`. For engagement analytics.

> Per-prediction **points are not stored** — derived on the fly by `app/scoring.py`,
> which is what makes live recompute trivial.

---

## 6. HTTP API (`app/main.py`)

| Method & path | Purpose |
|---|---|
| `GET /health` | Liveness. |
| `GET /` | Ingest page (upload screenshot / manual entry). |
| `GET /board` | Live standings board. |
| `GET /insights` | Analytics + engagement page. |
| `POST /predictions/ingest` | OCR a screenshot → parsed table (**does not save**). Needs `ANTHROPIC_API_KEY`. |
| `POST /predictions/confirm` | Save reviewed predictions (idempotent upsert). |
| `GET /matches` | List matches with scores/status. |
| `POST /matches/{id}/score` | **Manual** score set/override (`{home_score, away_score, finished?}`). |
| `POST /matches/{id}/link` | Manually link a match to a provider game id. |
| `GET /scores/games` | List provider's current games (to pick an id for linking). |
| `POST /scores/refresh` | Trigger one poll now (also auto-links by team name). |
| `GET /standings` | Live standings, recomputed each call. |
| `GET /analytics` | `{highlights, players, matches, engagement}` over finished matches. |
| `GET /track/participants` | Roster for the "who are you?" picker. |
| `POST /track/identify` | Bind device to a participant (sets `polla_user` cookie). |
| `POST /track/visit/start` | Record a page visit → `{visit_id}`. |
| `POST /track/visit/ping` | Update active time-on-page (idempotent max). |
| `/web/*` | Static assets (incl. `track.js`). |

---

## 7. Important things / gotchas (read before changing code)

1. **OCR never auto-saves.** `POST /predictions/ingest` only parses; saving requires
   the human-reviewed `POST /predictions/confirm`. This is deliberate — one wrong
   digit corrupts everyone's standings. Keep the gate.
2. **Language mismatch on team names.** Predictions come from Golpredictor in
   **Spanish** ("Sudáfrica"); the score API returns **English** ("South Africa").
   `app/teams.py` holds a Spanish→English alias map; `normalize_team()` collapses
   both sides (accent-only diffs like México/Mexico need no entry). Teams not in the
   map fall back to **manual linking** (`POST /matches/{id}/link`). Extend `teams.py`
   as needed.
3. **`username` is the join key**, never `display_name` (the group has multiple
   "Valderrama" / "Borda Penagos").
4. **Analytics use FINISHED matches only** — so KPIs don't flicker mid-game. The
   live **board** uses live scores; **insights** uses settled results.
5. **Standings are computed, not stored.** `compute_standings()` re-derives points
   every call. Cheap at this scale; don't add a points column to the DB.
6. **Polling is gated.** The scheduler only calls the score API inside a live window
   (`has_live_window`, ±kickoff) and only if `SCORE_API_TOKEN` is set — respects the
   free API's quota. Manual scores always work without a token.
7. **Live-score API reliability is unproven.** Provider implemented to worldcup26.ir's
   documented shape, but not validated against a real in-progress match. The manual
   `POST /matches/{id}/score` endpoint is the guaranteed fallback.
8. **Access tracking is first-party.** Cookies: `polla_uid` (anonymous device id,
   httpOnly) and `polla_user` (chosen handle). Tell the group it's on.
9. **Model id:** OCR uses `claude-opus-4-8` (see `OCR_MODEL`). Vision + structured
   outputs (`output_config.format`) — don't switch to a model without structured-output
   support.

---

## 8. Configuration (`.env`, see `.env.example`)

| Var | Default | Notes |
|---|---|---|
| `DB_HOST/PORT/USER/PASSWORD/NAME` | `127.0.0.1`/`3306`/`polla`/`polla`/`polla` | MySQL connection. |
| `DB_URL` | *(empty)* | Full SQLAlchemy URL override (e.g. `sqlite:///./polla.db`). Wins over the above. |
| `ANTHROPIC_API_KEY` | *(empty)* | Required for OCR ingestion. |
| `OCR_MODEL` | `claude-opus-4-8` | Vision model. |
| `SCORE_PROVIDER` | `worldcup_free` | Registry key. |
| `SCORE_POLL_SECONDS` | `45` | Poll interval during live window. |
| `SCORE_API_BASE_URL` | `https://worldcup26.ir` | Free WC-2026 API. |
| `SCORE_API_TOKEN` | *(empty)* | Free JWT; empty disables auto-polling. |

---

## 9. Tests

`pytest` — 28 tests, all on in-memory/file SQLite, no network:
- `test_scoring.py` — engine vs real México 2-0 data.
- `test_standings.py` — ranking end-to-end.
- `test_ingest.py` — idempotent save/upsert.
- `test_poller.py` — API parsing, auto-link by name, live→final standings, window gate.
- `test_analytics.py` — KPIs over finished matches.
- `test_tracking.py` — device cookie, identify, visit/ping, engagement.
- `test_api_integration.py` — full HTTP flow through the ASGI app.

`tests/conftest.py` points the app at a throwaway SQLite file via `DB_URL`.

---

## 10. Roadmap / possible next steps

- Deploy to the dedicated MySQL server; validate against a real live match.
- Replace `init_db()` (`create_all`) with **Alembic** migrations for prod.
- Validate worldcup26.ir latency; wire **API-Football** as a fallback provider.
- Cross-check computed points vs Golpredictor's official points (trust check).
- Upgrade the board from polling to **Server-Sent Events** for instant push.
- Auth / per-group privacy if it ever leaves the family.
- Expand `teams.py` alias coverage for all 48 nations.
