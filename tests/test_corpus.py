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
