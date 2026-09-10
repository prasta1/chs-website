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
