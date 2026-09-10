from conftest import PDF_DIR
from scripts.parsers.cemetery import parse_cemetery
from scripts.parsers.simple import parse_death, parse_warning, parse_freeman
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


def test_no_cemetery_emits_its_header_as_a_person():
    for stem in ("mtview", "jeffersonville", "northcambridge", "southcambridge",
                 "plainsroad", "eastcambridge", "hopkins", "smilie"):
        rows = parse_cemetery(PDF_DIR / f"{stem}.pdf", stem)
        bogus = [a for a in rows if a.surname == "Last Name" or a.given == "First Name"]
        assert bogus == [], f"{stem} emitted {len(bogus)} header rows as people"


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


def test_birth_recovers_the_mother_from_the_second_pass():
    rows = parse_birth(PDF_DIR / "birth_records.pdf")
    child = [r for r in rows if r.given == "Adalia Ellen" and r.role == "child"][0]
    mother = [r for r in rows if r.pair_key == child.pair_key and r.role == "mother"][0]
    assert mother.surname == "Adams"          # family surname, as with fathers
    assert mother.given                        # she has a given name
    assert mother.date_iso == child.date_iso


def test_birth_second_pass_does_not_leak_note_fragments_as_people():
    rows = parse_birth(PDF_DIR / "birth_records.pdf")
    assert not [r for r in rows if '"' in r.surname or "oclock" in (r.given or "")]


def test_death_extracts_person_and_date():
    rows = parse_death(PDF_DIR / "death_records.pdf")
    levi = [r for r in rows if r.surname == "Atwood" and r.given == "Levi"][0]
    assert levi.kind == "death" and levi.date_iso == "1813-02-21"


def test_warning_extracts_person_and_date():
    rows = parse_warning(PDF_DIR / "warningsout_records.pdf")
    asa = [r for r in rows if r.surname == "Adams" and r.given == "Asa"][0]
    assert asa.kind == "warning" and asa.date_iso == "1815-12-06"


def test_freeman_extracts_person_and_date():
    rows = parse_freeman(PDF_DIR / "freemansworn_records.pdf")
    dexter = [r for r in rows if r.surname == "Adams" and r.given == "Dexter"][0]
    assert dexter.kind == "freeman" and dexter.date_iso == "1828-09-02"


def test_death_does_not_leak_the_kinship_and_cause_passes():
    """death_records prints three passes over the same pages: death core
    (Volume/Page, First/Last Name, Date, Age) on pages 1-5, then a
    Father/Mother/Spouse table for the same rows on pages 6-10, then a Cause
    table on pages 11-15. iter_table_pages reuses page-1's columns for every
    later page too, so without a page bound, words from the later passes get
    misassigned onto the death columns — a father's name or a cause-of-death
    fragment turning into a fake death row. Every genuine death row carries a
    raw date string; a leaked row from the later passes does not.
    """
    rows = parse_death(PDF_DIR / "death_records.pdf")
    assert all(r.date_raw for r in rows)


def test_simple_parsers_have_plausible_counts():
    assert 200 <= len(parse_death(PDF_DIR / "death_records.pdf")) <= 400
    assert 90 <= len(parse_warning(PDF_DIR / "warningsout_records.pdf")) <= 200
    assert 800 <= len(parse_freeman(PDF_DIR / "freemansworn_records.pdf")) <= 1100
