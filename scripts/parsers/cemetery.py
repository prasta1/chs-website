"""Parser for the eleven mapped-cemetery inventories.

Columns: Last Name, First Name, Maiden Name, Born, Died, Age, Spouse, Mother,
Father, Notes. Not every file carries every trailing column.
"""
from pathlib import Path

from scripts.layout import assign_columns, iter_table_pages
from scripts.normalize import import_key, parse_date, surname_key
from scripts.parsers import Appearance


def _detail(vals: dict[str, str]) -> str | None:
    """Fold the relationship and note columns into one human-readable string."""
    bits = []
    for label, col in (("age", "Age"), ("spouse", "Spouse"),
                       ("mother", "Mother"), ("father", "Father"),
                       ("maiden", "Maiden Name"), ("note", "Notes")):
        if v := vals.get(col, "").strip():
            bits.append(f"{label} {v}" if label != "note" else v)
    return " · ".join(bits) or None


def parse_cemetery(pdf_path: Path, title: str) -> list[Appearance]:
    """Extract burials from one cemetery PDF."""
    out: list[Appearance] = []
    for page, cols, rows in iter_table_pages(pdf_path):
        for row in rows:
            vals = assign_columns(row, cols)
            surname = vals.get("Last Name", "").strip()
            given = vals.get("First Name", "").strip() or None
            if not surname:
                continue
            raw_line = " ".join(w.text for w in row)
            died = vals.get("Died", "").strip()
            born = vals.get("Born", "").strip()
            date_raw = died or born or None
            detail = _detail(vals)
            if born and died:
                detail = f"born {born}" + (f" · {detail}" if detail else "")
            out.append(Appearance(
                surname=surname,
                given=given,
                surname_key=surname_key(surname),
                kind="burial",
                role="deceased",
                page=page,
                raw_line=raw_line,
                import_key=import_key(pdf_path.name, page, raw_line),
                date_raw=date_raw,
                date_iso=parse_date(date_raw or ""),
                place=title,
                detail=detail,
            ))
    return out
