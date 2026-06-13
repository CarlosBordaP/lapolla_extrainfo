"""Tests for OCR→roster matching and completeness validation."""

from app.matching import match_and_validate

ROSTER = [
    ("kevinb", "Kevin Borda"),
    ("fonse", "Alberto Fonseca"),
    ("oasilv", "Orlando Silva"),
    ("mayeli", "Claudia Mayeli"),
]


def _row(u, n, h, a):
    return {"username": u, "display_name": n, "pred_home": h, "pred_away": a}


def test_cascade_exact_fuzzy_name_and_top_to_uploader():
    rows = [
        _row("fonse", "Alberto Fonseca", 2, 0),    # exact
        _row("oasllv", "Orlando Silva", 1, 1),     # fuzzy username -> oasilv
        _row("zzz999", "Claudia Mayeli", 0, 0),    # by name -> mayeli
    ]
    out = match_and_validate(rows, {"pred_home": 2, "pred_away": 0}, ROSTER, uploader="kevinb")

    by_ocr = {p["ocr_username"]: p for p in out["predictions"]}
    assert by_ocr["fonse"]["username"] == "fonse" and by_ocr["fonse"]["match"] == "exact"
    assert by_ocr["oasllv"]["username"] == "oasilv" and by_ocr["oasllv"]["match"] == "fuzzy"
    assert by_ocr["zzz999"]["username"] == "mayeli" and by_ocr["zzz999"]["match"] == "name"
    # Resolved rows carry the STORED display name.
    assert by_ocr["oasllv"]["display_name"] == "Orlando Silva"

    v = out["validation"]
    assert v["participants"] == 4 and v["uploaded"] == 3
    assert [m["username"] for m in v["missing"]] == ["kevinb"]
    # Uploader's top prediction is attributed to the uploader.
    assert out["top"]["username"] == "kevinb" and out["top"]["display_name"] == "Kevin Borda"
    assert out["top"]["pred_home"] == 2 and v["top_assigned_to"] == "kevinb"


def test_top_goes_to_single_missing_when_no_uploader():
    rows = [
        _row("fonse", "Alberto Fonseca", 1, 0),
        _row("oasilv", "Orlando Silva", 1, 0),
        _row("mayeli", "Claudia Mayeli", 1, 0),
    ]  # only kevinb missing
    out = match_and_validate(rows, {"pred_home": 3, "pred_away": 1}, ROSTER, uploader=None)
    assert out["top"]["username"] == "kevinb"  # inferred as the only missing person


def test_top_unassigned_when_ambiguous():
    rows = [_row("fonse", "Alberto Fonseca", 1, 0)]  # 3 missing, no uploader
    out = match_and_validate(rows, {"pred_home": 1, "pred_away": 1}, ROSTER, uploader=None)
    assert out["top"]["username"] == ""  # can't decide -> left for manual pick
    assert len(out["validation"]["missing"]) == 3


def test_unmatched_row_flagged():
    rows = [_row("totally_unknown", "Nadie Conocido", 0, 0)]
    out = match_and_validate(rows, None, ROSTER, uploader=None)
    p = out["predictions"][0]
    assert p["username"] == "" and p["match"] == "none"
    assert out["top"] is None