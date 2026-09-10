import sqlite3
import pytest
from scripts.db import connect, init_schema


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "t.sqlite")
    init_schema(c)
    return c


def test_tables_exist(conn):
    names = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"source", "appearance", "newsletter", "newsletter_page"} <= names


def test_import_key_is_unique(conn):
    conn.execute("INSERT INTO source (filename,title,kind,pages,sha256,imported_at)"
                 " VALUES ('a.pdf','A','cemetery',1,'x','now')")
    conn.execute(
        "INSERT INTO appearance (source_id,page,import_key,surname,surname_key,kind)"
        " VALUES (1,1,'dupe','Atwood','ATT','burial')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO appearance (source_id,page,import_key,surname,surname_key,kind)"
            " VALUES (1,1,'dupe','Atwood','ATT','burial')")


def test_appearance_requires_a_real_source(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO appearance (source_id,page,surname,surname_key,kind)"
            " VALUES (999,1,'Atwood','ATT','burial')")
        conn.commit()


def test_defaults_are_active_and_imported(conn):
    conn.execute("INSERT INTO source (filename,title,kind,pages,sha256,imported_at)"
                 " VALUES ('a.pdf','A','cemetery',1,'x','now')")
    conn.execute("INSERT INTO appearance (source_id,page,surname,surname_key,kind)"
                 " VALUES (1,1,'Atwood','ATT','burial')")
    row = conn.execute("SELECT origin, status, verified FROM appearance").fetchone()
    assert (row["origin"], row["status"], row["verified"]) == ("imported", "active", 0)
