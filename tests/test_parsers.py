from conftest import PDF_DIR
from scripts.parsers.cemetery import parse_cemetery
from scripts.parsers.vital import parse_birth, parse_marriage


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


def test_southcambridge_parses_despite_wider_letter_tracking():
    rows = parse_cemetery(PDF_DIR / "southcambridge.pdf", "South Cambridge Cemetery")
    assert 300 <= len(rows) <= 360


def test_birth_extracts_the_child():
    rows = parse_birth(PDF_DIR / "birth_records.pdf")
    a = [r for r in rows if r.given == "Adalia Ellen" and r.surname == "Adams"][0]
    assert a.kind == "birth" and a.role == "child"
    assert a.date_iso == "1854-04-26"


def test_birth_also_emits_the_father():
    rows = parse_birth(PDF_DIR / "birth_records.pdf")
    child = [r for r in rows if r.given == "Adalia Ellen"][0]
    father = [r for r in rows if r.pair_key == child.pair_key and r.role == "father"][0]
    assert father.surname == "Adams" and father.given == "Dexter"


def test_marriage_emits_both_parties_sharing_a_pair_key():
    rows = parse_marriage(PDF_DIR / "marriage_records2.pdf")
    groom = [r for r in rows if r.surname == "Atwood" and r.given == "Julius"][0]
    bride = [r for r in rows if r.pair_key == groom.pair_key and r.role == "bride"][0]
    assert groom.role == "groom"
    assert bride.surname == "Smilie" and bride.given == "Louisa"
    assert groom.date_iso == bride.date_iso == "1849-08-22"


def test_vital_rows_are_plausible_in_number():
    assert 1000 <= len(parse_birth(PDF_DIR / "birth_records.pdf")) <= 4000
    assert 800 <= len(parse_marriage(PDF_DIR / "marriage_records2.pdf")) <= 1200
