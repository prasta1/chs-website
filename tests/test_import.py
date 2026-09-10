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
    # A fresh in-memory db has no prior rows, so every row this run produces
    # must land as an insert -- nothing to update, nothing edited to skip.
    assert all(updated == 0 and skipped == 0 for _, updated, skipped in counts.values())
    assert sum(inserted for inserted, _, _ in counts.values()) > 7000


def test_import_all_reports_updates_and_skips_on_a_second_run(monkeypatch):
    """The number that operationally matters -- how many volunteer
    corrections survived a re-import -- can't be told apart from a plain
    row-count total, so import_all must surface upsert's own
    (inserted, updated, skipped) breakdown per source, not just len(rows).
    Reached entirely through import_all + a real hand edit made via SQL
    (the only correction path this phase has, same pattern as
    test_hand_edited_rows_are_never_overwritten above), never by
    hand-seeding the appearance table's own columns.

    Scoped to riverroad.pdf (20 rows) via monkeypatching import_pdfs.SOURCES
    -- the real import_all/upsert/parser/db path runs unmodified, just over
    one small source instead of the full 16-source corpus, so this doesn't
    pay for two full imports.
    """
    import scripts.import_pdfs as import_pdfs
    from scripts.db import connect as c2
    from scripts.parsers.cemetery import parse_cemetery

    monkeypatch.setattr(import_pdfs, "SOURCES", {
        "riverroad": ("River Road Cemetery", "cemetery",
                     lambda p: parse_cemetery(p, "River Road Cemetery")),
    })

    conn = c2(":memory:")
    init_schema(conn)
    import_all(conn, PDF_DIR)  # first run: everything inserted

    conn.execute("UPDATE appearance SET edited_at='2026-01-01', edited_by='jen'"
                 " WHERE id=(SELECT id FROM appearance LIMIT 1)")
    conn.commit()

    counts = import_all(conn, PDF_DIR)  # second run: re-import, unchanged PDF
    inserted, updated, skipped = counts["riverroad"]
    assert inserted == 0, "no source rows changed between the two runs"
    assert updated == 19, "every unedited row should be re-matched as an update"
    assert skipped == 1, "the one hand-edited row must be preserved, not overwritten"


def test_reimport_refreshes_stale_source_title_kind_and_pages(tmp_path, monkeypatch):
    """title, kind, and pages must be refreshed on every re-import, not
    frozen at whatever they were the first time a filename was seen -- the
    ON CONFLICT clause in import_all previously refreshed only
    sha256/imported_at, so a re-vendored PDF with a different page count, or
    a renamed CEMETERIES title, kept the stale value in `source` forever.
    Phase 2 will query these columns.

    Driven entirely through import_all's real INSERT ... ON CONFLICT path,
    twice, over a tmp pdf_dir: the first run copies in riverroad.pdf (1
    page) under its real title/kind; the second run swaps in smilie.pdf (4
    pages, a genuinely different real PDF) under the SAME stem/filename,
    with a renamed title and different kind in SOURCES too -- the two
    scenarios CodeRabbit named (different page count, renamed cemetery).
    Never a hand-written row.
    """
    import shutil
    import scripts.extract as extract
    import scripts.import_pdfs as import_pdfs
    from scripts.db import connect as c2
    from scripts.parsers.cemetery import parse_cemetery

    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    shutil.copyfile(PDF_DIR / "riverroad.pdf", pdf_dir / "riverroad.pdf")
    monkeypatch.setattr(import_pdfs, "SOURCES", {
        "riverroad": ("River Road Cemetery", "cemetery",
                     lambda p: parse_cemetery(p, "River Road Cemetery")),
    })
    conn = c2(":memory:")
    init_schema(conn)
    import_all(conn, pdf_dir)  # first run: real title/kind/pages for riverroad.pdf
    before = conn.execute(
        "SELECT title, kind, pages FROM source WHERE filename='riverroad.pdf'"
    ).fetchone()

    shutil.copyfile(PDF_DIR / "smilie.pdf", pdf_dir / "riverroad.pdf")
    # extract.py's page_count/extract_words are lru_cache'd by path. In real
    # use each import is its own `python -m scripts.import_pdfs` process, so
    # the cache never survives a re-vendored PDF; here, same process, same
    # path, so it must be cleared to see the swapped file for real instead
    # of asserting a page count we typed in.
    extract.page_count.cache_clear()
    extract.extract_words.cache_clear()
    monkeypatch.setattr(import_pdfs, "SOURCES", {
        "riverroad": ("River Road Cemetery (renamed)", "town",
                     lambda p: parse_cemetery(p, "River Road Cemetery (renamed)")),
    })
    import_all(conn, pdf_dir)  # second run: same filename, new metadata + real PDF swap
    after = conn.execute(
        "SELECT title, kind, pages FROM source WHERE filename='riverroad.pdf'"
    ).fetchone()

    assert (before["title"], before["kind"], before["pages"]) == (
        "River Road Cemetery", "cemetery", 1)
    assert (after["title"], after["kind"], after["pages"]) == (
        "River Road Cemetery (renamed)", "town", 4)


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


def test_dedupe_disambiguates_pair_key_for_a_duplicated_marriage_line():
    """A duplicated marriage line makes four rows: sha:groom, sha:bride (line
    1), sha:groom, sha:bride (line 2, a byte-identical repeat). Suffixing
    only import_key leaves all four sharing pair_key='sha' -- 'who did this
    person marry' via idx_appearance_pair would then return two couples as
    one. pair_key must gain the same -N suffix as its row's import_key, and
    groom/bride of the SAME occurrence must still share one pair_key."""

    def row(role):
        return Appearance(surname="X", given="Y", surname_key="X", kind="marriage",
                          role=role, page=1, raw_line="raw", pair_key="sha",
                          import_key=f"sha:{role}")

    rows = [row("groom"), row("bride"), row("groom"), row("bride")]
    _dedupe_import_keys(rows)
    assert [r.import_key for r in rows] == [
        "sha:groom", "sha:bride", "sha:groom-1", "sha:bride-1"]
    assert [r.pair_key for r in rows] == ["sha", "sha", "sha-1", "sha-1"]
    assert rows[0].pair_key == rows[1].pair_key       # line 1's couple
    assert rows[2].pair_key == rows[3].pair_key       # line 2's couple
    assert rows[0].pair_key != rows[2].pair_key       # the two lines differ


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
