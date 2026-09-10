"""Fast, isolated tests for scripts/validate.py.

test_golden.py exercises the validator against the real 16-source corpus;
these use a synthetic single-source DB so each check's edge cases (tolerance
boundary, orphan rows, review-report reasons) can be pinned without waiting
on a full import.
"""
import pytest
from conftest import PDF_DIR
from scripts.db import connect, init_schema


def make_appearance(conn, source_id=1, surname="Atwood", given="Ruth", page=1,
                    import_key="k1", raw_line="Atwood Ruth 11 Feb 1831",
                    surname_key="ATT", kind="burial", date_raw=None,
                    date_iso=None, status="active", edited_at=None, key_seen=1):
    conn.execute(
        "INSERT INTO appearance (source_id,page,import_key,raw_line,surname,"
        "given,surname_key,kind,status,date_raw,date_iso,edited_at,key_seen) VALUES"
        " (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (source_id, page, import_key, raw_line, surname, given, surname_key,
         kind, status, date_raw, date_iso, edited_at, key_seen))


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "t.sqlite")
    init_schema(c)
    c.execute("INSERT INTO source (filename,title,kind,pages,sha256,imported_at)"
              " VALUES ('x.pdf','X','cemetery',1,'s','now')")
    c.commit()
    return c


# ---- check_counts ----

def test_check_counts_passes_when_matching(conn):
    for i in range(100):
        make_appearance(conn, import_key=f"k{i}")
    conn.commit()
    from scripts.validate import check_counts
    assert check_counts(conn, {"x.pdf": 100}) == []


def test_check_counts_flags_drift_beyond_tolerance(conn):
    for i in range(90):
        make_appearance(conn, import_key=f"k{i}")
    conn.commit()
    from scripts.validate import check_counts
    problems = check_counts(conn, {"x.pdf": 100})
    assert len(problems) == 1
    assert "x.pdf" in problems[0]


def test_check_counts_passes_at_the_tolerance_boundary(conn):
    # 2% of 100 is 2, so 98 (a 2% drop) must still pass.
    for i in range(98):
        make_appearance(conn, import_key=f"k{i}")
    conn.commit()
    from scripts.validate import check_counts
    assert check_counts(conn, {"x.pdf": 100}) == []


def test_check_counts_fails_just_past_the_tolerance_boundary(conn):
    for i in range(97):
        make_appearance(conn, import_key=f"k{i}")
    conn.commit()
    from scripts.validate import check_counts
    assert check_counts(conn, {"x.pdf": 100}) != []


def test_check_counts_ignores_zero_baseline(conn):
    from scripts.validate import check_counts
    assert check_counts(conn, {"x.pdf": 0}) == []


def test_check_counts_flags_nonzero_rows_against_a_zero_baseline(conn):
    make_appearance(conn)
    conn.commit()
    from scripts.validate import check_counts
    problems = check_counts(conn, {"x.pdf": 0})
    assert any("x.pdf" in p for p in problems)


def test_check_counts_flags_a_db_source_missing_from_the_baseline(conn):
    # conn's fixture already inserted the 'x.pdf' source; an empty baseline
    # has no entry for it at all.
    from scripts.validate import check_counts
    problems = check_counts(conn, {})
    assert any("x.pdf" in p for p in problems)


def test_check_counts_ignores_manual_rows_not_in_any_pdf(conn):
    """The schema's origin='manual' + nullable import_key exist so a
    volunteer can add someone who appears in no PDF (spec: 'editors can ...
    add a record that exists in no PDF'). check_counts measures the
    extraction, not what a human later adds on top of it -- manual rows must
    never count as drift against a baseline that only knows the PDF."""
    for i in range(100):
        make_appearance(conn, import_key=f"k{i}")
    # 5 manual, PDF-absent rows on top of 100 imported: 5% drift if origin
    # leaks into the count -- well past 2% tolerance -- 0% if it doesn't.
    for i in range(5):
        conn.execute(
            "INSERT INTO appearance (source_id,page,import_key,raw_line,"
            "surname,given,surname_key,kind,origin) VALUES"
            " (1,1,NULL,NULL,'Smith',?,'SMT','burial','manual')", (f"Person{i}",))
    conn.commit()
    from scripts.validate import check_counts
    assert check_counts(conn, {"x.pdf": 100}) == []


def test_check_counts_only_counts_active_rows(conn):
    # 3 retired rows on top of 100 active is a 3% drift if retired rows leak
    # into the count -- well past the 2% tolerance -- but 0% if they don't.
    for i in range(100):
        make_appearance(conn, import_key=f"k{i}")
    for i in range(3):
        make_appearance(conn, import_key=f"retired{i}", status="retired")
    conn.commit()
    from scripts.validate import check_counts
    assert check_counts(conn, {"x.pdf": 100}) == []


# ---- check_integrity ----

def test_check_integrity_passes_on_a_clean_db(conn):
    make_appearance(conn)
    conn.commit()
    from scripts.validate import check_integrity
    assert check_integrity(conn) == []


def test_check_integrity_flags_orphan_appearance(conn):
    make_appearance(conn)
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM source WHERE id=1")
    conn.commit()
    from scripts.validate import check_integrity
    problems = check_integrity(conn)
    assert any("no source" in p for p in problems)


def test_check_integrity_flags_zero_page(conn):
    make_appearance(conn, page=0)
    conn.commit()
    from scripts.validate import check_integrity
    assert any("page" in p for p in check_integrity(conn))


def test_check_integrity_flags_missing_surname(conn):
    make_appearance(conn, surname="")
    conn.commit()
    from scripts.validate import check_integrity
    assert any("surname" in p for p in check_integrity(conn))


# ---- review_report ----

def test_review_report_is_empty_for_a_clean_row(conn):
    make_appearance(conn, surname="Atwood", given="Ruth", date_raw="11 Feb 1831",
                    date_iso="1831-02-11", raw_line="Atwood Ruth 11 Feb 1831")
    conn.commit()
    from scripts.validate import review_report
    assert review_report(conn) == []


def test_review_report_flags_unparseable_date(conn):
    make_appearance(conn, date_raw="garbage", date_iso=None)
    conn.commit()
    from scripts.validate import review_report
    flags = review_report(conn)
    assert len(flags) == 1
    assert flags[0]["reasons"] == ["date not parseable"]


def test_review_report_flags_short_surname(conn):
    make_appearance(conn, surname="A")
    conn.commit()
    from scripts.validate import review_report
    flags = review_report(conn)
    assert "surname suspiciously short" in flags[0]["reasons"]


def test_review_report_flags_missing_given_name(conn):
    make_appearance(conn, given=None)
    conn.commit()
    from scripts.validate import review_report
    flags = review_report(conn)
    assert "no given name" in flags[0]["reasons"]


def test_review_report_flags_lowercase_surname(conn):
    make_appearance(conn, surname="atwood")
    conn.commit()
    from scripts.validate import review_report
    flags = review_report(conn)
    assert "surname not capitalised" in flags[0]["reasons"]


def test_review_report_ignores_retired_rows(conn):
    make_appearance(conn, surname="a", status="retired")
    conn.commit()
    from scripts.validate import review_report
    assert review_report(conn) == []


def test_review_report_flags_a_merged_word_token(conn):
    make_appearance(
        conn, surname="Wilford", given="John",
        raw_line="Bk B p 227 18 Aug 1830 John AlexanderWilley Mary WellingtonStearns")
    conn.commit()
    from scripts.validate import review_report
    flags = review_report(conn)
    assert flags[0]["reasons"] == ["possible merged words in raw_line"]


def test_review_report_does_not_flag_ordinary_names_as_merged(conn):
    make_appearance(conn, surname="Atwood", given="Ruth",
                    raw_line="Atwood Ruth Burns Cloverdale 1831")
    conn.commit()
    from scripts.validate import review_report
    assert review_report(conn) == []


def test_review_report_flags_a_likely_reversed_name(conn):
    """A surname vanishingly rare in the corpus (<=1, i.e. only this row)
    paired with a given name whose first token is common as a surname
    elsewhere (>=5) looks like the two fields got swapped in transcription --
    the shape of the spec's own exemplar, Cloverdale's Alida/Seeley row."""
    for i in range(5):
        make_appearance(conn, import_key=f"seeley{i}", surname="Seeley",
                        given=f"Person{i}")
    make_appearance(conn, import_key="reversed", surname="Alida", given="Seeley")
    conn.commit()
    from scripts.validate import review_report
    flags = [f for f in review_report(conn) if f["name"] == "Alida, Seeley"]
    assert flags, "expected the reversed-looking row to be flagged"
    assert "name may be reversed" in flags[0]["reasons"]


def test_review_report_does_not_flag_a_common_surname_as_reversed(conn):
    for i in range(5):
        make_appearance(conn, import_key=f"atwood{i}", surname="Atwood",
                        given=f"Person{i}")
    conn.commit()
    from scripts.validate import review_report
    assert not any("name may be reversed" in f["reasons"] for f in review_report(conn))


def test_review_report_flags_an_edited_row_whose_key_went_stale(conn):
    """A hand correction whose source line changed or vanished is never
    retired (see import_pdfs.upsert) but must surface for a human to
    reconcile against the current PDF text."""
    make_appearance(conn, import_key="edited", edited_at="2026-01-01", key_seen=0)
    conn.commit()
    from scripts.validate import review_report
    flags = review_report(conn)
    assert len(flags) == 1
    assert flags[0]["reasons"] == ["hand correction's source line has changed or vanished"]


def test_review_report_does_not_flag_an_edited_row_whose_key_is_current(conn):
    make_appearance(conn, import_key="edited", edited_at="2026-01-01", key_seen=1)
    conn.commit()
    from scripts.validate import review_report
    assert review_report(conn) == []


# ---- reconcile ----

def test_source_row_key_keeps_a_duplicate_suffix_that_follows_a_role():
    """<sha1>:groom-1 is a different source row from <sha1>:groom.

    Splitting at the first ':' would discard the -N and merge them.
    """
    from scripts.validate import _source_row_key

    sha = "a" * 40
    assert _source_row_key(sha) == sha
    assert _source_row_key(f"{sha}:groom") == sha
    assert _source_row_key(f"{sha}:bride") == sha
    assert _source_row_key(f"{sha}-1") == f"{sha}-1"
    assert _source_row_key(f"{sha}:groom-1") == f"{sha}-1"
    assert _source_row_key(f"{sha}:bride-1") == f"{sha}-1"
    # the two halves of one marriage collapse together; a duplicate row does not
    assert _source_row_key(f"{sha}:groom") == _source_row_key(f"{sha}:bride")
    assert _source_row_key(f"{sha}:groom") != _source_row_key(f"{sha}:groom-1")


def test_reconcile_matches_parser_output_for_a_small_real_source(tmp_path):
    """riverroad.pdf is small (20 rows) and clean -- every row keeps its
    surname, so rows_in and rows_out must match exactly with zero delta."""
    from scripts.import_pdfs import _dedupe_import_keys, upsert
    from scripts.parsers.cemetery import parse_cemetery
    from scripts.validate import reconcile

    c = connect(tmp_path / "t.sqlite")
    init_schema(c)
    c.execute("INSERT INTO source (filename,title,kind,pages,sha256,imported_at)"
              " VALUES ('riverroad.pdf','River Road Cemetery','cemetery',1,'s','now')")
    c.commit()
    sid = c.execute("SELECT id FROM source WHERE filename='riverroad.pdf'"
                    ).fetchone()["id"]
    rows = parse_cemetery(PDF_DIR / "riverroad.pdf", "River Road Cemetery")
    _dedupe_import_keys(rows)
    upsert(c, sid, rows)

    result = reconcile(c, PDF_DIR)["riverroad.pdf"]
    assert result == {"rows_in": 20, "rows_out": 20, "delta": 0}


def test_reconcile_collapses_role_fanout_to_one_source_row(tmp_path):
    """One birth row fans out into child/father/mother appearances sharing a
    base import_key (sha, 'sha:father', 'sha:mother'). rows_out must count
    that as one source row, not three, or every multi-role row inflates the
    count and a real drop elsewhere gets diluted out of sight."""
    from scripts.validate import reconcile

    c = connect(tmp_path / "t.sqlite")
    init_schema(c)
    # riverroad.pdf is a real, small SOURCES entry -- reused here only so
    # reconcile() recognises the filename; the fan-out rows below are synthetic.
    c.execute("INSERT INTO source (filename,title,kind,pages,sha256,imported_at)"
              " VALUES ('riverroad.pdf','River Road Cemetery','cemetery',1,'s','now')")
    c.commit()
    sid = c.execute("SELECT id FROM source WHERE filename='riverroad.pdf'"
                    ).fetchone()["id"]
    sha = "a" * 40
    make_appearance(c, source_id=sid, import_key=sha)
    make_appearance(c, source_id=sid, import_key=f"{sha}:father")
    make_appearance(c, source_id=sid, import_key=f"{sha}:mother")
    c.commit()

    assert reconcile(c, PDF_DIR)["riverroad.pdf"]["rows_out"] == 1


def test_reconcile_keeps_duplicate_marriage_rows_distinct(tmp_path):
    """Two genuinely distinct source rows that happen to hash the same (a
    byte-identical duplicate line) fan out into groom/bride pairs sharing one
    sha but different -N dedup suffixes: sha:groom, sha:bride, sha:groom-1,
    sha:bride-1. rows_out must read that as 2 source rows, not 1 -- splitting
    at the first ':' would discard the -N and collapse them, fabricating a
    dropped-row signal for two rows that both made it in."""
    from scripts.validate import reconcile

    c = connect(tmp_path / "t.sqlite")
    init_schema(c)
    c.execute("INSERT INTO source (filename,title,kind,pages,sha256,imported_at)"
              " VALUES ('marriage_records2.pdf','Marriage records','vital',1,"
              "'s','now')")
    c.commit()
    sid = c.execute("SELECT id FROM source WHERE filename='marriage_records2.pdf'"
                    ).fetchone()["id"]
    sha = "b" * 40
    for key in (sha + ":groom", sha + ":bride",
                sha + ":groom-1", sha + ":bride-1"):
        make_appearance(c, source_id=sid, import_key=key)
    c.commit()

    assert reconcile(c, PDF_DIR)["marriage_records2.pdf"]["rows_out"] == 2


def test_reconcile_catches_the_known_dropped_marriage_row(tmp_path):
    """marriage_records2 p.15 prints 'John AlexanderWilley Mary
    WellingtonStearns' -- both surname columns land empty, so parse_marriage
    skips the whole row and it produces zero appearances. reconcile must show
    that as a nonzero delta rather than a silent match."""
    from scripts.import_pdfs import _dedupe_import_keys, upsert
    from scripts.parsers.vital import parse_marriage
    from scripts.validate import reconcile

    c = connect(tmp_path / "t.sqlite")
    init_schema(c)
    c.execute("INSERT INTO source (filename,title,kind,pages,sha256,imported_at)"
              " VALUES ('marriage_records2.pdf','Marriage records','vital',1,"
              "'s','now')")
    c.commit()
    sid = c.execute("SELECT id FROM source WHERE filename='marriage_records2.pdf'"
                    ).fetchone()["id"]
    rows = parse_marriage(PDF_DIR / "marriage_records2.pdf")
    _dedupe_import_keys(rows)
    upsert(c, sid, rows)

    result = reconcile(c, PDF_DIR)["marriage_records2.pdf"]
    assert result["delta"] >= 1


def test_reconcile_skips_sources_not_yet_in_the_db(conn):
    from scripts.validate import reconcile
    assert reconcile(conn, PDF_DIR) == {}
