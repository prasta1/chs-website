"""Parsers turning positioned table rows into person-appearances."""
from dataclasses import dataclass
from pathlib import Path

from scripts.layout import find_header_page

# Headings that mark a later pass's header, for the two wide tables printed
# in passes over the same page range (see vital.py / simple.py). Single
# source of truth for both the real parsers and validate.py's reconcile --
# duplicating this per module risks rows_in counting a different page set
# than the parser actually read.
SECOND_PASS_HEADINGS: dict[str, list[str]] = {
    "birth_records": ["Mother", "Notes"],
    "death_records": ["Father", "Mother", "Spouse"],
}


def bounds_for(stem: str, pdf_path: Path) -> dict:
    """The iter_table_pages kwargs the real parser for `stem` uses.

    Raises ValueError if a known multi-pass source's second-pass header
    can't be found -- falling through to an unbounded range would parse
    that pass with the first pass's columns and manufacture fake rows.
    """
    if stem in SECOND_PASS_HEADINGS:
        heading = SECOND_PASS_HEADINGS[stem]
        start = find_header_page(pdf_path, heading)
        if start is None:
            raise ValueError(
                f"{pdf_path.name}: expected second-pass heading {heading} "
                "not found"
            )
        return {"last_page": start - 1}
    if stem == "freemansworn_records":
        return {"header_contains": "Volume"}
    return {}


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
    volume: str | None = None
    detail: str | None = None
