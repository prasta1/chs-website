"""Parsers for the three one-person-per-row town record tables.

Each has a volume reference, a date, and a name split across two columns; only
the column names and the event kind differ.
"""
from pathlib import Path

from scripts.layout import assign_columns, find_header_page, iter_table_pages
from scripts.normalize import import_key, parse_date, surname_key
from scripts.parsers import Appearance

# death_records.pdf prints as three passes over the same pages: death core
# (Volume/Page, First/Last Name, Date, Age), then a Father/Mother/Spouse table
# for the same rows, then a Cause table — the same wide-table-in-passes shape
# birth_records uses (see vital.py), but with no columns this parser wants.
# Found by its own header text rather than a hardcoded page number, so a
# single-pass file just returns None below and the page range is unbounded.
DEATH_SECOND_PASS_HEADING = ["Father", "Mother", "Spouse"]


def _parse(pdf_path: Path, kind: str, role: str, vol_col: str, date_col: str,
           last_col: str, first_col: str, header_contains: str | None = None,
           last_page: int | None = None, detail_col: str | None = None,
           ) -> list[Appearance]:
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
                role=role,
                page=page,
                raw_line=raw,
                import_key=import_key(pdf_path.name, page, raw),
                date_raw=date_raw,
                date_iso=parse_date(date_raw or ""),
                volume=v.get(vol_col, "").strip() or None,
                detail=(v.get(detail_col, "").strip() or None) if detail_col else None,
            ))
    return out


def parse_death(pdf_path: Path) -> list[Appearance]:
    """Columns: Volume/Page, First Name, Last Name, Date, Age.

    Bounded to the first pass; see DEATH_SECOND_PASS_HEADING above. Age is
    NOT folded into `detail`: the source table's Age column mis-splits for
    ages spanning years+months+days (the years token falls left of the
    column boundary, into date_raw), so folding it would store a truncated,
    wrong age for some rows. The full age string still survives in
    raw_line -- a missing fact beats a fabricated one.
    """
    start = find_header_page(pdf_path, DEATH_SECOND_PASS_HEADING)
    last = (start - 1) if start else None
    return _parse(pdf_path, "death", "deceased", "Volume/Page", "Date",
                  "Last Name", "First Name", last_page=last)


def parse_warning(pdf_path: Path) -> list[Appearance]:
    """Columns: Volume, Date of Warning, Last Name, First Name."""
    return _parse(pdf_path, "warning", "warned", "Volume", "Date of Warning",
                  "Last Name", "First Name")


def parse_freeman(pdf_path: Path) -> list[Appearance]:
    """Columns: Volume, Date of Oath, First Name, Last Name."""
    return _parse(pdf_path, "freeman", "sworn", "Volume", "Date of Oath",
                  "Last Name", "First Name", header_contains="Volume")
