import pytest

import scripts.layout as layout
from conftest import PDF_DIR
from scripts.extract import Word, extract_words
from scripts.import_pdfs import CEMETERIES, SOURCES
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


def test_assign_columns_never_collapses_duplicate_column_names():
    """gap=0.0 splits Last/First/Maiden Name into three separate columns that
    all share the bare name 'Name'. assign_columns keys its output dict by
    column name, so before disambiguation those three distinct spans collapse
    onto one dict key and two of the three spans' values vanish."""
    rows = rows_for("cloverdale")
    cols = detect_columns(rows[0], gap=0.0)
    assert len(cols) == 13
    assert len({c.name for c in cols}) == 13, "detect_columns must not emit duplicate names"

    match = [r for r in rows if any(w.text == "Margaret" for w in r)][0]
    got = assign_columns(match, cols)
    assert len(got) == 13, "assign_columns must not lose columns to name collisions"


CEMETERY_COLS = ["Last Name", "First Name", "Maiden Name", "Born", "Died", "Age"]

# freemansworn_records is deliberately exempt from EXPECTED_HEADERS below:
# its header sits on row 1 under a title line ("Freeman's Oaths Taken"), so
# rows[0] isn't its header the way it is for every other source -- see
# test_iter_table_pages_skips_a_title_row_via_header_contains.
_NO_HEADER_EXPECTATION = {"freemansworn_records"}

# Every record table, not just the cemeteries -- the cemetery stems come
# from import_pdfs.CEMETERIES (the same dict SOURCES is built from) so a
# newly added cemetery is covered automatically instead of silently
# skipped; see test_expected_headers_covers_every_source below for the
# non-cemetery sources.
EXPECTED_HEADERS = {
    **{stem: CEMETERY_COLS for stem in CEMETERIES},
    "birth_records": ["Volume", "Birth Day", "Child", "Family Name", "Father"],
    "marriage_records2": ["Volume", "Marriage Date", "Groom First", "Groom Last",
                          "Bride First", "Bride Last", "Notes"],
    "death_records": ["Volume/Page", "First Name", "Last Name", "Date", "Age"],
    "warningsout_records": ["Volume", "Date of Warning", "Last Name", "First Name"],
}


def test_expected_headers_covers_every_source_except_the_documented_exemption():
    """A source added to SOURCES (per scripts/README.md's "Adding a source")
    with no matching entry here would get zero header-detection coverage from
    test_detect_columns_handles_every_record_table below, and this file would
    keep passing regardless -- the exact silent-omission risk this pins."""
    missing = set(SOURCES) - set(EXPECTED_HEADERS) - _NO_HEADER_EXPECTATION
    assert missing == set(), f"no header expectation for: {sorted(missing)}"


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


def test_iter_table_pages_forwards_gap_to_detect_columns():
    """detect_columns's docstring says pass `gap` to override the derived
    threshold; iter_table_pages must actually forward it, or no production
    caller can reach the override it promises."""
    pages = list(iter_table_pages(PDF_DIR / "cloverdale.pdf", gap=0.0))
    _, cols, _ = pages[0]
    # gap=0.0 forces every header gap to separate columns, splitting the
    # compound heading "Last Name" into two -- only reachable if gap arrives.
    assert [c.name for c in cols][:2] == ["Last", "Name"]


def test_iter_table_pages_raises_a_clear_error_for_an_unmatched_header_contains():
    with pytest.raises(ValueError, match="nonexistentword"):
        list(iter_table_pages(PDF_DIR / "cloverdale.pdf",
                              header_contains="nonexistentword"))


def test_iter_table_pages_skips_a_title_row_via_header_contains():
    """freemansworn_records prints a caption ("Freeman's Oaths Taken") above
    its real header; header_contains lets the caller name a word only the
    real header carries, so the caption is dropped instead of misread as columns.
    """
    pages = list(iter_table_pages(PDF_DIR / "freemansworn_records.pdf",
                                  header_contains="Volume"))
    _, cols, rows = pages[0]
    assert [c.name for c in cols] == ["Volume", "Date of Oath", "First Name", "Last Name"]
    assert not any("Oaths" in w.text for w in rows[0]), \
        "the title row must be dropped, not yielded as data"


def test_iter_table_pages_skips_a_leading_cover_page_via_header_contains(monkeypatch):
    """A cover/title page that comes BEFORE the header, as its own page
    rather than as an extra row above the header on the same page (see
    test_iter_table_pages_skips_a_title_row_via_header_contains for that
    case), must not abort the read -- the docstring says the header is
    found on the first page that has one, so a page with no match should be
    skipped, not treated as an error. Only once no page in the whole range
    matches should this raise (see
    test_iter_table_pages_raises_a_clear_error_for_an_unmatched_header_contains).

    None of the 16 real record PDFs happen to have this exact shape (a
    whole separate cover page ahead of the header page), so the extraction
    boundary (extract_words/page_count) is faked here -- the real
    group_rows/detect_columns/assign_columns/header-matching machinery
    under test runs unmodified, the same pattern
    test_paired_mothers_rejects_a_page_offset_mismatch in test_parsers.py
    uses to isolate a boundary case with no real-file example.
    """
    cover = [Word(text="Cover", x0=0, x1=20, y0=0, y1=10)]
    header = [Word(text="Volume", x0=0, x1=20, y0=0, y1=10),
              Word(text="Name", x0=40, x1=60, y0=0, y1=10)]
    data = [Word(text="1", x0=0, x1=10, y0=20, y1=30),
            Word(text="Smith", x0=40, x1=60, y0=20, y1=30)]
    pages = {1: cover, 2: header, 3: data}

    monkeypatch.setattr(layout, "extract_words", lambda path, page: pages.get(page, []))
    monkeypatch.setattr(layout, "page_count", lambda path: 3)

    out = list(layout.iter_table_pages(PDF_DIR / "fake.pdf", header_contains="Volume"))

    header_page, cols, _ = out[0]
    assert header_page == 2, "cover page 1 must be skipped, not mistaken for the header"
    assert [c.name for c in cols] == ["Volume", "Name"]

    data_pages = [(p, [w.text for row in rows for w in row]) for p, _, rows in out if rows]
    assert data_pages == [(3, ["1", "Smith"])]


def test_iter_table_pages_drops_headers_reprinted_on_later_pages():
    """Most cemetery files reprint their column header on every page.

    header_texts is read from the file's own header row rather than hand-typed,
    so the check can't drift from what the real header actually says (mtview's
    carries Spouse/Mother/Father/Notes too — a fixed, incomplete word list here
    would make this assert trivially true regardless of whether the fix works).
    """
    header_row = rows_for("mtview")[0]
    header_texts = tuple(w.text for w in header_row)
    pages = list(iter_table_pages(PDF_DIR / "mtview.pdf"))
    for page, _cols, rows in pages:
        for row in rows:
            assert tuple(w.text for w in row) != header_texts, \
                f"header row leaked as data on page {page}"
