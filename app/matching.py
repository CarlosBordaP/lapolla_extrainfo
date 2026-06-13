"""Match OCR'd predictions to the stored participants and validate completeness.

OCR usernames/names can have small errors, so we resolve each row to a stored
participant in cascade: exact username -> fuzzy username -> exact name. Resolved
rows use the STORED display name (authoritative), so everything concords with what
we already have. The uploader's own prediction (the "top") is attributed to the
identified uploader, or — if exactly one participant is missing — to that person.
"""

from __future__ import annotations

import difflib
import unicodedata


def _norm(s: str) -> str:
    stripped = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return stripped.lower().strip()


def match_and_validate(
    ocr_rows: list[dict],
    top: dict | None,
    participants: list[tuple[str, str]],  # (username, display_name)
    uploader: str | None,
) -> dict:
    by_user = {u.lower(): (u, name) for u, name in participants}
    # Name index — only unique normalized names are usable for name-matching.
    name_counts: dict[str, int] = {}
    for _u, name in participants:
        name_counts[_norm(name)] = name_counts.get(_norm(name), 0) + 1
    by_name = {_norm(name): u for u, name in participants if name_counts[_norm(name)] == 1}
    usernames_lower = list(by_user.keys())

    resolved: list[dict] = []
    for row in ocr_rows:
        ocr_user = (row.get("username") or "").strip()
        ocr_name = (row.get("display_name") or "").strip()
        key = ocr_user.lower()
        username = ""
        display = ocr_name
        status = "none"

        if key in by_user:
            username, display = by_user[key]
            status = "exact"
        else:
            close = difflib.get_close_matches(key, usernames_lower, n=1, cutoff=0.8)
            if close:
                username, display = by_user[close[0]]
                status = "fuzzy"
            elif _norm(ocr_name) in by_name:
                username = by_name[_norm(ocr_name)]
                display = by_user[username.lower()][1]
                status = "name"

        resolved.append({
            "ocr_username": ocr_user,
            "ocr_name": ocr_name,
            "username": username,
            "display_name": display,
            "pred_home": row.get("pred_home"),
            "pred_away": row.get("pred_away"),
            "match": status,
        })

    covered = {r["username"] for r in resolved if r["username"]}
    missing = [
        {"username": u, "display_name": name}
        for u, name in participants
        if u not in covered
    ]

    # Attribute the uploader's top prediction.
    top_out = None
    if top is not None:
        assigned = ""
        if uploader and uploader not in covered:
            assigned = uploader
        elif len(missing) == 1:
            assigned = missing[0]["username"]
        assigned_name = by_user[assigned.lower()][1] if assigned and assigned.lower() in by_user else ""
        top_out = {
            "username": assigned,
            "display_name": assigned_name,
            "pred_home": top.get("pred_home"),
            "pred_away": top.get("pred_away"),
        }

    return {
        "predictions": resolved,
        "top": top_out,
        "validation": {
            "participants": len(participants),
            "uploaded": len(covered),
            "missing": missing,
            "uploader": uploader,
            "top_assigned_to": top_out["username"] if top_out else None,
        },
    }
