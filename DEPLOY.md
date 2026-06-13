# Deploying Polla to a server

FastAPI app, single process (the background score-poller runs in-process, so run
**one** worker). Tables are created automatically on first startup.

## 1. Prerequisites
- Python 3.11
- MySQL 8 (or MariaDB) — a database + user
- Outbound HTTPS (for the Gemini OCR API and the live-score API)

## 2. Get the code
```bash
git clone <your-repo-url> polla && cd polla
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # includes 'cryptography' for MySQL 8 auth
```

## 3. Create the database
```sql
CREATE DATABASE polla CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'polla'@'localhost' IDENTIFIED BY 'a-strong-password';
GRANT ALL PRIVILEGES ON polla.* TO 'polla'@'localhost';
FLUSH PRIVILEGES;
```

## 4. Configure `.env`
```bash
cp .env.example .env
```
Edit `.env`:
- `DB_HOST/DB_USER/DB_PASSWORD/DB_NAME` → your MySQL (leave `DB_URL` empty).
- `ADMIN_USERS=kliche` (Golpredictor handle(s) with admin access; comma-separated).
- `GEMINI_API_KEY=...` (free key from Google AI Studio) — for screenshot OCR.
- `SCORE_POLL_SECONDS=120` (live-score poll interval).

> `.env` is gitignored — never commit it. Keep the API keys out of version control.

## 5. First run (smoke test)
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Open `http://<server>:8000/health` → `{"status":"ok"}`. Tables auto-create.

## 6. Load the data (once)
With the app running:
```bash
.venv/bin/python scripts/load_wc2026_groups.py http://localhost:8000   # 72 fixtures
.venv/bin/python scripts/load_participants.py  http://localhost:8000   # 52 players
```
(Both scripts authenticate as admin via a `polla_user=kliche` cookie — make sure
`ADMIN_USERS` includes `kliche`, or edit the cookie in the scripts.)

## 7. Run as a service (production)
Use the provided `deploy/polla.service` (systemd). Adjust paths/user, then:
```bash
sudo cp deploy/polla.service /etc/systemd/system/polla.service
sudo systemctl daemon-reload
sudo systemctl enable --now polla
sudo systemctl status polla
journalctl -u polla -f          # logs (you'll see "poll: updated N" every 2 min)
```

## 8. Reverse proxy + TLS (recommended)
Put nginx (or Caddy) in front for HTTPS on port 443, proxying to `127.0.0.1:8000`.
Minimal nginx location:
```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

## Notes
- **One process only.** The score poller uses APScheduler in-process; multiple
  workers would poll (and update) the DB redundantly. Scale with a proxy, not
  workers, or move the poller to a separate process if you need many workers.
- **Uploads** (OCR screenshots + CSVs) are stored under `uploads/<id>.<Home>-<Away>/`.
  This folder is gitignored; back it up if you want to keep the source images.
- **Schema migrations:** there are none — `init_db()` (`create_all`) builds the full
  current schema on a fresh database. For schema changes on an existing DB later,
  introduce Alembic.
- **Tests:** `pytest` (38 tests, SQLite-backed, no network).
