import pytest

from conftest import PDF_DIR
from scripts.extract import extract_words
from scripts.layout import group_rows, detect_columns, assign_columns, iter_table_pages


def rows_for(stem, page=1):
    return group_rows(extract_words(PDF_DIR / f"{stem}.pdf", page))


def test_groups_words_into_rows():
    rows = rows_for("cloverdale")
    assert [w.text for w in rows[0]] == ["Last", "Name", "First", "Name",
                                         "Maiden", "Name", "Born", "Died", "Age",
                                         "Spouse", "Mother", "Father", "Notes"]


def test_detects_cemetery_columns():
    rows = rows_for("cloverdale")
    cols = [c.name for c in detect_columns(rows[0])]
    assert cols == ["Last Name", "First Name", "Maiden Name", "Born", "Died",
                    "Age", "Spouse", "Mother", "Father", "Notes"]


def test_assigns_values_to_columns():
    rows = rows_for("cloverdale")
    cols = detect_columns(rows[0])
    # Row 3 on page 1: Atwood / Margaret, died 1869-9-29 aged 36 yrs.
    match = [r for r in rows if any(w.text == "Margaret" for w in r)][0]
    got = assign_columns(match, cols)
    assert got["Last Name"] == "Atwood"
    assert got["First Name"] == "Margaret"
    assert got["Died"] == "1869-9-29"
    assert got["Age"] == "36 yrs"
    assert got["Spouse"] == "Lewis Atwood"


def test_right_aligned_age_still_lands_in_age():
    """'86 yrs 9 mos' is wider than its header and right-aligned."""
    rows = rows_for("cloverdale")
    cols = detect_columns(rows[0])
    # Find row where Thomas is the first name (appears early in the row),
    # not where it appears as a spouse name later in the row.
    match = [r for r in rows if len(r) > 1 and r[1].text == "Thomas"][0]
    assert assign_columns(match, cols)["Age"] == "86 yrs 9 mos"


def test_detect_columns_adapts_to_each_files_letter_tracking():
    """South Cambridge tracks ~4x wider than East Cambridge; both must parse."""
    for stem in ("eastcambridge", "cloverdale", "southcambridge"):
        rows = rows_for(stem)
        names = [c.name for c in detect_columns(rows[0])][:5]
        assert names == ["Last Name", "First Name", "Maiden Name", "Born", "Died"], stem


def test_detect_columns_honours_an_explicit_gap_override():
    rows = rows_for("cloverdale")
    # 0.0 forces every gap to separate columns, splitting compound headings.
    assert [c.name for c in detect_columns(rows[0], gap=0.0)][:2] == ["Last", "Name"]


CEMETERY_COLS = ["Last Name", "First Name", "Maiden Name", "Born", "Died", "Age"]

# Every record table, not just the cemeteries. freemansworn_records is absent
# deliberately: its header sits on row 1 under a title line, which Task 8 fixes
# in iter_table_pages' header detection.
EXPECTED_HEADERS = {
    **{stem: CEMETERY_COLS for stem in (
        "cloverdale", "eastcambridge", "gates", "hopkins", "jeffersonville",
        "mtview", "northcambridge", "plainsroad", "riverroad", "smilie",
        "southcambridge")},
    "birth_records": ["Volume", "Birth Day", "Child", "Family Name", "Father"],
    "marriage_records2": ["Volume", "Marriage Date", "Groom First", "Groom Last",
                          "Bride First", "Bride Last", "Notes"],
    "death_records": ["Volume/Page", "First Name", "Last Name", "Date", "Age"],
    "warningsout_records": ["Volume", "Date of Warning", "Last Name", "First Name"],
}


@pytest.mark.parametrize("stem,expected", sorted(EXPECTED_HEADERS.items()))
def test_detect_columns_handles_every_record_table(stem, expected):
    """One threshold must serve every record type, not just the cemeteries.

    Letter-tracking differs per file, so the boundary ratio between intra-heading
    and inter-column spacing ranges from 1.82 (marriages) to 9.48 (Gates).
    """
    rows = rows_for(stem)
    names = [c.name for c in detect_columns(rows[0])]
    assert names[:len(expected)] == expected


def test_iter_table_pages_reads_header_once_and_reuses_columns():
    pages = list(iter_table_pages(PDF_DIR / "cloverdale.pdf"))
    assert pages, "expected at least one page of table data"
    first_page, cols, rows = pages[0]
    assert first_page == 1
    assert [c.name for c in cols][:3] == ["Last Name", "First Name", "Maiden Name"]
    assert all(page_cols is cols for _, page_cols, _ in pages), \
        "later pages must reuse the columns detected on the first"
    assert not {"Last", "Name", "First"}.issubset({w.text for w in rows[0]}), \
        "the header row must be consumed, not yielded as data"
