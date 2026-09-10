from conftest import PDF_DIR
from scripts import extract
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


def test_extract_words_and_page_count_are_cached(monkeypatch):
    """The same page gets re-extracted multiple times per pipeline run (a
    parser's own bound-finding prescan then its real read, import then
    validate's reconcile recounting the same pages, the test suite calling
    the same parser repeatedly) purely to recount rows -- a cache must
    avoid re-invoking pdftotext/pdfinfo for an already-seen (path, page)."""
    extract_words.cache_clear()
    page_count.cache_clear()
    calls = []
    real_run = extract.subprocess.run

    def counting_run(cmd, *a, **kw):
        calls.append(cmd[0])
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(extract.subprocess, "run", counting_run)

    extract_words(PDF_DIR / "cloverdale.pdf", 1)
    extract_words(PDF_DIR / "cloverdale.pdf", 1)
    assert calls.count("pdftotext") == 1, "second call must hit the cache, not pdftotext"

    page_count(PDF_DIR / "cloverdale.pdf")
    page_count(PDF_DIR / "cloverdale.pdf")
    assert calls.count("pdfinfo") == 1, "second call must hit the cache, not pdfinfo"
