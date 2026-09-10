"""Birth and marriage parsers.

Both fan out: a source line naming several people yields one Appearance each,
sharing a pair_key, so a bride is findable under her own surname and a father
under his own name rather than only as a footnote on someone else's row.
"""
from pathlib import Path

from scripts.layout import assign_columns, iter_table_pages
from scripts.normalize import import_key, parse_date, surname_key
from scripts.parsers import Appearance


def parse_birth(pdf_path: Path) -> list[Appearance]:
    """Columns: Volume, Birth Day, Child, Family Name, Father."""
    out: list[Appearance] = []
    for page, cols, rows in iter_table_pages(pdf_path):
        for row in rows:
            v = assign_columns(row, cols)
            surname = v.get("Family Name", "").strip()
            child = v.get("Child", "").strip()
            if not surname or not child:
                continue
            raw = " ".join(w.text for w in row)
            key = import_key(pdf_path.name, page, raw)
            date_raw = v.get("Birth Day", "").strip() or None
            iso = parse_date(date_raw or "")
            vol = v.get("Volume", "").strip() or None

            out.append(Appearance(
                surname=surname, given=child, surname_key=surname_key(surname),
                kind="birth", role="child", pair_key=key, page=page,
                raw_line=raw, import_key=key, date_raw=date_raw, date_iso=iso,
                place=vol, detail=None,
            ))
            if father := v.get("Father", "").strip():
                out.append(Appearance(
                    surname=surname, given=father, surname_key=surname_key(surname),
                    kind="birth", role="father", pair_key=key, page=page,
                    raw_line=raw, import_key=f"{key}:father",
                    date_raw=date_raw, date_iso=iso, place=vol,
                    detail=f"father of {child}",
                ))
    return out


def parse_marriage(pdf_path: Path) -> list[Appearance]:
    """Columns: Volume, Marriage Date, Groom First/Last, Bride First/Last, Notes."""
    out: list[Appearance] = []
    for page, cols, rows in iter_table_pages(pdf_path):
        for row in rows:
            v = assign_columns(row, cols)
            g_last = v.get("Groom Last", "").strip()
            b_last = v.get("Bride Last", "").strip()
            if not g_last and not b_last:
                continue
            raw = " ".join(w.text for w in row)
            key = import_key(pdf_path.name, page, raw)
            date_raw = v.get("Marriage Date", "").strip() or None
            iso = parse_date(date_raw or "")
            vol = v.get("Volume", "").strip() or None
            note = v.get("Notes", "").strip() or None
            g_first = v.get("Groom First", "").strip() or None
            b_first = v.get("Bride First", "").strip() or None

            for last, first, role, other in (
                (g_last, g_first, "groom", f"{b_first or ''} {b_last}".strip()),
                (b_last, b_first, "bride", f"{g_first or ''} {g_last}".strip()),
            ):
                if not last:
                    continue
                detail = f"married {other}" if other else None
                if note:
                    detail = f"{detail} · {note}" if detail else note
                out.append(Appearance(
                    surname=last, given=first, surname_key=surname_key(last),
                    kind="marriage", role=role, pair_key=key, page=page,
                    raw_line=raw, import_key=f"{key}:{role}",
                    date_raw=date_raw, date_iso=iso, place=vol, detail=detail,
                ))
    return out
