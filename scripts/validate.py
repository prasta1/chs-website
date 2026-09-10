"""Integrity gates and the human-review report.

A parser regression that silently drops several hundred people is the failure
this exists to catch, so count drift fails the build rather than shipping.
"""
import re
import sqlite3
from pathlib import Path

from scripts.import_pdfs import SOURCES
from scripts.layout import iter_table_pages
from scripts.parsers.simple import DEATH_SECOND_PASS_HEADING, _pass1_last_page
from scripts.parsers.vital import _second_pass_start

TOLERANCE = 0.02  # 2% drift allowed before a source is considered broken

# A lowercase letter directly followed by an uppercase one, with no space
# between -- the signature pdftotext leaves when it glues two source words
# together (e.g. "AlexanderWilley"). Real hyphenated/prefixed surnames
# (McNally, MacArthur, O'Brien...) also match this; that's fine, this list is
# for a human to skim and dismiss, not an auto-fail.
MERGE_PATTERN = re.compile(r"[a-z][A-Z]")


def check_counts(conn: sqlite3.Connection, baseline: dict[str, int]) -> list[str]:
    """Compare per-source active row counts against the committed baseline."""
    problems = []
    for filename, expected in baseline.items():
        row = conn.execute(
            "SELECT COUNT(*) c FROM appearance a JOIN source s ON s.id=a.source_id"
            " WHERE s.filename=? AND a.status='active'", (filename,)).fetchone()
        got = row["c"]
        if expected == 0:
            continue
        if abs(got - expected) / expected > TOLERANCE:
            problems.append(f"{filename}: expected ~{expected}, got {got}")
    return problems


def check_integrity(conn: sqlite3.Connection) -> list[str]:
    """Every appearance must have a real source and a positive page number."""
    problems = []
    orphans = conn.execute(
        "SELECT COUNT(*) c FROM appearance a LEFT JOIN source s ON s.id=a.source_id"
        " WHERE s.id IS NULL").fetchone()["c"]
    if orphans:
        problems.append(f"{orphans} appearances have no source")

    bad_page = conn.execute(
        "SELECT COUNT(*) c FROM appearance WHERE page IS NULL OR page < 1"
    ).fetchone()["c"]
    if bad_page:
        problems.append(f"{bad_page} appearances have no usable page number")

    no_name = conn.execute(
        "SELECT COUNT(*) c FROM appearance WHERE surname IS NULL OR surname=''"
    ).fetchone()["c"]
    if no_name:
        problems.append(f"{no_name} appearances have no surname")
    return problems


def _parser_bounds(stem: str, pdf_path: Path) -> dict:
    """The page range / header hint the real parser for `stem` uses.

    Reuses each parser's own pass-boundary detector (rather than re-deriving
    it) so rows_in below counts exactly the rows the parser looked at -- not
    the whole file, which for a bounded wide-table PDF like birth/death would
    double-count the second pass and make the reconciliation meaningless.
    """
    if stem == "birth_records":
        start = _second_pass_start(pdf_path)
        return {"last_page": (start - 1) if start else None}
    if stem == "death_records":
        return {"last_page": _pass1_last_page(pdf_path, DEATH_SECOND_PASS_HEADING)}
    if stem == "freemansworn_records":
        return {"header_contains": "Volume"}
    return {}


def reconcile(conn: sqlite3.Connection, pdf_dir: Path) -> dict[str, dict]:
    """Per-source rows_in / rows_out / delta -- nothing is dropped invisibly.

    rows_in is the number of source table rows the parser's own page range
    actually covers. rows_out is the number of distinct source rows
    represented in the database, recovered from import_key: every key begins
    with the sha1 of (filename, page, raw_line), with role fan-out
    (":father"/":mother"/":groom"/":bride") and duplicate-line disambiguation
    ("-1"/"-2") appended after it, so splitting on the first ":" collapses a
    row's fan-out back to one id.

    The gap is rows that produced no appearance at all -- not an error, not a
    warning, just absent. E.g. marriage_records2 p.15 prints "John
    AlexanderWilley Mary WellingtonStearns": two words merged with no gap on
    each side, so both surname columns come out empty and the whole row -- two
    real people -- is skipped by parse_marriage with no trace. A non-zero
    delta here is how that becomes visible instead of silent.

    Never fails the build: some rows legitimately carry no surname (a blank
    ledger line). The number must be seen, not gated -- a review_report flag
    or a reconcile spike is what tells a human to go look.
    """
    out = {}
    for stem in SOURCES:
        path = pdf_dir / f"{stem}.pdf"
        src = conn.execute("SELECT id FROM source WHERE filename=?",
                            (path.name,)).fetchone()
        if src is None:
            continue
        rows_in = sum(len(rows) for _, _, rows in
                       iter_table_pages(path, **_parser_bounds(stem, path)))
        keys = conn.execute(
            "SELECT import_key FROM appearance WHERE source_id=? AND"
            " status='active' AND import_key IS NOT NULL", (src["id"],)).fetchall()
        rows_out = len({k["import_key"].split(":", 1)[0] for k in keys})
        out[path.name] = {"rows_in": rows_in, "rows_out": rows_out,
                          "delta": rows_in - rows_out}
    return out


def review_report(conn: sqlite3.Connection) -> list[dict]:
    """Rows a human should look at. Never auto-corrected.

    Flags names that look reversed or malformed -- Cloverdale's first row
    parses as surname 'Alida', given name 'Seeley', likely reversed in the
    original transcription rather than misparsed. Guessing here would launder
    a real transcription error into the archive as verified fact.

    Also flags a raw_line carrying a merged-word artifact -- a token with a
    lowercase letter immediately followed by an uppercase one, e.g.
    "AlexanderWilley". There's no principled way to know where the word
    boundary falls, so this is surfaced for a human to fix by consulting the
    original document, never split automatically.
    """
    flags = []
    rows = conn.execute(
        "SELECT a.id, a.surname, a.given, a.date_raw, a.date_iso, a.page,"
        " a.raw_line, s.filename FROM appearance a JOIN source s ON"
        " s.id=a.source_id WHERE a.status='active'").fetchall()
    for r in rows:
        reasons = []
        if r["date_raw"] and not r["date_iso"]:
            reasons.append("date not parseable")
        if r["surname"] and len(r["surname"]) < 2:
            reasons.append("surname suspiciously short")
        if not r["given"]:
            reasons.append("no given name")
        if r["surname"] and not r["surname"][0].isupper():
            reasons.append("surname not capitalised")
        if r["raw_line"] and any(MERGE_PATTERN.search(tok)
                                 for tok in r["raw_line"].split()):
            reasons.append("possible merged words in raw_line")
        if reasons:
            flags.append({"id": r["id"], "file": r["filename"], "page": r["page"],
                          "name": f"{r['surname']}, {r['given']}",
                          "reasons": reasons})
    return flags


if __name__ == "__main__":
    import json
    from scripts.db import connect

    conn = connect(Path("data/archive.sqlite"))
    baseline = json.loads(Path("data/baseline.json").read_text())
    problems = check_counts(conn, baseline) + check_integrity(conn)
    report = review_report(conn)
    recon = reconcile(conn, Path("pdfs"))

    for p in problems:
        print(f"FAIL {p}")

    print("\nreconciliation (source rows in vs. rows represented in the db):")
    total_in = total_out = 0
    for filename in sorted(recon):
        r = recon[filename]
        total_in += r["rows_in"]
        total_out += r["rows_out"]
        marker = "  <-- check" if r["delta"] else ""
        print(f"  {filename:<28} in={r['rows_in']:<6} out={r['rows_out']:<6}"
              f" delta={r['delta']}{marker}")
    print(f"  {'TOTAL':<28} in={total_in:<6} out={total_out:<6}"
          f" delta={total_in - total_out}")

    print(f"\n{len(report)} rows flagged for review")
    for f in report[:40]:
        print(f"  {f['file']} p{f['page']}: {f['name']} — {', '.join(f['reasons'])}")
    raise SystemExit(1 if problems else 0)
