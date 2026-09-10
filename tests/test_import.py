import pytest
from conftest import PDF_DIR
from scripts.db import connect, init_schema
from scripts.import_pdfs import _dedupe_import_keys, import_all, upsert
from scripts.parsers import Appearance


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "t.sqlite")
    init_schema(c)
    c.execute("INSERT INTO source (filename,title,kind,pages,sha256,imported_at)"
              " VALUES ('x.pdf','X','cemetery',1,'s','now')")
    c.commit()
    return c


def make(key="k1", given="Ruth"):
    return Appearance(surname="Atwood", given=given, surname_key="ATT",
                      kind="burial", page=1, raw_line="raw", import_key=key)


def test_insert_then_update_is_idempotent(conn):
    assert upsert(conn, 1, [make()]) == (1, 0, 0)
    assert upsert(conn, 1, [make()]) == (0, 1, 0)
    assert conn.execute("SELECT COUNT(*) c FROM appearance").fetchone()["c"] == 1


def test_hand_edited_rows_are_never_overwritten(conn):
    upsert(conn, 1, [make(given="Ruth")])
    conn.execute("UPDATE appearance SET given='Ruthe', edited_at='2026-01-01',"
                 " edited_by='jen'")
    conn.commit()
    assert upsert(conn, 1, [make(given="Ruth")]) == (0, 0, 1)
    assert conn.execute("SELECT given FROM appearance").fetchone()["given"] == "Ruthe"


def test_edited_row_is_never_retired_even_if_its_key_vanishes(conn):
    """A human corrected this row; re-running import must never silently
    retire it just because its source line changed or disappeared -- that
    would make the correction unreachable from every status='active' query,
    which is exactly what review_report and reconcile both filter to."""
    upsert(conn, 1, [make(key="edited")])
    conn.execute("UPDATE appearance SET given='Ruthe', edited_at='2026-01-01',"
                 " edited_by='jen' WHERE import_key='edited'")
    conn.commit()
    upsert(conn, 1, [make(key="unrelated")])  # 'edited' key absent from this parse
    row = conn.execute("SELECT status, given, key_seen FROM appearance"
                       " WHERE import_key='edited'").fetchone()
    assert row["status"] == "active"
    assert row["given"] == "Ruthe"
    assert row["key_seen"] == 0


def test_edited_rows_key_seen_flag_clears_when_the_key_reappears(conn):
    upsert(conn, 1, [make(key="edited")])
    conn.execute("UPDATE appearance SET edited_at='2026-01-01' WHERE import_key='edited'")
    conn.commit()
    upsert(conn, 1, [make(key="unrelated")])  # key goes missing -> key_seen=0
    upsert(conn, 1, [make(key="edited")])     # key reappears byte-identical
    row = conn.execute("SELECT key_seen FROM appearance WHERE import_key='edited'").fetchone()
    assert row["key_seen"] == 1


def test_retired_edited_row_reactivates_when_its_key_reappears(conn):
    """A row can be retired (unedited, source vanished) and later
    hand-edited by a human correcting the stale data. If its key then
    reappears in a later import, the row must come back to status='active'
    -- not stay retired forever, invisible to review_report's active-only
    view.

    status='retired' and key_seen must come from the real retire path (via
    upsert), not be hand-seeded -- the retire path sets status only, so a
    row hand-seeded with status='retired', key_seen=0 together is a state
    upsert itself can never produce, and a test built on it can pass against
    broken code. edited_at/edited_by are hand-set because no correction
    tooling exists yet in this phase; that's the only unavoidable seed.
    """
    upsert(conn, 1, [make(key="k")])
    upsert(conn, 1, [make(key="unrelated")])  # 'k' absent this run -> retired
    row = conn.execute("SELECT status, key_seen FROM appearance"
                       " WHERE import_key='k'").fetchone()
    assert (row["status"], row["key_seen"]) == ("retired", 0)

    conn.execute("UPDATE appearance SET edited_at='2026-01-01', edited_by='jen'"
                 " WHERE import_key='k'")
    conn.commit()
    upsert(conn, 1, [make(key="k")])  # key reappears byte-identical
    row = conn.execute("SELECT status FROM appearance WHERE import_key='k'").fetchone()
    assert row["status"] == "active"


def test_update_path_resets_a_stale_key_seen_flag(conn):
    """key_seen=0 must not survive on a row whose key is present in the
    current import, or a stale flag from an earlier edit cycle falsely
    reads forever as 'source line has changed or vanished'."""
    upsert(conn, 1, [make(key="k")])
    conn.execute("UPDATE appearance SET key_seen=0 WHERE import_key='k'")
    conn.commit()
    upsert(conn, 1, [make(key="k")])  # normal re-import, unedited, key present
    row = conn.execute("SELECT key_seen FROM appearance WHERE import_key='k'").fetchone()
    assert row["key_seen"] == 1


def test_rows_absent_from_reimport_are_retired_not_deleted(conn):
    upsert(conn, 1, [make(key="gone")])
    upsert(conn, 1, [make(key="stays")])
    row = conn.execute("SELECT status FROM appearance WHERE import_key='gone'"
                       ).fetchone()
    assert row["status"] == "retired"
    assert conn.execute("SELECT COUNT(*) c FROM appearance").fetchone()["c"] == 2


def test_import_all_loads_every_source():
    from scripts.db import connect as c2
    conn = c2(":memory:")
    init_schema(conn)
    counts = import_all(conn, PDF_DIR)
    assert len(counts) == 16
    assert sum(counts.values()) > 7000


def test_dedupe_leaves_distinct_keys_untouched():
    rows = [make(key="a"), make(key="b"), make(key="c")]
    _dedupe_import_keys(rows)
    assert [r.import_key for r in rows] == ["a", "b", "c"]


def test_dedupe_suffixes_only_repeats_after_the_first():
    """The first occurrence must keep its bare key, or every existing DB row
    desyncs and re-import silently orphans every hand correction."""
    rows = [make(key="dup"), make(key="dup"), make(key="dup"), make(key="other")]
    _dedupe_import_keys(rows)
    assert [r.import_key for r in rows] == ["dup", "dup-1", "dup-2", "other"]


def test_dedupe_is_stable_across_repeated_parses_of_real_duplicates():
    """mtview page 52 carries byte-identical ledger lines. The same row must get
    the same key on every run, or a volunteer's edit is orphaned next import.
    """
    from conftest import PDF_DIR
    from scripts.parsers.cemetery import parse_cemetery

    first = parse_cemetery(PDF_DIR / "mtview.pdf", "Mountain View Cemetery")
    second = parse_cemetery(PDF_DIR / "mtview.pdf", "Mountain View Cemetery")
    _dedupe_import_keys(first)
    _dedupe_import_keys(second)
    assert [r.import_key for r in first] == [r.import_key for r in second]
    assert any(r.import_key.endswith("-1") for r in first), \
        "expected mtview to contain at least one real duplicate group"
