import json
import pathlib
import pytest
from scripts.db import connect, init_schema
from scripts.import_pdfs import import_all
from conftest import PDF_DIR

BASELINE = pathlib.Path(__file__).parent.parent / "data" / "baseline.json"


@pytest.fixture(scope="module")
def conn():
    c = connect(":memory:")
    init_schema(c)
    import_all(c, PDF_DIR)
    return c


def q(conn, sql, *args):
    return conn.execute(sql, args).fetchall()


def test_row_counts_match_baseline(conn):
    from scripts.validate import check_counts
    assert check_counts(conn, json.loads(BASELINE.read_text())) == []


def test_no_orphan_or_pageless_appearances(conn):
    from scripts.validate import check_integrity
    assert check_integrity(conn) == []


def test_golden_ruth_atwood(conn):
    r = q(conn, "SELECT * FROM appearance WHERE surname='Atwood' AND given='Ruth'"
                " AND kind='burial'")[0]
    assert r["date_iso"] == "1831-02-11"
    assert r["place"] == "Cloverdale Cemetery"


def test_golden_phonetic_search_finds_variants(conn):
    from scripts.normalize import surname_key
    rows = q(conn, "SELECT DISTINCT surname FROM appearance WHERE surname_key=?",
             surname_key("Atwood"))
    assert len(rows) >= 1


def test_every_appearance_has_a_surname_key(conn):
    assert q(conn, "SELECT COUNT(*) c FROM appearance WHERE surname_key=''"
             )[0]["c"] == 0


def test_total_is_in_the_expected_range(conn):
    total = q(conn, "SELECT COUNT(*) c FROM appearance")[0]["c"]
    assert 7000 <= total <= 15000


def test_reconciliation_total_delta_is_small(conn):
    """The gap between source table rows and appearances they produced must stay
    small and visible. A parser regression that starts silently dropping rows
    (see marriage_records2 p.15, 'John AlexanderWilley') would blow this up."""
    from scripts.validate import reconcile
    recon = reconcile(conn, PDF_DIR)
    total_in = sum(r["rows_in"] for r in recon.values())
    total_delta = sum(r["delta"] for r in recon.values())
    assert total_delta / total_in < 0.01


def test_review_report_flags_a_known_merged_word_row(conn):
    """marriage_records2 p.? has a groom whose given and surname printed with no
    gap ('Thomas RusselHawley' instead of 'Thomas Russel Hawley') -- unlike the
    p.15 AlexanderWilley/WellingtonStearns row (both surnames empty, whole row
    dropped -- see the reconciliation test), this row keeps a nonempty surname
    so it lands in the database, and review_report must still catch the
    artifact for a human to fix."""
    from scripts.validate import review_report
    flags = review_report(conn)
    assert any(f["name"].startswith("RusselHawley") and
               any("merged" in reason.lower() for reason in f["reasons"])
               for f in flags)
