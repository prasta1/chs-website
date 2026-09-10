"""Birth and marriage parsers.

Both fan out: a source line naming several people yields one Appearance each,
sharing a pair_key, so a bride is findable under her own surname and a father
under his own name rather than only as a footnote on someone else's row.
"""
from pathlib import Path

from scripts.layout import assign_columns, iter_table_pages
from scripts.normalize import import_key, parse_date, surname_key
from scripts.parsers import Appearance, bounds_for

# birth_records.pdf prints as a wide table in two passes over the same pages:
# pass one carries Volume/Birth Day/Child/Family Name/Father, pass two carries
# Mother/Notes for the same rows in the same order. The pass boundary (see
# scripts/parsers/__init__.py's bounds_for, the single source of truth also
# read by validate.py's reconcile) is found by its own header text rather
# than a hardcoded page number, so a differently-paginated reprint doesn't
# silently misalign.


def _paired_mothers(pdf_path: Path, second_start: int, pass1_pages: list) -> list[tuple[str, str]]:
    """Mother/Notes for every pass-one row, in row order.

    Positional pairing has no shared key with pass one, so a single dropped
    row would silently shift every later mother onto the wrong child — worse
    than a missing mother, since it fabricates a genealogical fact. Verify the
    page count, the page offset, and every page pair's row count line up
    before trusting it.
    """
    pass2_pages = list(iter_table_pages(pdf_path, first_page=second_start))
    if len(pass1_pages) != len(pass2_pages):
        raise ValueError(
            f"{pdf_path.name}: two-pass birth table has {len(pass1_pages)} "
            f"pages in pass one but {len(pass2_pages)} in pass two"
        )
    mothers: list[tuple[str, str]] = []
    for (p1, _, rows1), (p2, cols2, rows2) in zip(pass1_pages, pass2_pages):
        if p2 - p1 != second_start - 1:
            raise ValueError(
                f"{pdf_path.name}: page {p1} pairs with page {p2}, expected "
                f"offset {second_start - 1} -- a blank page in only one pass "
                f"could shift every later pairing undetected"
            )
        if len(rows1) != len(rows2):
            raise ValueError(
                f"{pdf_path.name}: page {p1} has {len(rows1)} rows but its "
                f"second-pass counterpart page {p2} has {len(rows2)} rows"
            )
        for row in rows2:
            v = assign_columns(row, cols2)
            mothers.append((v.get("Mother", "").strip(), v.get("Notes", "").strip()))
    return mothers


def parse_birth(pdf_path: Path) -> list[Appearance]:
    """Columns: Volume, Birth Day, Child, Family Name, Father, Mother, Notes."""
    bounds = bounds_for("birth_records", pdf_path)  # raises if the pass-two
    second_start = bounds["last_page"] + 1           # heading isn't found
    pass1_pages = list(iter_table_pages(pdf_path, **bounds))
    mothers = _paired_mothers(pdf_path, second_start, pass1_pages)

    out: list[Appearance] = []
    idx = 0
    for page, cols, rows in pass1_pages:
        for row in rows:
            v = assign_columns(row, cols)
            surname = v.get("Family Name", "").strip()
            child = v.get("Child", "").strip()
            mother, notes = mothers[idx] if mothers else ("", "")
            idx += 1
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
                volume=vol, detail=notes or None,
            ))
            if father := v.get("Father", "").strip():
                out.append(Appearance(
                    surname=surname, given=father, surname_key=surname_key(surname),
                    kind="birth", role="father", pair_key=key, page=page,
                    raw_line=raw, import_key=f"{key}:father",
                    date_raw=date_raw, date_iso=iso, volume=vol,
                    detail=f"father of {child}",
                ))
            if mother:
                out.append(Appearance(
                    surname=surname, given=mother, surname_key=surname_key(surname),
                    kind="birth", role="mother", pair_key=key, page=page,
                    raw_line=raw, import_key=f"{key}:mother",
                    date_raw=date_raw, date_iso=iso, volume=vol,
                    detail=f"mother of {child}",
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
                    date_raw=date_raw, date_iso=iso, volume=vol, detail=detail,
                ))
    return out
