# CHS Archive Extraction (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn 16 tabular record PDFs into a validated local SQLite database of ~7,350 person-appearances, with golden tests and validation gates proving the parse is trustworthy.

**Architecture:** `pdftotext -bbox-layout` yields word-level x/y coordinates. Words are grouped into rows by y-position and assigned to columns by x-overlap against a header row. Per-record-type parsers map columns to `appearance` rows and write them to SQLite. No network, no Cloudflare, no web UI in this phase.

**Tech Stack:** Python 3.14, stdlib `sqlite3` and `xml.etree`, poppler `pdftotext` 26.08, `metaphone` for Double Metaphone, `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-09-chs-archive-search-design.md`

## Global Constraints

- Extraction MUST use `pdftotext -bbox-layout`. Plain `-layout` merges header tokens (`Maiden Name Born` reads as one field) and cannot distinguish left-aligned name columns from the right-aligned `Age` column. Non-layout mode returns text column-major and scrambles rows entirely.
- Nothing is ever deleted. Rows absent from a re-import get `status = 'retired'`.
- Rows with `edited_at` set are never overwritten by import.
- Every `appearance` row MUST carry a valid `source_id` and `page`.
- Suspicious rows are reported for human review, never auto-corrected.
- Dates may be partial. Store `date_raw` verbatim always; `date_iso` may be `YYYY`, `YYYY-MM`, or `YYYY-MM-DD`, or NULL.
- All work is local. No Cloudflare resources are created in Phase 1.

## Scope

**In scope — 16 files, 6 parsers:**

| Type | Files | Columns |
|---|---|---|
| cemetery | 11 (cloverdale, eastcambridge, gates, hopkins, jeffersonville, mtview, northcambridge, plainsroad, riverroad, smilie, southcambridge) | Last Name, First Name, Maiden Name, Born, Died, Age, Spouse, Mother, Father, Notes |
| birth | birth_records | Volume, Birth Day, Child, Family Name, Father |
| marriage | marriage_records2 | Volume, Marriage Date, Groom First, Groom Last, Bride First, Bride Last, Notes |
| death | death_records | Volume/Page, First Name, Last Name, Date, Age |
| warning | warningsout_records | Volume, Date of Warning, Last Name, First Name |
| freeman | freemansworn_records | Volume, Date of Oath, First Name, Last Name |

**Explicitly deferred** — these are not row-per-person tables and need separate handling: `taxpayers_1874` (four side-by-side name column-pairs), `townmeetings_name_references` (page/date matrix), `cattle_earmarks` (pictorial marks, not text), `crows_and_foxes`, `land_records_vol_1_name_index` (free-form index), `1790_census` (statistical table with nested numeric headers). Together these are under 5% of the corpus text.

## File Structure

```
pdfs/                          52 source PDFs (committed)
scripts/
├── __init__.py
├── extract.py                 bbox XML → Word objects
├── layout.py                  rows and columns from Words
├── normalize.py               dates, metaphone, import_key
├── db.py                      connection + schema init
├── schema.sql                 DDL
├── parsers/
│   ├── __init__.py            SOURCES registry
│   ├── cemetery.py
│   ├── vital.py               birth + marriage (both fan out)
│   └── simple.py              death, warning, freeman
├── import_pdfs.py             orchestrator + edit preservation
└── validate.py                gates + review report
tests/
├── conftest.py
├── test_extract.py
├── test_layout.py
├── test_normalize.py
├── test_db.py
├── test_parsers.py
├── test_import.py
└── test_golden.py
data/
├── baseline.json              per-source expected row counts
└── archive.sqlite             generated, committed at end of phase
```

---

### Task 1: Scaffolding and corpus

**Files:**
- Create: `requirements.txt`, `pyproject.toml`, `scripts/__init__.py`, `tests/conftest.py`
- Create: `pdfs/` (copy 52 PDFs)
- Modify: `.gitignore`
- Test: `tests/test_corpus.py`

**Interfaces:**
- Consumes: nothing
- Produces: `PDF_DIR` (pathlib.Path) and `RECORD_PDFS` (dict[str, str] mapping stem → type) from `tests/conftest.py`; `pdfs/<name>.pdf` on disk

- [ ] **Step 1: Copy the PDFs into the repo**

```bash
mkdir -p pdfs
cp cambridgehistoricalsociety.org/uploads/3/4/3/4/34345214/*.pdf pdfs/
ls pdfs/*.pdf | wc -l   # expect 47
```

- [ ] **Step 2: Create the Python project files**

`requirements.txt`:
```
pytest==8.3.4
metaphone==0.6
```

`pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

`scripts/__init__.py`: (empty file)

- [ ] **Step 3: Update .gitignore**

Add these lines to `.gitignore`:
```
.venv/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 4: Create the venv and install**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Note: use `.venv/bin/python -m pip`, never `.venv/bin/pip` — script shebangs hold absolute paths and break if the folder moves.

- [ ] **Step 5: Write the failing test**

`tests/conftest.py`:
```python
import pathlib
import pytest

PDF_DIR = pathlib.Path(__file__).parent.parent / "pdfs"

# stem -> record type. Phase 1 scope only.
RECORD_PDFS = {
    "cloverdale": "cemetery", "eastcambridge": "cemetery", "gates": "cemetery",
    "hopkins": "cemetery", "jeffersonville": "cemetery", "mtview": "cemetery",
    "northcambridge": "cemetery", "plainsroad": "cemetery", "riverroad": "cemetery",
    "smilie": "cemetery", "southcambridge": "cemetery",
    "birth_records": "birth",
    "marriage_records2": "marriage",
    "death_records": "death",
    "warningsout_records": "warning",
    "freemansworn_records": "freeman",
}


@pytest.fixture(scope="session")
def pdf_dir():
    return PDF_DIR
```

`tests/test_corpus.py`:
```python
import shutil
from conftest import PDF_DIR, RECORD_PDFS


def test_pdftotext_available():
    assert shutil.which("pdftotext"), "poppler's pdftotext must be on PATH"


def test_all_record_pdfs_present():
    missing = [s for s in RECORD_PDFS if not (PDF_DIR / f"{s}.pdf").exists()]
    assert missing == [], f"missing PDFs: {missing}"


def test_record_pdfs_are_nonempty():
    for stem in RECORD_PDFS:
        assert (PDF_DIR / f"{stem}.pdf").stat().st_size > 1000
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_corpus.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pyproject.toml .gitignore scripts/__init__.py tests/conftest.py tests/test_corpus.py pdfs/
git commit -m "Vendor the archive PDFs and scaffold the extraction project

The index will point at these files page by page, so they belong in the repo
rather than hot-linked to a Weebly site that already 404s five issues."
```

---

### Task 2: Word extraction with coordinates

**Files:**
- Create: `scripts/extract.py`
- Test: `tests/test_extract.py`

**Interfaces:**
- Consumes: `pdfs/*.pdf`
- Produces: `Word` (NamedTuple: `text: str`, `x0: float`, `x1: float`, `y0: float`, `y1: float`) and `extract_words(pdf_path: Path, page: int) -> list[Word]`, and `page_count(pdf_path: Path) -> int`

- [ ] **Step 1: Write the failing test**

`tests/test_extract.py`:
```python
from conftest import PDF_DIR
from scripts.extract import extract_words, page_count


def test_page_count():
    assert page_count(PDF_DIR / "cloverdale.pdf") == 3


def test_extracts_words_with_coordinates():
    words = extract_words(PDF_DIR / "cloverdale.pdf", 1)
    assert len(words) > 100
    first = words[0]
    assert first.text == "Last"
    assert first.x1 > first.x0
    assert first.y1 > first.y0


def test_header_words_present_on_first_page():
    words = extract_words(PDF_DIR / "cloverdale.pdf", 1)
    texts = [w.text for w in words]
    for expected in ["Last", "Name", "First", "Maiden", "Born", "Died", "Age"]:
        assert expected in texts


def test_known_surname_present():
    words = extract_words(PDF_DIR / "cloverdale.pdf", 1)
    assert "Atwood" in [w.text for w in words]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_extract.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.extract'`

- [ ] **Step 3: Write the implementation**

`scripts/extract.py`:
```python
"""Word-level PDF text extraction with coordinates.

Uses `pdftotext -bbox-layout`, which emits XHTML with a bounding box per word.
Coordinates are what make column assignment reliable: the record tables mix
left-aligned name columns with right-aligned age columns, so character-offset
slicing of `-layout` output misparses them.
"""
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple

XHTML = "{http://www.w3.org/1999/xhtml}"


class Word(NamedTuple):
    """A single word and its bounding box in PDF points."""
    text: str
    x0: float
    x1: float
    y0: float
    y1: float


def page_count(pdf_path: Path) -> int:
    """Return the number of pages in the PDF."""
    out = subprocess.run(
        ["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=True
    ).stdout
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    raise ValueError(f"no page count in pdfinfo output for {pdf_path}")


def extract_words(pdf_path: Path, page: int) -> list[Word]:
    """Extract every word on one 1-indexed page, with coordinates.

    Returns words in document order. Raises CalledProcessError if pdftotext fails.
    """
    xml = subprocess.run(
        ["pdftotext", "-q", "-bbox-layout", "-f", str(page), "-l", str(page),
         str(pdf_path), "-"],
        capture_output=True, text=True, check=True,
    ).stdout
    root = ET.fromstring(xml)
    words = []
    for el in root.iter(f"{XHTML}word"):
        text = (el.text or "").strip()
        if not text:
            continue
        words.append(Word(
            text=text,
            x0=float(el.get("xMin")), x1=float(el.get("xMax")),
            y0=float(el.get("yMin")), y1=float(el.get("yMax")),
        ))
    return words
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_extract.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/extract.py tests/test_extract.py
git commit -m "Extract PDF words with coordinates rather than character offsets

The record tables mix left-aligned names with right-aligned ages, and header
tokens like 'Maiden Name Born' collapse under -layout. Coordinates avoid both."
```

---

### Task 3: Rows and columns from coordinates

**Files:**
- Create: `scripts/layout.py`
- Test: `tests/test_layout.py`

**Interfaces:**
- Consumes: `Word` from `scripts.extract`
- Produces: `group_rows(words: list[Word], tol: float = 3.0) -> list[list[Word]]`, `Column` (NamedTuple: `name: str`, `x0: float`, `x1: float`), `detect_columns(header: list[Word], gap: float = 8.0) -> list[Column]`, `assign_columns(row: list[Word], cols: list[Column]) -> dict[str, str]`

- [ ] **Step 1: Write the failing test**

`tests/test_layout.py`:
```python
from conftest import PDF_DIR
from scripts.extract import extract_words
from scripts.layout import group_rows, detect_columns, assign_columns


def rows_for(stem, page=1):
    return group_rows(extract_words(PDF_DIR / f"{stem}.pdf", page))


def test_groups_words_into_rows():
    rows = rows_for("cloverdale")
    assert [w.text for w in rows[0]] == ["Last", "Name", "First", "Name",
                                         "Maiden", "Name", "Born", "Died", "Age",
                                         "Spouse", "Mother", "Father", "Notes"]


def test_detects_cemetery_columns():
    rows = rows_for("cloverdale")
    cols = [c.name for c in detect_columns(rows[0])]
    assert cols == ["Last Name", "First Name", "Maiden Name", "Born", "Died",
                    "Age", "Spouse", "Mother", "Father", "Notes"]


def test_assigns_values_to_columns():
    rows = rows_for("cloverdale")
    cols = detect_columns(rows[0])
    # Row 3 on page 1: Atwood / Margaret, died 1869-9-29 aged 36 yrs.
    match = [r for r in rows if any(w.text == "Margaret" for w in r)][0]
    got = assign_columns(match, cols)
    assert got["Last Name"] == "Atwood"
    assert got["First Name"] == "Margaret"
    assert got["Died"] == "1869-9-29"
    assert got["Age"] == "36 yrs"
    assert got["Spouse"] == "Lewis Atwood"


def test_right_aligned_age_still_lands_in_age():
    """'86 yrs 9 mos' is wider than its header and right-aligned."""
    rows = rows_for("cloverdale")
    cols = detect_columns(rows[0])
    match = [r for r in rows if any(w.text == "Thomas" for w in r)][0]
    assert assign_columns(match, cols)["Age"] == "86 yrs 9 mos"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_layout.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.layout'`

- [ ] **Step 3: Write the implementation**

`scripts/layout.py`:
```python
"""Turn positioned words into table rows and columns.

Rows come from clustering words by vertical position. Columns come from the
header row: adjacent header words separated by a small gap belong to one
heading ("Maiden" + "Name"), a larger gap starts a new column. Each column
then owns the horizontal span from its own start to the next column's start,
so values wider than their heading — right-aligned ages, long spouse names —
still land in the right place.
"""
from typing import NamedTuple

from scripts.extract import Word


class Column(NamedTuple):
    """A table column and the horizontal span it owns."""
    name: str
    x0: float
    x1: float


def group_rows(words: list[Word], tol: float = 3.0) -> list[list[Word]]:
    """Cluster words into rows by vertical midpoint, ordered top to bottom.

    `tol` is the vertical distance in points within which two words count as
    being on the same line.
    """
    rows: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (w.y0, w.x0)):
        mid = (w.y0 + w.y1) / 2
        for row in rows:
            ref = row[0]
            if abs(mid - (ref.y0 + ref.y1) / 2) <= tol:
                row.append(w)
                break
        else:
            rows.append([w])
    for row in rows:
        row.sort(key=lambda w: w.x0)
    return rows


def detect_columns(header: list[Word], gap: float = 8.0) -> list[Column]:
    """Derive columns from a header row.

    Header words closer together than `gap` are joined into one heading. Each
    column spans from its first word's left edge to the next column's left edge;
    the last column extends to infinity.
    """
    if not header:
        return []
    groups: list[list[Word]] = [[header[0]]]
    for prev, cur in zip(header, header[1:]):
        if cur.x0 - prev.x1 <= gap:
            groups[-1].append(cur)
        else:
            groups.append([cur])

    cols = []
    for i, group in enumerate(groups):
        name = " ".join(w.text for w in group)
        x0 = group[0].x0
        x1 = groups[i + 1][0].x0 if i + 1 < len(groups) else float("inf")
        cols.append(Column(name=name, x0=x0, x1=x1))
    return cols


def assign_columns(row: list[Word], cols: list[Column]) -> dict[str, str]:
    """Map a row's words onto column headings by horizontal position.

    A word belongs to the column whose span contains its midpoint; words left of
    every column fall into the first one.
    """
    out: dict[str, list[str]] = {c.name: [] for c in cols}
    for w in row:
        mid = (w.x0 + w.x1) / 2
        target = cols[0]
        for c in cols:
            if c.x0 <= mid < c.x1:
                target = c
                break
        out[target.name].append(w.text)
    return {name: " ".join(parts) for name, parts in out.items()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_layout.py -v`
Expected: 4 passed

If `test_assigns_values_to_columns` fails on `Age`, tune `gap` — do not special-case the Age column.

- [ ] **Step 5: Commit**

```bash
git add scripts/layout.py tests/test_layout.py
git commit -m "Assign table values to columns by coordinate span

Each column owns the span to the next column's start, so values wider than
their own heading land correctly instead of bleeding into a neighbour."
```

---

### Task 4: Value normalizers

**Files:**
- Create: `scripts/normalize.py`
- Test: `tests/test_normalize.py`

**Interfaces:**
- Consumes: nothing
- Produces: `parse_date(raw: str) -> str | None`, `surname_key(surname: str) -> str`, `import_key(filename: str, page: int, raw_line: str) -> str`

- [ ] **Step 1: Write the failing test**

`tests/test_normalize.py`:
```python
import pytest
from scripts.normalize import parse_date, surname_key, import_key


@pytest.mark.parametrize("raw,expected", [
    ("21 Feb 1813", "1813-02-21"),
    ("26 Apr 1854", "1854-04-26"),
    ("6 Dec 1815", "1815-12-06"),
    ("1869-9-29", "1869-09-29"),
    ("1831-2-11", "1831-02-11"),
    ("1857", "1857"),
    ("Apr 1854", "1854-04"),
    ("", None),
    ("   ", None),
    ("unknown", None),
])
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


def test_parse_date_rejects_impossible_days():
    assert parse_date("31 Feb 1813") is None


def test_surname_key_groups_spelling_variants():
    assert surname_key("Atwood") == surname_key("Attwood") == surname_key("Atwoode")


def test_surname_key_separates_unrelated_names():
    assert surname_key("Atwood") != surname_key("Blaisdell")


def test_surname_key_is_case_insensitive():
    assert surname_key("ATWOOD") == surname_key("atwood")


def test_surname_key_handles_empty():
    assert surname_key("") == ""


def test_import_key_is_stable():
    a = import_key("cloverdale.pdf", 1, "Atwood Ruth 1831-2-11")
    b = import_key("cloverdale.pdf", 1, "Atwood Ruth 1831-2-11")
    assert a == b and len(a) == 40


def test_import_key_varies_with_every_input():
    base = import_key("cloverdale.pdf", 1, "Atwood Ruth")
    assert base != import_key("gates.pdf", 1, "Atwood Ruth")
    assert base != import_key("cloverdale.pdf", 2, "Atwood Ruth")
    assert base != import_key("cloverdale.pdf", 1, "Atwood Ruthe")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_normalize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.normalize'`

- [ ] **Step 3: Write the implementation**

`scripts/normalize.py`:
```python
"""Normalisers shared by every parser."""
import calendar
import hashlib
import re

from metaphone import doublemetaphone

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}

_DMY = re.compile(r"^(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})$")
_MY = re.compile(r"^([A-Za-z]{3,})\s+(\d{4})$")
_ISOISH = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_YEAR = re.compile(r"^(\d{4})$")


def _valid(year: int, month: int, day: int) -> bool:
    return 1 <= month <= 12 and 1 <= day <= calendar.monthrange(year, month)[1]


def parse_date(raw: str) -> str | None:
    """Normalise a source date to ISO, keeping whatever precision exists.

    Returns 'YYYY-MM-DD', 'YYYY-MM', 'YYYY', or None when unparseable. Partial
    dates are common in these records and must not be discarded or guessed at.
    """
    s = (raw or "").strip()
    if not s:
        return None

    if m := _DMY.match(s):
        day, mon, year = int(m[1]), MONTHS.get(m[2][:3].lower()), int(m[3])
        if mon and _valid(year, mon, day):
            return f"{year:04d}-{mon:02d}-{day:02d}"
        return None

    if m := _ISOISH.match(s):
        year, mon, day = int(m[1]), int(m[2]), int(m[3])
        if _valid(year, mon, day):
            return f"{year:04d}-{mon:02d}-{day:02d}"
        return None

    if m := _MY.match(s):
        mon = MONTHS.get(m[1][:3].lower())
        if mon:
            return f"{int(m[2]):04d}-{mon:02d}"
        return None

    if m := _YEAR.match(s):
        return m[1]

    return None


def surname_key(surname: str) -> str:
    """Phonetic key so Atwood, Attwood and Atwoode match one another.

    Computed at import time and stored in an indexed column, so search behaves
    identically wherever it runs.
    """
    s = (surname or "").strip()
    if not s:
        return ""
    return doublemetaphone(s)[0]


def import_key(filename: str, page: int, raw_line: str) -> str:
    """Stable fingerprint for 'this row came from that line'.

    Lets re-import update untouched rows in place while leaving hand-corrected
    rows alone.
    """
    payload = f"{filename}\x00{page}\x00{raw_line}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_normalize.py -v`
Expected: 17 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/normalize.py tests/test_normalize.py
git commit -m "Normalise dates and surnames

Partial dates keep their precision rather than being padded to a false exact
day. Surnames get a phonetic key at import time so spelling drift is findable."
```

---

### Task 5: Schema and database module

**Files:**
- Create: `scripts/schema.sql`, `scripts/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: nothing
- Produces: `connect(path: Path) -> sqlite3.Connection` (foreign keys enabled, `Row` factory), `init_schema(conn) -> None`

- [ ] **Step 1: Write the failing test**

`tests/test_db.py`:
```python
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
    for _ in range(2):
        conn.execute(
            "INSERT INTO appearance (source_id,page,import_key,surname,surname_key,kind)"
            " VALUES (1,1,'dupe','Atwood','ATT','burial')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.commit()


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.db'`

- [ ] **Step 3: Write the schema**

`scripts/schema.sql`:
```sql
CREATE TABLE IF NOT EXISTS source (
  id          INTEGER PRIMARY KEY,
  filename    TEXT NOT NULL UNIQUE,
  title       TEXT NOT NULL,
  kind        TEXT NOT NULL,
  pages       INTEGER NOT NULL,
  sha256      TEXT NOT NULL,
  imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS appearance (
  id          INTEGER PRIMARY KEY,
  source_id   INTEGER NOT NULL REFERENCES source(id),
  page        INTEGER NOT NULL,
  import_key  TEXT UNIQUE,
  raw_line    TEXT,

  surname     TEXT NOT NULL,
  given       TEXT,
  surname_key TEXT NOT NULL,
  kind        TEXT NOT NULL,
  role        TEXT,
  pair_key    TEXT,
  date_raw    TEXT,
  date_iso    TEXT,
  place       TEXT,
  detail      TEXT,

  origin      TEXT NOT NULL DEFAULT 'imported',
  status      TEXT NOT NULL DEFAULT 'active',
  verified    INTEGER NOT NULL DEFAULT 0,
  note        TEXT,
  edited_at   TEXT,
  edited_by   TEXT
);

CREATE INDEX IF NOT EXISTS idx_appearance_surname     ON appearance(surname);
CREATE INDEX IF NOT EXISTS idx_appearance_surname_key ON appearance(surname_key);
CREATE INDEX IF NOT EXISTS idx_appearance_kind        ON appearance(kind);
CREATE INDEX IF NOT EXISTS idx_appearance_date        ON appearance(date_iso);
CREATE INDEX IF NOT EXISTS idx_appearance_pair        ON appearance(pair_key);

CREATE TABLE IF NOT EXISTS newsletter (
  id         INTEGER PRIMARY KEY,
  filename   TEXT NOT NULL UNIQUE,
  volume     TEXT,
  number     TEXT,
  issue_date TEXT,
  title      TEXT,
  pages      INTEGER NOT NULL,
  sha256     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS newsletter_page (
  newsletter_id INTEGER NOT NULL REFERENCES newsletter(id),
  page          INTEGER NOT NULL,
  text          TEXT NOT NULL,
  PRIMARY KEY (newsletter_id, page)
);
```

- [ ] **Step 4: Write the db module**

`scripts/db.py`:
```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_db.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add scripts/schema.sql scripts/db.py tests/test_db.py
git commit -m "Add the archive schema

Foreign keys are enabled per connection; SQLite ignores the constraint
otherwise, which would let appearances point at sources that do not exist."
```

---

### Task 6: Cemetery parser

**Files:**
- Create: `scripts/parsers/__init__.py`, `scripts/parsers/cemetery.py`
- Test: `tests/test_parsers.py`

**Interfaces:**
- Consumes: `group_rows`, `detect_columns`, `assign_columns`, `parse_date`, `surname_key`, `import_key`
- Produces: `Appearance` (dataclass, in `scripts/parsers/__init__.py`) with fields `surname, given, surname_key, kind, role, pair_key, date_raw, date_iso, place, detail, page, raw_line, import_key`; and `parse_cemetery(pdf_path: Path, title: str) -> list[Appearance]`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_parsers.py`:
```python
from conftest import PDF_DIR
from scripts.parsers.cemetery import parse_cemetery


def test_cemetery_extracts_expected_person():
    rows = parse_cemetery(PDF_DIR / "cloverdale.pdf", "Cloverdale Cemetery")
    ruth = [a for a in rows if a.surname == "Atwood" and a.given == "Ruth"][0]
    assert ruth.kind == "burial"
    assert ruth.date_iso == "1831-02-11"
    assert ruth.place == "Cloverdale Cemetery"
    assert "Thomas Atwood" in ruth.detail
    assert ruth.page == 1


def test_cemetery_skips_the_header_row():
    rows = parse_cemetery(PDF_DIR / "cloverdale.pdf", "Cloverdale Cemetery")
    assert not any(a.surname == "Last" for a in rows)


def test_cemetery_row_count_is_plausible():
    rows = parse_cemetery(PDF_DIR / "cloverdale.pdf", "Cloverdale Cemetery")
    assert 140 <= len(rows) <= 170


def test_cemetery_every_row_has_identity_and_key():
    rows = parse_cemetery(PDF_DIR / "cloverdale.pdf", "Cloverdale Cemetery")
    assert all(a.surname and a.import_key and a.page >= 1 for a in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_parsers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.parsers'`

- [ ] **Step 3: Write the shared Appearance type**

`scripts/parsers/__init__.py`:
```python
"""Parsers turning positioned table rows into person-appearances."""
from dataclasses import dataclass


@dataclass
class Appearance:
    """One person as they appear on one source line.

    A source line naming several people yields several Appearances sharing a
    pair_key. This asserts nothing about identity across different lines.
    """
    surname: str
    given: str | None
    surname_key: str
    kind: str
    page: int
    raw_line: str
    import_key: str
    role: str | None = None
    pair_key: str | None = None
    date_raw: str | None = None
    date_iso: str | None = None
    place: str | None = None
    detail: str | None = None
```

- [ ] **Step 4: Write the cemetery parser**

`scripts/parsers/cemetery.py`:
```python
"""Parser for the eleven mapped-cemetery inventories.

Columns: Last Name, First Name, Maiden Name, Born, Died, Age, Spouse, Mother,
Father, Notes. Not every file carries every trailing column.
"""
from pathlib import Path

from scripts.extract import extract_words, page_count
from scripts.layout import assign_columns, detect_columns, group_rows
from scripts.normalize import import_key, parse_date, surname_key
from scripts.parsers import Appearance


def _detail(vals: dict[str, str]) -> str | None:
    """Fold the relationship and note columns into one human-readable string."""
    bits = []
    for label, col in (("age", "Age"), ("spouse", "Spouse"),
                       ("mother", "Mother"), ("father", "Father"),
                       ("maiden", "Maiden Name"), ("note", "Notes")):
        if v := vals.get(col, "").strip():
            bits.append(f"{label} {v}" if label != "note" else v)
    return " · ".join(bits) or None


def parse_cemetery(pdf_path: Path, title: str) -> list[Appearance]:
    """Extract burials from one cemetery PDF.

    The header row appears on page 1 only; later pages reuse those columns.
    """
    out: list[Appearance] = []
    cols = None
    for page in range(1, page_count(pdf_path) + 1):
        rows = group_rows(extract_words(pdf_path, page))
        if not rows:
            continue
        start = 0
        if cols is None:
            cols = detect_columns(rows[0])
            start = 1
        for row in rows[start:]:
            vals = assign_columns(row, cols)
            surname = vals.get("Last Name", "").strip()
            given = vals.get("First Name", "").strip() or None
            if not surname:
                continue
            raw_line = " ".join(w.text for w in row)
            died = vals.get("Died", "").strip()
            born = vals.get("Born", "").strip()
            date_raw = died or born or None
            detail = _detail(vals)
            if born and died:
                detail = f"born {born}" + (f" · {detail}" if detail else "")
            out.append(Appearance(
                surname=surname,
                given=given,
                surname_key=surname_key(surname),
                kind="burial",
                role="deceased",
                page=page,
                raw_line=raw_line,
                import_key=import_key(pdf_path.name, page, raw_line),
                date_raw=date_raw,
                date_iso=parse_date(date_raw or ""),
                place=title,
                detail=detail,
            ))
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_parsers.py -v`
Expected: 4 passed

- [ ] **Step 6: Verify the parser across all eleven cemeteries**

```bash
.venv/bin/python -c "
from pathlib import Path
from scripts.parsers.cemetery import parse_cemetery
for s in ['cloverdale','eastcambridge','gates','hopkins','jeffersonville','mtview',
          'northcambridge','plainsroad','riverroad','smilie','southcambridge']:
    n = len(parse_cemetery(Path('pdfs')/f'{s}.pdf', s))
    print(f'{s:<18} {n}')
"
```
Expected: non-zero counts for all eleven, with mtview and jeffersonville well over 1,000. Investigate any zero before continuing.

- [ ] **Step 7: Commit**

```bash
git add scripts/parsers/__init__.py scripts/parsers/cemetery.py tests/test_parsers.py
git commit -m "Parse the eleven cemetery inventories

Header columns are read once from page 1 and reused; later pages carry rows
only."
```

---

### Task 7: Birth and marriage parsers

**Files:**
- Create: `scripts/parsers/vital.py`
- Test: `tests/test_parsers.py` (append)

**Interfaces:**
- Consumes: `Appearance`, layout and normalize helpers
- Produces: `parse_birth(pdf_path: Path) -> list[Appearance]`, `parse_marriage(pdf_path: Path) -> list[Appearance]`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_parsers.py`:
```python
from scripts.parsers.vital import parse_birth, parse_marriage


def test_birth_extracts_the_child():
    rows = parse_birth(PDF_DIR / "birth_records.pdf")
    a = [r for r in rows if r.given == "Adalia Ellen" and r.surname == "Adams"][0]
    assert a.kind == "birth" and a.role == "child"
    assert a.date_iso == "1854-04-26"


def test_birth_also_emits_the_father():
    rows = parse_birth(PDF_DIR / "birth_records.pdf")
    child = [r for r in rows if r.given == "Adalia Ellen"][0]
    father = [r for r in rows if r.pair_key == child.pair_key and r.role == "father"][0]
    assert father.surname == "Adams" and father.given == "Dexter"


def test_marriage_emits_both_parties_sharing_a_pair_key():
    rows = parse_marriage(PDF_DIR / "marriage_records2.pdf")
    groom = [r for r in rows if r.surname == "Atwood" and r.given == "Julius"][0]
    bride = [r for r in rows if r.pair_key == groom.pair_key and r.role == "bride"][0]
    assert groom.role == "groom"
    assert bride.surname == "Smilie" and bride.given == "Louisa"
    assert groom.date_iso == bride.date_iso == "1849-08-22"


def test_vital_rows_are_plausible_in_number():
    assert 1000 <= len(parse_birth(PDF_DIR / "birth_records.pdf")) <= 4000
    assert 800 <= len(parse_marriage(PDF_DIR / "marriage_records2.pdf")) <= 1200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_parsers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.parsers.vital'`

- [ ] **Step 3: Write the implementation**

`scripts/parsers/vital.py`:
```python
"""Birth and marriage parsers.

Both fan out: a source line naming several people yields one Appearance each,
sharing a pair_key, so a bride is findable under her own surname and a father
under his own name rather than only as a footnote on someone else's row.
"""
from pathlib import Path

from scripts.extract import extract_words, page_count
from scripts.layout import assign_columns, detect_columns, group_rows
from scripts.normalize import import_key, parse_date, surname_key
from scripts.parsers import Appearance


def _pages(pdf_path: Path):
    """Yield (page, header_columns, data_rows), reading columns from page 1."""
    cols = None
    for page in range(1, page_count(pdf_path) + 1):
        rows = group_rows(extract_words(pdf_path, page))
        if not rows:
            continue
        start = 0
        if cols is None:
            cols = detect_columns(rows[0])
            start = 1
        yield page, cols, rows[start:]


def parse_birth(pdf_path: Path) -> list[Appearance]:
    """Columns: Volume, Birth Day, Child, Family Name, Father."""
    out: list[Appearance] = []
    for page, cols, rows in _pages(pdf_path):
        for row in rows:
            v = assign_columns(row, cols)
            surname = v.get("Family Name", "").strip()
            child = v.get("Child", "").strip()
            if not surname or not child:
                continue
            raw = " ".join(w.text for w in row)
            key = import_key(pdf_path.name, page, raw)
            date_raw = v.get("Birth Day", "").strip() or None
            iso = parse_date(date_raw or "")
            vol = v.get("Volume", "").strip() or None

            out.append(Appearance(
                surname=surname, given=child, surname_key=surname_key(surname),
                kind="birth", role="child", pair_key=key, page=page,
                raw_line=raw, import_key=key, date_raw=date_raw, date_iso=iso,
                place=vol, detail=None,
            ))
            if father := v.get("Father", "").strip():
                out.append(Appearance(
                    surname=surname, given=father, surname_key=surname_key(surname),
                    kind="birth", role="father", pair_key=key, page=page,
                    raw_line=raw, import_key=f"{key}:father",
                    date_raw=date_raw, date_iso=iso, place=vol,
                    detail=f"father of {child}",
                ))
    return out


def parse_marriage(pdf_path: Path) -> list[Appearance]:
    """Columns: Volume, Marriage Date, Groom First/Last, Bride First/Last, Notes."""
    out: list[Appearance] = []
    for page, cols, rows in _pages(pdf_path):
        for row in rows:
            v = assign_columns(row, cols)
            g_last = v.get("Groom Last", "").strip()
            b_last = v.get("Bride Last", "").strip()
            if not g_last and not b_last:
                continue
            raw = " ".join(w.text for w in row)
            key = import_key(pdf_path.name, page, raw)
            date_raw = v.get("Marriage Date", "").strip() or None
            iso = parse_date(date_raw or "")
            vol = v.get("Volume", "").strip() or None
            note = v.get("Notes", "").strip() or None
            g_first = v.get("Groom First", "").strip() or None
            b_first = v.get("Bride First", "").strip() or None

            for last, first, role, other in (
                (g_last, g_first, "groom", f"{b_first or ''} {b_last}".strip()),
                (b_last, b_first, "bride", f"{g_first or ''} {g_last}".strip()),
            ):
                if not last:
                    continue
                detail = f"married {other}" if other else None
                if note:
                    detail = f"{detail} · {note}" if detail else note
                out.append(Appearance(
                    surname=last, given=first, surname_key=surname_key(last),
                    kind="marriage", role=role, pair_key=key, page=page,
                    raw_line=raw, import_key=f"{key}:{role}",
                    date_raw=date_raw, date_iso=iso, place=vol, detail=detail,
                ))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_parsers.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/parsers/vital.py tests/test_parsers.py
git commit -m "Parse births and marriages, emitting every named person

A bride recorded only as a groom's row is invisible to anyone searching her own
surname, which is precisely the search a researcher runs."
```

---

### Task 8: Death, warning and freeman parsers

**Files:**
- Create: `scripts/parsers/simple.py`
- Test: `tests/test_parsers.py` (append)

**Interfaces:**
- Consumes: `Appearance`, layout and normalize helpers
- Produces: `parse_death(pdf_path)`, `parse_warning(pdf_path)`, `parse_freeman(pdf_path)`, each `-> list[Appearance]`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_parsers.py`:
```python
from scripts.parsers.simple import parse_death, parse_warning, parse_freeman


def test_death_extracts_person_and_date():
    rows = parse_death(PDF_DIR / "death_records.pdf")
    levi = [r for r in rows if r.surname == "Atwood" and r.given == "Levi"][0]
    assert levi.kind == "death" and levi.date_iso == "1813-02-21"


def test_warning_extracts_person_and_date():
    rows = parse_warning(PDF_DIR / "warningsout_records.pdf")
    asa = [r for r in rows if r.surname == "Adams" and r.given == "Asa"][0]
    assert asa.kind == "warning" and asa.date_iso == "1815-12-06"


def test_freeman_extracts_person_and_date():
    rows = parse_freeman(PDF_DIR / "freemansworn_records.pdf")
    dexter = [r for r in rows if r.surname == "Adams" and r.given == "Dexter"][0]
    assert dexter.kind == "freeman" and dexter.date_iso == "1828-09-02"


def test_simple_parsers_have_plausible_counts():
    assert 200 <= len(parse_death(PDF_DIR / "death_records.pdf")) <= 400
    assert 90 <= len(parse_warning(PDF_DIR / "warningsout_records.pdf")) <= 200
    assert 800 <= len(parse_freeman(PDF_DIR / "freemansworn_records.pdf")) <= 1100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_parsers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.parsers.simple'`

- [ ] **Step 3: Write the implementation**

`scripts/parsers/simple.py`:
```python
"""Parsers for the three one-person-per-row town record tables.

Each has a volume reference, a date, and a name split across two columns; only
the column names and the event kind differ.
"""
from pathlib import Path

from scripts.layout import assign_columns
from scripts.normalize import import_key, parse_date, surname_key
from scripts.parsers import Appearance
from scripts.parsers.vital import _pages


def _parse(pdf_path: Path, kind: str, vol_col: str, date_col: str,
           last_col: str, first_col: str) -> list[Appearance]:
    """Shared body: one Appearance per row that names somebody."""
    out: list[Appearance] = []
    for page, cols, rows in _pages(pdf_path):
        for row in rows:
            v = assign_columns(row, cols)
            surname = v.get(last_col, "").strip()
            if not surname:
                continue
            raw = " ".join(w.text for w in row)
            date_raw = v.get(date_col, "").strip() or None
            out.append(Appearance(
                surname=surname,
                given=v.get(first_col, "").strip() or None,
                surname_key=surname_key(surname),
                kind=kind,
                page=page,
                raw_line=raw,
                import_key=import_key(pdf_path.name, page, raw),
                date_raw=date_raw,
                date_iso=parse_date(date_raw or ""),
                place=v.get(vol_col, "").strip() or None,
            ))
    return out


def parse_death(pdf_path: Path) -> list[Appearance]:
    """Columns: Volume/Page, First Name, Last Name, Date, Age."""
    return _parse(pdf_path, "death", "Volume/Page", "Date", "Last Name", "First Name")


def parse_warning(pdf_path: Path) -> list[Appearance]:
    """Columns: Volume, Date of Warning, Last Name, First Name."""
    return _parse(pdf_path, "warning", "Volume", "Date of Warning",
                  "Last Name", "First Name")


def parse_freeman(pdf_path: Path) -> list[Appearance]:
    """Columns: Volume, Date of Oath, First Name, Last Name."""
    return _parse(pdf_path, "freeman", "Volume", "Date of Oath",
                  "Last Name", "First Name")
```

Note: `freemansworn_records` and `townmeetings_name_references` carry a title line above the header. If `detect_columns` picks up the title instead of the header, `_pages` needs a header-detection tweak: skip rows until one contains a known column word such as `Volume`. Make that change in `_pages` rather than in each parser.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_parsers.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/parsers/simple.py tests/test_parsers.py
git commit -m "Parse death, warning-out and freeman's-oath records"
```

---

### Task 9: Import orchestrator with edit preservation

**Files:**
- Create: `scripts/import_pdfs.py`
- Test: `tests/test_import.py`

**Interfaces:**
- Consumes: every parser, `connect`, `init_schema`
- Produces: `SOURCES: dict[str, tuple[str, str, callable]]` (stem → (title, source kind, parser)), `import_all(conn, pdf_dir: Path) -> dict[str, int]`, `upsert(conn, source_id: int, rows: list[Appearance]) -> tuple[int, int, int]` returning (inserted, updated, skipped_edited)

- [ ] **Step 1: Write the failing test**

`tests/test_import.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_import.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.import_pdfs'`

- [ ] **Step 3: Write the implementation**

`scripts/import_pdfs.py`:
```python
"""Load record PDFs into SQLite, preserving hand corrections.

The PDFs are one input and the volunteers are another. Re-running import must
never destroy a correction, so rows carrying edited_at are left untouched and
rows that vanish from a source are retired rather than deleted.
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
    marked retired.
    """
    now = datetime.now(timezone.utc).isoformat()
    existing = {
        r["import_key"]: r for r in conn.execute(
            "SELECT import_key, edited_at FROM appearance WHERE source_id = ?",
            (source_id,))
        if r["import_key"] is not None
    }
    seen, inserted, updated, skipped = set(), 0, 0, 0

    for a in rows:
        seen.add(a.import_key)
        prior = existing.get(a.import_key)
        if prior is not None and prior["edited_at"]:
            skipped += 1
            continue
        # Named placeholders so one dict drives both statements — the INSERT and
        # UPDATE differ only in whether source_id is set.
        fields = {
            "source_id": source_id, "page": a.page, "import_key": a.import_key,
            "raw_line": a.raw_line, "surname": a.surname, "given": a.given,
            "surname_key": a.surname_key, "kind": a.kind, "role": a.role,
            "pair_key": a.pair_key, "date_raw": a.date_raw,
            "date_iso": a.date_iso, "place": a.place, "detail": a.detail,
        }
        if prior is None:
            conn.execute(
                "INSERT INTO appearance (source_id,page,import_key,raw_line,surname,"
                "given,surname_key,kind,role,pair_key,date_raw,date_iso,place,detail)"
                " VALUES (:source_id,:page,:import_key,:raw_line,:surname,:given,"
                ":surname_key,:kind,:role,:pair_key,:date_raw,:date_iso,:place,"
                ":detail)", fields)
            inserted += 1
        else:
            conn.execute(
                "UPDATE appearance SET page=:page, raw_line=:raw_line,"
                " surname=:surname, given=:given, surname_key=:surname_key,"
                " kind=:kind, role=:role, pair_key=:pair_key, date_raw=:date_raw,"
                " date_iso=:date_iso, place=:place, detail=:detail,"
                " status='active' WHERE import_key=:import_key", fields)
            updated += 1

    stale = [k for k in existing if k not in seen]
    for key in stale:
        conn.execute("UPDATE appearance SET status='retired' WHERE import_key=?",
                     (key,))
    conn.commit()
    return inserted, updated, skipped


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_import.py -v`
Expected: 4 passed

- [ ] **Step 5: Build the database**

```bash
.venv/bin/python -m scripts.import_pdfs
```

- [ ] **Step 6: Commit**

```bash
git add scripts/import_pdfs.py tests/test_import.py
git commit -m "Import records to SQLite, treating hand corrections as sacred

Edited rows survive re-import untouched and vanished rows are retired rather
than deleted. Silently losing a row is a worse failure for an archive than
crashing."
```

---

### Task 10: Validation gates and review report

**Files:**
- Create: `scripts/validate.py`, `data/baseline.json`
- Test: `tests/test_golden.py`

**Interfaces:**
- Consumes: `connect`
- Produces: `check_counts(conn, baseline: dict) -> list[str]`, `check_integrity(conn) -> list[str]`, `review_report(conn) -> list[dict]`

- [ ] **Step 1: Write the failing test**

`tests/test_golden.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_golden.py -v`
Expected: FAIL — `scripts.validate` missing and `data/baseline.json` absent

- [ ] **Step 3: Write the validator**

`scripts/validate.py`:
```python
"""Integrity gates and the human-review report.

A parser regression that silently drops several hundred people is the failure
this exists to catch, so count drift fails the build rather than shipping.
"""
import sqlite3

TOLERANCE = 0.02  # 2% drift allowed before a source is considered broken


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


def review_report(conn: sqlite3.Connection) -> list[dict]:
    """Rows a human should look at. Never auto-corrected.

    Flags names that look reversed or malformed — Cloverdale's first row parses
    as surname 'Alida', given name 'Seeley', which is likely reversed in the
    original transcription rather than misparsed. Guessing here would launder a
    real transcription error into the archive.
    """
    flags = []
    rows = conn.execute(
        "SELECT a.id, a.surname, a.given, a.date_raw, a.date_iso, a.page,"
        " s.filename FROM appearance a JOIN source s ON s.id=a.source_id"
        " WHERE a.status='active'").fetchall()
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
        if reasons:
            flags.append({"id": r["id"], "file": r["filename"], "page": r["page"],
                          "name": f"{r['surname']}, {r['given']}",
                          "reasons": reasons})
    return flags


if __name__ == "__main__":
    import json
    from pathlib import Path
    from scripts.db import connect

    conn = connect(Path("data/archive.sqlite"))
    baseline = json.loads(Path("data/baseline.json").read_text())
    problems = check_counts(conn, baseline) + check_integrity(conn)
    report = review_report(conn)

    for p in problems:
        print(f"FAIL {p}")
    print(f"\n{len(report)} rows flagged for review")
    for f in report[:40]:
        print(f"  {f['file']} p{f['page']}: {f['name']} — {', '.join(f['reasons'])}")
    raise SystemExit(1 if problems else 0)
```

- [ ] **Step 4: Generate the baseline from the current parse**

```bash
.venv/bin/python -c "
import json
from pathlib import Path
from scripts.db import connect
conn = connect(Path('data/archive.sqlite'))
rows = conn.execute('''SELECT s.filename f, COUNT(*) c FROM appearance a
  JOIN source s ON s.id=a.source_id WHERE a.status='active' GROUP BY s.filename''')
baseline = {r['f']: r['c'] for r in rows}
Path('data/baseline.json').write_text(json.dumps(baseline, indent=2, sort_keys=True))
print(json.dumps(baseline, indent=2, sort_keys=True))
"
```

Read the numbers before committing them. A baseline recording a broken parse makes every later check meaningless. Sanity-check against these observed row counts: cloverdale ~155, jeffersonville ~1331, mtview ~1341, birth_records ~1304 (plus fathers), marriage_records2 ~500 (×2 for both parties), death_records ~274, warningsout ~128, freemansworn ~971.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_golden.py -v`
Expected: 6 passed

- [ ] **Step 6: Run the validator and read the review report**

```bash
.venv/bin/python -m scripts.validate
```

Expected: exit 0, plus a list of flagged rows. Read them. If the flagged count exceeds roughly 5% of all rows, a parser is misbehaving — investigate before continuing rather than raising the threshold.

- [ ] **Step 7: Commit**

```bash
git add scripts/validate.py data/baseline.json tests/test_golden.py
git commit -m "Gate the parse on row counts, integrity and golden records

Count drift beyond 2% fails rather than shipping. Suspicious rows are reported
for a human instead of being auto-corrected, so a transcription error is never
laundered into the archive as fact."
```

---

### Task 11: Commit the built database and document the pipeline

**Files:**
- Create: `scripts/README.md`
- Modify: `README.md`, `.gitignore`
- Commit: `data/archive.sqlite`

**Interfaces:**
- Consumes: everything above
- Produces: `data/archive.sqlite` in the repo, ready for Phase 2's D1 load

- [ ] **Step 1: Rebuild the database from scratch**

```bash
rm -f data/archive.sqlite
.venv/bin/python -m scripts.import_pdfs
.venv/bin/python -m scripts.validate
```
Expected: validator exits 0.

- [ ] **Step 2: Confirm the full suite passes**

Run: `.venv/bin/python -m pytest -v`
Expected: all tests pass. Record the count.

- [ ] **Step 3: Write the pipeline docs**

`scripts/README.md`:
```markdown
# Archive extraction pipeline

Turns the record PDFs in `pdfs/` into `data/archive.sqlite`.

## Running it

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m scripts.import_pdfs    # build the database
.venv/bin/python -m scripts.validate       # gates + review report
.venv/bin/python -m pytest                 # full suite
```

Use `.venv/bin/python -m pip`, never `.venv/bin/pip` — venv script shebangs
hold absolute paths and break if the folder is moved.

## How it works

`pdftotext -bbox-layout` gives every word an x/y box. Words are grouped into
rows by vertical position, and into columns by horizontal overlap with a header
row. This is why plain `-layout` is not used: header tokens such as
`Maiden Name Born` collapse into one field, and the tables mix left-aligned
name columns with right-aligned age columns, so character-offset slicing
misparses them.

## Adding a source

1. Put the PDF in `pdfs/`.
2. Add an entry to `SOURCES` in `scripts/import_pdfs.py`.
3. Write a parser in `scripts/parsers/` if its columns are new.
4. Rebuild, then regenerate `data/baseline.json` and read the numbers before
   committing them.

## Not yet parsed

These are not row-per-person tables and need their own handling:
`taxpayers_1874` (four side-by-side name pairs), `townmeetings_name_references`
(page/date matrix), `cattle_earmarks` (pictorial marks), `crows_and_foxes`,
`land_records_vol_1_name_index` (free-form index), `1790_census` (statistical
table).
```

- [ ] **Step 4: Note the archive database in the main README**

Add to `README.md` under "What's here":

```markdown
## Searchable archive

`data/archive.sqlite` holds the person-level index extracted from the record
PDFs — see `scripts/README.md` to rebuild it, and
`docs/superpowers/specs/2026-09-09-chs-archive-search-design.md` for the design.
```

- [ ] **Step 5: Commit**

```bash
git add scripts/README.md README.md data/archive.sqlite data/baseline.json
git commit -m "Commit the built archive database and pipeline docs

The database is the Phase 2 input for the D1 load, and having it in git means
the extracted data survives independently of any hosting decision."
```

---

## Definition of done

- [ ] `.venv/bin/python -m pytest` passes with no failures
- [ ] `.venv/bin/python -m scripts.validate` exits 0
- [ ] `data/archive.sqlite` holds between 7,000 and 15,000 active appearances across 16 sources
- [ ] The review report has been read, and flagged rows are under ~5% of the total
- [ ] Re-running `import_pdfs` twice in a row changes no row counts
- [ ] `data/baseline.json` numbers have been eyeballed against the expected counts, not blindly accepted

## Known risks

- **Column detection may need per-file tuning.** The `gap` threshold in `detect_columns` is the first knob; adjust it rather than special-casing individual columns.
- **`freemansworn_records` has a title line above its header.** If `detect_columns` grabs the title, fix header detection in `_pages` so it skips rows until one contains a known column word.
- **The baseline is only as good as the first parse.** Step 4 of Task 10 exists to force a human to look at the numbers before they become the standard everything else is measured against.
