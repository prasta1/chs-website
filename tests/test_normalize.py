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


def test_surname_key_pins_the_expected_metaphone_value():
    """Tasks 9's fixtures hard-code "ATT"; pin it so a metaphone version bump
    fails here rather than as a confusing fixture mismatch elsewhere."""
    assert surname_key("Atwood") == "ATT"


def test_import_key_is_stable():
    a = import_key("cloverdale.pdf", 1, "Atwood Ruth 1831-2-11")
    b = import_key("cloverdale.pdf", 1, "Atwood Ruth 1831-2-11")
    assert a == b and len(a) == 40


def test_import_key_varies_with_every_input():
    base = import_key("cloverdale.pdf", 1, "Atwood Ruth")
    assert base != import_key("gates.pdf", 1, "Atwood Ruth")
    assert base != import_key("cloverdale.pdf", 2, "Atwood Ruth")
    assert base != import_key("cloverdale.pdf", 1, "Atwood Ruthe")
