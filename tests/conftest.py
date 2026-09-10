import pathlib
import pytest

from scripts.import_pdfs import SOURCES

PDF_DIR = pathlib.Path(__file__).parent.parent / "pdfs"

# stem -> record kind, derived from the same SOURCES dict import_pdfs.py
# uses to build the database, so a new source added there (per
# scripts/README.md's "Adding a source") is never silently excluded from
# the presence/non-empty checks in test_corpus.py. Phase 1 scope only.
RECORD_PDFS = {stem: kind for stem, (_, kind, _) in SOURCES.items()}


@pytest.fixture(scope="session")
def pdf_dir():
    return PDF_DIR
