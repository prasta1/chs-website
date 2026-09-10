"""Load record PDFs into SQLite, preserving hand corrections.

The PDFs are one input and the volunteers are another. Re-running import must
never destroy a correction, so rows carrying edited_at are left untouched,
and unedited rows that vanish from a source are retired rather than deleted.
A hand-edited row is never retired even if its import_key vanishes (the
source line changed or disappeared) -- it stays active and authoritative,
flagged instead via key_seen for a human to reconcile (see upsert()).
"""
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from scripts.db import connect, init_schema
from scripts.extract import page_count
from scripts.parsers import Appearance
from scripts.parsers.cemetery import parse_cemetery
from scripts.parsers.simple import parse_death, parse_freeman, parse_warning
from scripts.parsers.vital import parse_birth, parse_marriage

CEMETERIES = {
    "cloverdale": "Cloverdale Cemetery", "eastcambridge": "East Cambridge Cemetery",
    "gates": "Gates Cemetery", "hopkins": "Hopkins Cemetery",
    "jeffersonville": "Jeffersonville Cemetery", "mtview": "Mountain View Cemetery",
    "northcambridge": "North Cambridge Cemetery", "plainsroad": "Plains Road Cemetery",
    "riverroad": "River Road Cemetery", "smilie": "Smilie Cemetery",
    "southcambridge": "South Cambridge Cemetery",
}

SOURCES: dict[str, tuple[str, str, object]] = {
    **{stem: (title, "cemetery",
              lambda p, t=title: parse_cemetery(p, t))
       for stem, title in CEMETERIES.items()},
    "birth_records": ("Birth records", "vital", parse_birth),
    "marriage_records2": ("Marriage records", "vital", parse_marriage),
    "death_records": ("Death records", "vital", parse_death),
    "warningsout_records": ("Warnings out", "town", parse_warning),
    "freemansworn_records": ("Freeman's oaths", "town", parse_freeman),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def upsert(conn: sqlite3.Connection, source_id: int,
           rows: list[Appearance]) -> tuple[int, int, int]:
    """Write rows for one source. Returns (inserted, updated, skipped_edited).

    Rows already in the database for this source but absent from `rows` are
    marked retired -- *unless* they carry a hand correction (`edited_at`
    set). A human corrected that row, so it stays authoritative: it is left
    `active` and its `key_seen` flag is cleared to 0 instead, so
    review_report can surface it as a hand correction whose source line has
    changed or vanished, for a human to reconcile. Nothing edited is ever
    deleted or silently dropped from view.
    """
    existing = {
        r["import_key"]: r for r in conn.execute(
            "SELECT import_key, edited_at, key_seen FROM appearance WHERE source_id = ?",
            (source_id,))
        if r["import_key"] is not None
    }
    seen, inserted, updated, skipped = set(), 0, 0, 0

    for a in rows:
        seen.add(a.import_key)
        prior = existing.get(a.import_key)
        if prior is not None and prior["edited_at"]:
            skipped += 1
            if not prior["key_seen"]:
                # The key had previously gone missing and reappeared
                # byte-identical -- clear the stale flag and, if a retired
                # row's key came back, restore it to active too.
                conn.execute(
                    "UPDATE appearance SET key_seen=1, status='active'"
                    " WHERE import_key=?", (a.import_key,))
            continue
        # Named placeholders so one dict drives both statements — the INSERT and
        # UPDATE differ only in whether source_id is set.
        fields = {
            "source_id": source_id, "page": a.page, "import_key": a.import_key,
            "raw_line": a.raw_line, "surname": a.surname, "given": a.given,
            "surname_key": a.surname_key, "kind": a.kind, "role": a.role,
            "pair_key": a.pair_key, "date_raw": a.date_raw,
            "date_iso": a.date_iso, "place": a.place, "volume": a.volume,
            "detail": a.detail,
        }
        if prior is None:
            conn.execute(
                "INSERT INTO appearance (source_id,page,import_key,raw_line,surname,"
                "given,surname_key,kind,role,pair_key,date_raw,date_iso,place,volume,"
                "detail) VALUES (:source_id,:page,:import_key,:raw_line,:surname,"
                ":given,:surname_key,:kind,:role,:pair_key,:date_raw,:date_iso,:place,"
                ":volume,:detail)", fields)
            inserted += 1
        else:
            conn.execute(
                "UPDATE appearance SET page=:page, raw_line=:raw_line,"
                " surname=:surname, given=:given, surname_key=:surname_key,"
                " kind=:kind, role=:role, pair_key=:pair_key, date_raw=:date_raw,"
                " date_iso=:date_iso, place=:place, volume=:volume, detail=:detail,"
                " status='active', key_seen=1 WHERE import_key=:import_key", fields)
            updated += 1

    stale = [k for k in existing if k not in seen]
    for key in stale:
        if existing[key]["edited_at"]:
            conn.execute("UPDATE appearance SET key_seen=0 WHERE import_key=?",
                         (key,))
        else:
            conn.execute("UPDATE appearance SET status='retired' WHERE import_key=?",
                         (key,))
    conn.commit()
    return inserted, updated, skipped


def _dedupe_import_keys(rows: list[Appearance]) -> None:
    """Suffix repeated import_keys within one parse so none collide.

    import_key hashes (filename, page, raw_line). A few source pages contain
    byte-identical lines twice — a duplicated ledger entry, a stray reprinted
    table header — so two distinct Appearances can hash the same. Suffixing
    every repeat after the first keeps every row (nothing dropped, no
    IntegrityError) without touching the base key that a plain, non-repeated
    row already has in the database. Parse order is stable across runs, so
    the same row gets the same suffix every time re-import happens.
    """
    seen: dict[str, int] = {}
    for a in rows:
        n = seen.get(a.import_key, 0)
        seen[a.import_key] = n + 1
        if n:
            a.import_key = f"{a.import_key}-{n}"


def import_all(conn: sqlite3.Connection, pdf_dir: Path) -> dict[str, int]:
    """Import every in-scope source. Returns stem -> appearance count."""
    counts: dict[str, int] = {}
    for stem, (title, kind, parser) in SOURCES.items():
        path = pdf_dir / f"{stem}.pdf"
        conn.execute(
            "INSERT INTO source (filename,title,kind,pages,sha256,imported_at)"
            " VALUES (?,?,?,?,?,?) ON CONFLICT(filename) DO UPDATE SET"
            " sha256=excluded.sha256, imported_at=excluded.imported_at",
            (path.name, title, kind, page_count(path), _sha256(path),
             datetime.now(timezone.utc).isoformat()))
        source_id = conn.execute(
            "SELECT id FROM source WHERE filename=?", (path.name,)).fetchone()["id"]
        rows = parser(path)
        _dedupe_import_keys(rows)
        upsert(conn, source_id, rows)
        counts[stem] = len(rows)
    return counts


if __name__ == "__main__":
    db = Path("data/archive.sqlite")
    db.parent.mkdir(exist_ok=True)
    conn = connect(db)
    init_schema(conn)
    for stem, n in import_all(conn, Path("pdfs")).items():
        print(f"{stem:<24} {n}")
