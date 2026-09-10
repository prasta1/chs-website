"""Integrity gates and the human-review report.

A parser regression that silently drops several hundred people is the failure
this exists to catch, so count drift fails the build rather than shipping.
"""
import re
import sqlite3
from pathlib import Path

from scripts.import_pdfs import SOURCES
from scripts.layout import iter_table_pages
from scripts.parsers import bounds_for

TOLERANCE = 0.02  # 2% drift allowed before a source is considered broken

# A lowercase letter directly followed by an uppercase one, with no space
# between -- the signature pdftotext leaves when it glues two source words
# together (e.g. "AlexanderWilley"). Real hyphenated/prefixed surnames
# (McNally, MacArthur, O'Brien...) also match this; that's fine, this list is
# for a human to skim and dismiss, not an auto-fail.
MERGE_PATTERN = re.compile(r"[a-z][A-Z]")

# import_key shape: <sha1>[:role][-N]. Role fan-out (":father"/":mother"/
# ":groom"/":bride") comes first; duplicate-line disambiguation ("-1"/"-2")
# is appended *after* that by _dedupe_import_keys, not before it.
_KEY_ROOT = re.compile(r"^(?P<sha>[0-9a-f]{40})(?::[a-z]+)?(?P<dup>-\d+)?$")


def _source_row_key(import_key: str) -> str:
    """Collapse a role fan-out key back to the source row it came from.

    Keys are <sha1>[:role][-N]: role fan-out appends :father/:mother/:groom/
    :bride, and duplicate-line disambiguation appends -N *after* that. Both
    parts must be handled together -- stripping at the first ':' would discard
    the -N as well and merge two genuinely distinct duplicate rows into one
    (e.g. <sha1>:groom and <sha1>:groom-1, two different marriage lines that
    happen to hash the same, would both read back as <sha1>).
    """
    m = _KEY_ROOT.match(import_key)
    if not m:
        return import_key
    return m["sha"] + (m["dup"] or "")


def check_counts(conn: sqlite3.Connection, baseline: dict[str, int]) -> list[str]:
    """Compare per-source active *imported* row counts against the baseline.

    Scoped to origin='imported' -- the baseline measures what the PDF parse
    produced. A volunteer can add a person who appears in no PDF
    (origin='manual', import_key NULL; see upsert()'s NULL-key filter), and
    that must never count as drift against an extraction baseline that knows
    nothing about it.

    Also flags a source present in the database but absent from the
    baseline entirely -- a new SOURCES entry whose baseline was never
    regenerated would otherwise go completely ungated.
    """
    problems = []
    for filename, expected in baseline.items():
        row = conn.execute(
            "SELECT COUNT(*) c FROM appearance a JOIN source s ON s.id=a.source_id"
            " WHERE s.filename=? AND a.status='active' AND a.origin='imported'",
            (filename,)).fetchone()
        got = row["c"]
        if expected == 0:
            if got:
                problems.append(f"{filename}: expected 0, got {got}")
            continue
        if abs(got - expected) / expected > TOLERANCE:
            problems.append(f"{filename}: expected ~{expected}, got {got}")

    db_files = {r["filename"] for r in conn.execute("SELECT DISTINCT filename FROM source")}
    for filename in sorted(db_files - set(baseline)):
        problems.append(f"{filename}: source in the database has no baseline entry")
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


def reconcile(conn: sqlite3.Connection, pdf_dir: Path) -> dict[str, dict]:
    """Per-source rows_in / rows_out / delta -- nothing is dropped invisibly.

    rows_in is the number of source table rows the parser's own page range
    actually covers. rows_out is the number of distinct source rows
    represented in the database, recovered from import_key via
    _source_row_key: every key begins with the sha1 of (filename, page,
    raw_line), with role fan-out (":father"/":mother"/":groom"/":bride") and
    duplicate-line disambiguation ("-1"/"-2") appended after it -- collapsing
    a row's fan-out back to one id has to keep the -N suffix, or two
    genuinely distinct duplicate rows collapse into one.

    The gap is rows that produced no appearance at all -- not an error, not a
    warning, just absent. E.g. marriage_records2 p.15 prints "John
    AlexanderWilley Mary WellingtonStearns": two words merged with no gap on
    each side, so both surname columns come out empty and the whole row -- two
    real people -- is skipped by parse_marriage with no trace. A non-zero
    delta here is how that becomes visible instead of silent.

    Never fails the build: some rows legitimately carry no surname (a blank
    ledger line). The number must be seen, not gated -- a review_report flag
    or a reconcile spike is what tells a human to go look.

    delta is blind to a *half*-dropped row: marriage_records2 p.14 prints
    "Bk. B p. 234 6 Jan 1836 John FrederickWait Evelina Hawley he of Barre".
    pdftotext merges Frederick+Wait, so Groom Last comes out empty and
    parse_marriage drops the groom -- but the bride still emits, so the
    source row still yields one root and delta reads 0. half_pairs catches
    this: a marriage pair_key with only one active member (should be
    groom+bride, two) means a party was lost. Restricted to kind='marriage'
    -- birth's father/mother are legitimately optional, so a lone child row
    is normal there, not a drop.
    """
    out = {}
    for stem in SOURCES:
        path = pdf_dir / f"{stem}.pdf"
        src = conn.execute("SELECT id FROM source WHERE filename=?",
                            (path.name,)).fetchone()
        if src is None:
            continue
        rows_in = sum(len(rows) for _, _, rows in
                       iter_table_pages(path, **bounds_for(stem, path)))
        keys = conn.execute(
            "SELECT import_key FROM appearance WHERE source_id=? AND"
            " status='active' AND import_key IS NOT NULL", (src["id"],)).fetchall()
        rows_out = len({_source_row_key(k["import_key"]) for k in keys})
        half_pairs = conn.execute(
            "SELECT COUNT(*) c FROM (SELECT pair_key FROM appearance WHERE"
            " source_id=? AND status='active' AND kind='marriage' AND"
            " pair_key IS NOT NULL GROUP BY pair_key HAVING COUNT(*)=1)",
            (src["id"],)).fetchone()["c"]
        out[path.name] = {"rows_in": rows_in, "rows_out": rows_out,
                          "delta": rows_in - rows_out, "half_pairs": half_pairs}
    return out


def review_report(conn: sqlite3.Connection) -> list[dict]:
    """Rows a human should look at. Never auto-corrected.

    Flags names that look reversed -- Cloverdale's first row parses as
    surname 'Alida', given name 'Seeley'. The signal is corpus-derived, never
    a hardcoded name list: count how often each token appears as a *surname*
    across the whole corpus, then flag a row whose surname is vanishingly
    rare (<=1, i.e. only this row) while its given name's first token is
    common as a surname elsewhere (>=5) -- exactly the shape of two fields
    swapped in transcription. Guessing which way round they go would launder
    a real transcription error into the archive as verified fact, so this
    only flags for a human, never corrects.

    Also flags a raw_line carrying a merged-word artifact -- a token with a
    lowercase letter immediately followed by an uppercase one, e.g.
    "AlexanderWilley". There's no principled way to know where the word
    boundary falls, so this is surfaced for a human to fix by consulting the
    original document, never split automatically.

    Also flags a hand correction whose source line has changed or vanished:
    an active row with `edited_at` set but whose `import_key` went unseen in
    the most recent import (see `key_seen` and scripts/import_pdfs.upsert).
    Such a row is never retired -- the human correction stays authoritative
    -- but it needs a human to reconcile it against the PDF's current text.

    Also flags a marriage whose pair_key has only one active member (see
    reconcile's half_pairs) -- the other party was lost, most often a
    merged-word artifact that emptied their name column. Surfaced for a
    human to consult the original page, never guessed at.
    """
    flags = []
    rows = conn.execute(
        "SELECT a.id, a.surname, a.given, a.date_raw, a.date_iso, a.page,"
        " a.raw_line, a.edited_at, a.key_seen, a.kind, a.pair_key, s.filename"
        " FROM appearance a JOIN source s ON s.id=a.source_id"
        " WHERE a.status='active'").fetchall()

    # Frequency of each token as a surname across the corpus, computed once.
    sur: dict[str, int] = {}
    for r in rows:
        if r["surname"]:
            sur[r["surname"]] = sur.get(r["surname"], 0) + 1

    # Marriage pair_key group sizes, computed once -- a group of 1 means the
    # other party (groom or bride) was dropped by the parser.
    marriage_pairs: dict[str, int] = {}
    for r in rows:
        if r["kind"] == "marriage" and r["pair_key"]:
            marriage_pairs[r["pair_key"]] = marriage_pairs.get(r["pair_key"], 0) + 1

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
        given_tokens = (r["given"] or "").split()
        if (given_tokens and sur.get(r["surname"], 0) <= 1
                and sur.get(given_tokens[0], 0) >= 5):
            reasons.append("name may be reversed")
        if r["raw_line"] and any(MERGE_PATTERN.search(tok)
                                 for tok in r["raw_line"].split()):
            reasons.append("possible merged words in raw_line")
        if r["edited_at"] and not r["key_seen"]:
            reasons.append("hand correction's source line has changed or vanished")
        if (r["kind"] == "marriage" and r["pair_key"]
                and marriage_pairs.get(r["pair_key"], 0) == 1):
            reasons.append("other marriage party missing (possible merged/dropped name)")
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
    total_in = total_out = total_half = 0
    for filename in sorted(recon):
        r = recon[filename]
        total_in += r["rows_in"]
        total_out += r["rows_out"]
        total_half += r["half_pairs"]
        marker = "  <-- check" if r["delta"] or r["half_pairs"] else ""
        print(f"  {filename:<28} in={r['rows_in']:<6} out={r['rows_out']:<6}"
              f" delta={r['delta']:<4} half_pairs={r['half_pairs']}{marker}")
    print(f"  {'TOTAL':<28} in={total_in:<6} out={total_out:<6}"
          f" delta={total_in - total_out:<4} half_pairs={total_half}")

    print(f"\n{len(report)} rows flagged for review")
    for f in report[:40]:
        print(f"  {f['file']} p{f['page']}: {f['name']} — {', '.join(f['reasons'])}")
    raise SystemExit(1 if problems else 0)
