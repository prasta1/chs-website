import pytest
from conftest import PDF_DIR
from scripts.db import connect, init_schema
from scripts.import_pdfs import import_all, upsert
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
