# data/

## `archive.sqlite`

A generated binary (3.87 MB), rebuilt by `python -m scripts.import_pdfs` from the PDFs in
`pdfs/` and the parsers in `scripts/`. Nothing in it is hand-authored.

The repo's standing rule is not to commit generated files. This is a deliberate exception:

- **Phase 2 loads it.** The spec's next phase imports this database into D1 for the public
  search UI (`docs/superpowers/specs/2026-09-09-chs-archive-search-design.md`). Committing
  it means Phase 2 has a known-good artifact to start from rather than requiring a full
  16-PDF re-extraction (~15s with the `extract.py` cache, longer without) before any other
  work can begin.
- **It's the reviewable record of what one parse run actually produced.** Per-source counts
  are pinned separately in `baseline.json` for the automated gate, but the database itself
  lets a human open it and look at real rows.

**Rebuilt, not edited.** Re-running `scripts.import_pdfs` is safe and idempotent — it
upserts by `import_key`, so unchanged rows update in place and nothing is duplicated (see
`scripts/README.md`). Never hand-edit `archive.sqlite` directly.

### Open question: volunteer corrections in a binary blob

Starting in Phase 3, volunteers correct rows by hand (`edited_at`/`edited_by`, per the
spec). Once that happens, this file stops being purely reproducible from the PDFs —
it also carries human judgment calls no diff can show. A committed SQLite file has no
readable diff: two commits' worth of hand corrections are invisible in `git log`, `git
diff`, and code review, unlike every other artifact in this repo.

This is **not settled**. Options nobody has chosen between yet:
- Keep committing the binary and accept that corrections are only inspectable by opening
  the file (e.g. `sqlite3 data/archive.sqlite`).
- Export corrected rows to a diffable format (CSV/JSON) alongside the binary, so `git diff`
  shows *what a volunteer changed*, not just that the file changed.
- Stop committing the database once Phase 2's D1 load makes it the system of record
  elsewhere, keeping only `baseline.json` and the PDFs in git.

Whoever picks this up: decide before Phase 3 ships real corrections, not after.

## `baseline.json`

Per-source appearance counts from the last known-good import (16 sources, 9,665 total).
`scripts/validate.py`'s `check_counts` gate compares a fresh import against these; drift
past 2% fails the build. Regenerate it (see `scripts/README.md`'s "Adding a source") only
after reading the new counts, not blindly — it becomes the standard every future run is
measured against.
