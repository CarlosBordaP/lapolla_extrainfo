"""Pytest setup: point the app at a throwaway SQLite DB before app modules import.

Must run before `app.db` is imported (which builds the engine at import time), so
this lives in conftest.py at the tests root — pytest loads it first.
"""

import os
import pathlib
import tempfile

_db_path = pathlib.Path(tempfile.gettempdir()) / "polla_test.sqlite"
if _db_path.exists():
    _db_path.unlink()

os.environ["DB_URL"] = f"sqlite:///{_db_path}"
os.environ["SCORE_API_TOKEN"] = ""  # keep the background poller idle during tests
os.environ["ADMIN_USERS"] = "kevinb"  # admin-gated views test against this user
