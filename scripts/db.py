"""SQLite connection and schema setup."""
import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).parent / "schema.sql"


def connect(path: Path) -> sqlite3.Connection:
    """Open a connection with foreign keys on and dict-like rows.

    SQLite leaves foreign key enforcement off by default, so it must be enabled
    per connection or the source_id reference is decorative.
    """
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create tables and indexes if they do not already exist."""
    conn.executescript(SCHEMA.read_text())
    conn.commit()
