"""Parsers for the three one-person-per-row town record tables.

Each has a volume reference, a date, and a name split across two columns; only
the column names and the event kind differ.
"""
from pathlib import Path

from scripts.extract import extract_words, page_count
from scripts.layout import assign_columns, group_rows, iter_table_pages
from scripts.normalize import import_key, parse_date, surname_key
from scripts.parsers import Appearance

# death_records.pdf prints as three passes over the same pages: death core
# (Volume/Page, First/Last Name, Date, Age), then a Father/Mother/Spouse table
# for the same rows, then a Cause table — the same wide-table-in-passes shape
# birth_records uses (see vital.py), but with no columns this parser wants.
# Found by its own header text rather than a hardcoded page number, so a
# single-pass file just returns None below and the page range is unbounded.
DEATH_SECOND_PASS_HEADING = ["Father", "Mother", "Spouse"]


def _pass1_last_page(pdf_path: Path, second_pass_heading: list[str]) -> int | None:
    """Last page before a later pass's header, or None when there isn't one."""
    for page in range(1, page_count(pdf_path) + 1):
        rows = group_rows(extract_words(pdf_path, page))
        if rows and [w.text for w in rows[0]] == second_pass_heading:
            return page - 1
    return None


def _parse(pdf_path: Path, kind: str, vol_col: str, date_col: str,
           last_col: str, first_col: str, header_contains: str | None = None,
           last_page: int | None = None) -> list[Appearance]:
    """Shared body: one Appearance per row that names somebody."""
    out: list[Appearance] = []
    for page, cols, rows in iter_table_pages(pdf_path, last_page=last_page,
                                             header_contains=header_contains):
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
    """Columns: Volume/Page, First Name, Last Name, Date, Age.

    Bounded to the first pass; see DEATH_SECOND_PASS_HEADING above.
    """
    last = _pass1_last_page(pdf_path, DEATH_SECOND_PASS_HEADING)
    return _parse(pdf_path, "death", "Volume/Page", "Date", "Last Name", "First Name",
                  last_page=last)


def parse_warning(pdf_path: Path) -> list[Appearance]:
    """Columns: Volume, Date of Warning, Last Name, First Name."""
    return _parse(pdf_path, "warning", "Volume", "Date of Warning",
                  "Last Name", "First Name")


def parse_freeman(pdf_path: Path) -> list[Appearance]:
    """Columns: Volume, Date of Oath, First Name, Last Name."""
    return _parse(pdf_path, "freeman", "Volume", "Date of Oath",
                  "Last Name", "First Name", header_contains="Volume")
