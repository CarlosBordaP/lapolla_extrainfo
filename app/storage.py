"""Storage for uploaded OCR screenshots (kept so match detail can show the source).

Files are organized one folder per match, named "<id>.<Home>-<Away>" (e.g.
uploads/1.Mex-Sud/), each holding the renamed image plus the OCR CSV for easy
identification and validation.
"""

from __future__ import annotations

import os
import unicodedata
import uuid

from app.config import get_settings

_EXT = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def _abbr(name: str) -> str:
    """First 3 letters of a team name, accent-stripped (México -> Mex)."""
    base = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    base = "".join(ch for ch in base if ch.isalnum())
    return base[:3].capitalize()


def match_slug(match) -> str:
    """Ordered, human-friendly key for a match's files, e.g. '1.Mex-Sud'."""
    return f"{match.id}.{_abbr(match.home_team)}-{_abbr(match.away_team)}"


def save_prediction_files(
    match, image_bytes: bytes, content_type: str, csv_text: str
) -> tuple[str, str, str]:
    """Save the screenshot AND the OCR CSV into the match's folder, with matching
    names. Returns (upload_id, image_path, csv_path)."""
    settings = get_settings()
    slug = match_slug(match)
    folder = os.path.join(settings.uploads_dir, slug)
    os.makedirs(folder, exist_ok=True)

    ext = _EXT.get((content_type or "").lower(), ".img")
    image_path = os.path.join(folder, f"{slug}{ext}")
    with open(image_path, "wb") as f:
        f.write(image_bytes)

    csv_path = os.path.join(folder, f"{slug}.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write(csv_text or "")

    return uuid.uuid4().hex, image_path, csv_path


def save_upload_file(
    image_bytes: bytes, content_type: str, subdir: str | None = None
) -> tuple[str, str]:
    """Persist an uploaded image. Files are organized into subfolders (one per
    match, e.g. uploads/match_12/). Returns (upload_id, stored_path)."""
    settings = get_settings()
    folder = os.path.join(settings.uploads_dir, subdir) if subdir else settings.uploads_dir
    os.makedirs(folder, exist_ok=True)
    upload_id = uuid.uuid4().hex
    ext = _EXT.get((content_type or "").lower(), ".img")
    path = os.path.join(folder, f"{upload_id}{ext}")
    with open(path, "wb") as f:
        f.write(image_bytes)
    return upload_id, path
