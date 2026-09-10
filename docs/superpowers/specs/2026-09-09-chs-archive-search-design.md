# Searchable archive for the Cambridge Historical Society

**Date:** 2026-09-09
**Status:** Approved design, not yet planned or implemented
**Repo:** `prasta1/chs-website`

## Problem

The records section currently lists 22 PDFs by title. Someone hunting an ancestor has to
download all 22 and search each one by hand. The Harkener archive has the same shape: 30
newsletters, browsable only by date.

The underlying data is far more valuable than the current presentation admits. The record
PDFs are **tables**, not prose, and hold roughly 7,400 person-rows — 1,341 burials in
Mountain View alone, 1,304 births, 971 freemen sworn, 500 marriages. All 52 PDFs carry
extractable text; no OCR is required.

Two goals:

1. Searching a surname should return **people** — every appearance across cemeteries,
   births, marriages, deaths and town records, with dates, linked to the source page.
2. Board members must be able to **correct and add records from a browser**, with no
   install, no repository, and no terminal.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| What search returns | Person index for records, full-text for newsletters | One extraction pipeline, two outputs |
| PDF hosting | Committed to this repo | An index pointing at 404s is worse than no index; five Harkener issues already 404 on Weebly |
| Store | Cloudflare D1 (SQLite at the edge) | Real SQL for search, edit, extract; no server to run; schema is portable SQLite |
| Editing | `/admin` behind Cloudflare Access | Volunteers get an emailed sign-in code — no install, no repo, no stored passwords |
| Account | CHS-owned Cloudflare account | Clean succession: the org can keep its archive if Patrick steps back |
| Durability | Scheduled `wrangler d1 export` committed to git | Live data in D1, versioned vendor-independent copy in the repo |

A hosted database was initially rejected on the grounds that 7,400 rows is small enough to
serve statically. That reasoning was about performance and missed the real requirement:
the archive must be **writable** by non-technical volunteers. Data size was never the
constraint; human access was.

## Architecture

```
Cloudflare Pages · project: chs-website · CHS-owned account
├── static/          HTML, CSS, JS, and the 52 source PDFs
├── functions/
│   ├── api/search           public, read-only, queries D1
│   └── api/admin/*          CRUD, gated by Cloudflare Access
└── binding: DB → chs-archive (D1)

scripts/
├── import_pdfs.py           PDFs → SQL, run locally by the maintainer
└── validate.py              integrity gates, run in CI
```

Public search queries D1 directly at the edge (~50 ms). There is no regeneration step and
no window in which the site is stale relative to a correction.

## Data model

```sql
CREATE TABLE source (
  id          INTEGER PRIMARY KEY,
  filename    TEXT NOT NULL UNIQUE,      -- 'cloverdale.pdf'
  title       TEXT NOT NULL,             -- 'Cloverdale Cemetery'
  kind        TEXT NOT NULL,             -- cemetery|vital|land|census|town
  pages       INTEGER NOT NULL,
  sha256      TEXT NOT NULL,
  imported_at TEXT NOT NULL
);

CREATE TABLE appearance (
  id          INTEGER PRIMARY KEY,
  source_id   INTEGER NOT NULL REFERENCES source(id),
  page        INTEGER NOT NULL,
  import_key  TEXT UNIQUE,               -- NULL for manually added rows
  raw_line    TEXT,                      -- exactly what the parser read

  surname     TEXT NOT NULL,
  given       TEXT,
  surname_key TEXT NOT NULL,             -- Double Metaphone, indexed
  kind        TEXT NOT NULL,             -- burial|birth|marriage|death|tax|warning|freeman
  role        TEXT,                      -- child|father|mother|groom|bride|spouse|deceased
  pair_key    TEXT,                      -- links both halves of a marriage, or a family group
  date_raw    TEXT,                      -- '1831-2-11', '26 Apr 1854', 'abt 1840'
  date_iso    TEXT,                      -- normalised; partial dates allowed (YYYY, YYYY-MM)
  place       TEXT,
  detail      TEXT,

  origin      TEXT NOT NULL DEFAULT 'imported',  -- imported|manual
  status      TEXT NOT NULL DEFAULT 'active',    -- active|retired
  verified    INTEGER NOT NULL DEFAULT 0,
  note        TEXT,
  edited_at   TEXT,
  edited_by   TEXT
);

CREATE INDEX idx_appearance_surname     ON appearance(surname);
CREATE INDEX idx_appearance_surname_key ON appearance(surname_key);
CREATE INDEX idx_appearance_kind        ON appearance(kind);
CREATE INDEX idx_appearance_date        ON appearance(date_iso);

CREATE TABLE newsletter (
  id         INTEGER PRIMARY KEY,
  filename   TEXT NOT NULL UNIQUE,
  volume     TEXT,
  number     TEXT,
  issue_date TEXT,
  title      TEXT,
  pages      INTEGER NOT NULL,
  sha256     TEXT NOT NULL
);

CREATE TABLE newsletter_page (
  newsletter_id INTEGER NOT NULL REFERENCES newsletter(id),
  page          INTEGER NOT NULL,
  text          TEXT NOT NULL,
  PRIMARY KEY (newsletter_id, page)
);
```

Two field names need care because they look interchangeable and are not:

- **`source.kind`** describes the *document* (`cemetery`, `vital`, `land`, `census`,
  `town`). **`appearance.kind`** describes the *event* (`burial`, `birth`, `marriage`,
  `death`, `tax`, `warning`, `freeman`). One vital-records PDF yields births, marriages and
  deaths, so the two vocabularies are deliberately different and must not be merged.
- **`pair_key`** links appearances extracted from the *same source line* — the two halves
  of a marriage, or a child and their named parents. It asserts nothing about identity
  across different lines or documents.

### One row per appearance, not per person

Ruth Atwood appears once as a birth, once as a marriage, once in the cemetery. Searching
`Atwood` returns all three in date order. That is not duplication — it is a life traced
across the town's records, which is exactly what a researcher currently assembles by hand.

Rows fan out where a source line names more than one person:

- A **marriage** row emits two appearances, groom and bride, sharing a `pair_key`, so the
  bride is findable under her own surname.
- A **birth** row emits the child plus any named father and mother, with `role` set
  accordingly and a shared `pair_key`. This makes parents searchable in their own right.

Expect roughly 12,000 appearances from ~7,400 source rows.

Merging appearances into unified person entities is deliberately **out of scope** — it is a
hard genealogical modelling problem and the appearance list is useful without it.

## Import and edit preservation

The PDFs are one input; the volunteers are another. Re-running the import must never
destroy a correction.

Every imported row carries an `import_key`: a hash of source filename, page, and the exact
raw text line. That is a stable fingerprint for "this row came from that line". `raw_line`
is stored beside it so a bad parse is inspectable rather than mysterious.

| Situation | Behaviour |
|---|---|
| Key exists, never hand-edited | Updated in place |
| Key exists, `edited_at` set | **Left untouched.** If the source line also changed, flagged as a conflict for review |
| New key | Inserted |
| Key absent from the PDF | `status` set to `retired` |

Nothing is ever deleted. For an archive, silently losing a row is a worse failure than
crashing.

Extraction uses `pdftotext -layout`, which preserves the fixed-width table structure.
Default (non-layout) extraction returns text column-major — every surname, then every given
name — which would scramble the data. This is not optional.

## Search

Genealogical search lives or dies on spelling drift: Atwood, Attwood and Atwoode are one
family across three clerks. Each surname therefore gets a Double Metaphone key computed
**at import time** and stored in an indexed column. Queries match literal text and phonetic
key. Computing it at import rather than query time keeps behaviour identical everywhere and
queries fast.

Query supports: surname prefix, phonetic match, filter by record kind, and date range.

Newsletters use SQLite FTS5 over `newsletter_page`, returning issue, page and a snippet.

## Admin

`/admin` sits behind Cloudflare Access, which gates on an emailed sign-in code against an
invited email list — free up to 50 users. No password is ever created, transmitted, or
stored by this application.

Editors can: correct any field, add a record that exists in no PDF (`origin = 'manual'`),
mark a row `verified`, retire a row, and leave a note. Every write stamps `edited_at` and
`edited_by`.

Account and Access setup is performed by the maintainer in the Cloudflare dashboard. It is
not automated by this project.

## Validation and testing

Run in CI on every import:

- **Per-source row counts** must match a committed baseline. A parser regression that drops
  200 people fails the build rather than shipping.
- Every appearance must carry a valid `source_id` and `page`.
- **Golden tests**: a fixed set of known people must resolve with exact expected fields.
- A **review report** lists suspicious rows rather than guessing. Cloverdale's first row
  parses as surname `Alida`, given name `Seeley`, which is likely a reversed entry in the
  original transcription. Such rows are surfaced for a human, never auto-corrected.

## Provenance

Every result links to its source PDF at the exact page (`#page=N`) and carries a note that
these are volunteer transcriptions with the PDF as authoritative. Jen Bartlau's
transcription of Books A, B and C is credited by name. Corrected rows show that they were
edited.

Genealogy data that circulates without provenance causes real downstream harm: errors get
copied into family trees and can never be traced back to their source.

## Phases

1. **Extraction and schema, local SQLite only.** Parsers for each record type, validation
   gates, golden tests. De-risks everything else — if the parse is unreliable, nothing
   downstream matters.
2. **D1 and public search.** Load the database, `/api/search`, rebuild the records page UI.
3. **Admin and Access.** CRUD behind auth.
4. **Newsletter full-text.** FTS5 index and newsletter search UI.
5. **Backup automation.** Scheduled `wrangler d1 export` committed to the repo.

Ship Phase 1 before committing to the rest.

## Risks

- **Parser quality on ragged tables is the dominant risk.** Column alignment varies between
  files and the source transcriptions contain quirks. Mitigated by per-file parsers,
  baseline row counts, and the review report.
- **FTS5 availability in D1 must be verified** before Phase 4. If unavailable, fall back to
  `LIKE` over `newsletter_page`, which is adequate for 30 documents.
- **CHS must create the Cloudflare account** before Phase 2 can deploy.
- **Five Harkener issues 404 on the source site** (Jul 2020, Jun 2021, Mar 2020, Oct 2021,
  Sep 2020). Committing PDFs to the repo makes these recoverable only if CHS still holds
  the originals.

## Out of scope

- Public user accounts, submissions, or comments
- OCR or scanned page images of the original handwritten books
- Merging appearances into unified person records
- Replacing the live Weebly site — this remains a prototype until CHS decides otherwise

## Assumption to confirm

"No one deals with GitHub" is read as *volunteers* never touching it. The maintainer still
pushes PDFs and lets Pages deploy from the repo, and a scheduled Action runs the database
backup. If GitHub should be out of the maintainer's loop too, deploys move to direct
`wrangler` uploads and backups to R2 instead.
