# Archive extraction pipeline

Turns the record PDFs in `pdfs/` into `data/archive.sqlite` — a searchable
person index for the Cambridge Historical Society's cemetery, vital, and town
records.

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

`import_pdfs` is safe to re-run: it upserts by a stable `import_key` (a hash
of filename, page and raw line), leaves rows with a hand correction
(`edited_at` set) untouched, and retires rows that vanish from a source
rather than deleting them. Re-running it twice in a row changes no counts.

## How it works

`pdftotext -bbox-layout` gives every word an x/y box. Words are grouped into
rows by vertical position, and into columns by horizontal overlap with a
header row. This is why plain `-layout` is not used: header tokens such as
`Maiden Name Born` collapse into one field under `-layout`, and the tables mix
left-aligned name columns with right-aligned age columns, so character-offset
slicing misparses them. Bounding boxes sidestep both problems by assigning
each word to a column from its own position, not its place in a line of text.

## Adding a source

1. Put the PDF in `pdfs/`.
2. Add an entry to `SOURCES` in `scripts/import_pdfs.py`.
3. Write a parser in `scripts/parsers/` if its columns are new.
4. Rebuild, then regenerate `data/baseline.json` and read the numbers before
   committing them — the baseline is only as good as the first parse, and it
   becomes the standard every future run is measured against.

## Wide tables printed in passes

Two source PDFs print one logical table as several passes over the same page
range, because the underlying spreadsheet was wider than the page: pass one
prints on pages 1..N, pass two reprints the *same rows* starting on page N+1
with different columns. Both parsers find the pass boundary by its header
text (`SECOND_PASS_HEADING` / `DEATH_SECOND_PASS_HEADING`), not a hardcoded
page number, so a differently-paginated reprint doesn't silently misalign.

- **`birth_records.pdf` is fully parsed, in two passes.** Pages 1-27 carry
  `Volume, Birth Day, Child, Family Name, Father`; pages 28-54 carry
  `Mother, Notes` for the same 1,158 rows, in the same order. The two passes
  line up exactly — zero mismatched page pairs — so mothers are recovered by
  *position*: row N of pass two is the mother of row N of pass one. That's
  only safe because it's verified, not assumed: `_paired_mothers` in
  `scripts/parsers/vital.py` asserts the page count and every page pair's row
  count match before trusting the pairing, and raises `ValueError` on any
  mismatch. `import_all` commits per source, so this does not abort the whole
  import — sources already processed before `birth_records.pdf` stay
  committed — it prevents *this* source's mother/child pairings from being
  written wrong. A wrong mother silently attached to the wrong child is worse
  than a missing one, because it fabricates a genealogical fact that looks
  verified.

- **`death_records.pdf` is a *three*-pass table, and only the first pass is
  parsed.** Pages 1-5 are the deaths themselves (what `parse_death` reads);
  pages 6-10 carry `Father | Mother | Spouse` and pages 11-15 carry `Cause`,
  for the same 208 people. These two passes are **deliberately excluded**.
  Unlike the birth table, there's no positional correspondence to lean on:
  the passes hold 208 / 162 / 47 rows — not every death recorded a parent or
  a spouse, and only 47 note a cause, so the rows don't line up 1:1 the way
  birth's two passes do. Pairing by position here would attach parents to
  whichever deceased person happened to share a row index, fabricating
  relationships instead of recovering them. Recovering this data needs a
  real linking key (e.g. matching on name and date against pass one), not a
  row count — left for a future pass.

## Rows that produce no appearance

`scripts/validate.py`'s `reconcile()` compares the number of source table
rows each parser looked at (`rows_in`) against the number of distinct rows
represented in the database (`rows_out`), per source, and prints the delta.
Across the whole corpus this delta is about 33 rows out of roughly 6,900
source rows (0.5%) — rows with no surname to key off, so the parser correctly
produces nothing for them.

The largest single group is `eastcambridge.pdf`'s 19: wrapped epitaph and
inscription continuation lines in the cemetery inventory, which carry no
surname of their own because they belong to a grave already recorded on an
earlier row. No person is lost — the grave's primary row is still in the
index. This reconciliation exists so that a future regression that starts
dropping *hundreds* of rows shows up as a visible spike instead of quietly
passing.

## The word-merge review flag

`review_report()` in `scripts/validate.py` flags any row whose raw source
line contains a token with a lowercase letter directly followed by an
uppercase one (e.g. `AlexanderWilley`) — the pattern `pdftotext` leaves when
it glues two words together with no rendered gap between them. As of this
build it flags 109 rows. Only two are real merge damage (`RusselHawley`,
`FrederickWait`); the rest are ordinary `Mc`/`Mac`/`La`/`Le`/`De` name
prefixes (`McClure`, `LaFountain`, ...) that happen to match the same
lowercase-then-uppercase shape.

The check stays advisory on purpose — it flags for a human to check against
the original document, and never auto-splits. There's no principled way to
tell from the merged token alone where the real word boundary falls
(`AlexanderWilley` could be `Alexander Willey` or `Alex Anderwilley`), so a
best-guess split would risk fabricating a name that reads as clean data.

## Not yet parsed

These six PDFs are not row-per-person tables and need their own handling —
they are out of scope for this phase:

- `taxpayers_1874.pdf` — four side-by-side name pairs per row
- `townmeetings_name_references.pdf` — a page/date matrix, not a person table
- `cattle_earmarks.pdf` — pictorial marks, not text
- `crows_and_foxes.pdf` — unstructured
- `land_records_vol_1_name_index.pdf` — free-form index, not a fixed grid
- `1790_census.pdf` — a statistical table, not one row per person

This phase parses 16 of the 22 record PDFs in `pdfs/`; the other six above,
plus the program flyers and membership forms also in that folder, are
out of scope.
