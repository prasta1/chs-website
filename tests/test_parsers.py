from conftest import PDF_DIR
from scripts.parsers.cemetery import parse_cemetery


def test_cemetery_extracts_expected_person():
    rows = parse_cemetery(PDF_DIR / "cloverdale.pdf", "Cloverdale Cemetery")
    ruth = [a for a in rows if a.surname == "Atwood" and a.given == "Ruth"][0]
    assert ruth.kind == "burial"
    assert ruth.date_iso == "1831-02-11"
    assert ruth.place == "Cloverdale Cemetery"
    assert "Thomas Atwood" in ruth.detail
    assert ruth.page == 1


def test_cemetery_skips_the_header_row():
    rows = parse_cemetery(PDF_DIR / "cloverdale.pdf", "Cloverdale Cemetery")
    assert not any(a.surname == "Last" for a in rows)


def test_cemetery_row_count_is_plausible():
    rows = parse_cemetery(PDF_DIR / "cloverdale.pdf", "Cloverdale Cemetery")
    assert 140 <= len(rows) <= 170


def test_cemetery_every_row_has_identity_and_key():
    rows = parse_cemetery(PDF_DIR / "cloverdale.pdf", "Cloverdale Cemetery")
    assert all(a.surname and a.import_key and a.page >= 1 for a in rows)
