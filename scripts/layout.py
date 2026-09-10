"""Turn positioned words into table rows and columns.

Rows come from clustering words by vertical position. Columns come from the
header row: adjacent header words separated by a small gap belong to one
heading ("Maiden" + "Name"), a larger gap starts a new column. Each column
then owns the horizontal span from its own start to the next column's start,
so values wider than their heading — right-aligned ages, long spouse names —
still land in the right place.
"""
import math
from pathlib import Path
from typing import NamedTuple

from scripts.extract import Word, extract_words, page_count


class Column(NamedTuple):
    """A table column and the horizontal span it owns."""
    name: str
    x0: float
    x1: float


def group_rows(words: list[Word], tol: float = 3.0) -> list[list[Word]]:
    """Cluster words into rows by vertical midpoint, ordered top to bottom.

    `tol` is the vertical distance in points within which two words count as
    being on the same line.
    """
    rows: list[list[Word]] = []
    for w in sorted(words, key=lambda w: (w.y0, w.x0)):
        mid = (w.y0 + w.y1) / 2
        for row in rows:
            ref = row[0]
            if abs(mid - (ref.y0 + ref.y1) / 2) <= tol:
                row.append(w)
                break
        else:
            rows.append([w])
    for row in rows:
        row.sort(key=lambda w: w.x0)
    return rows


def _intra_heading_threshold(gaps: list[float], jump: float = 1.5) -> float:
    """Separate intra-heading spacing from inter-column spacing.

    Header gaps are bimodal: a few tight gaps inside compound headings like
    "Maiden Name", then a clear jump to the spacing between columns. These files
    use different letter-tracking, so the absolute values differ per file while
    the ratio at the boundary does not. The first sorted-gap ratio jump of
    `jump` or more marks that boundary; the threshold sits at the geometric mean
    of the pair.

    Measured across all sixteen record tables, that boundary ratio runs from
    1.82 (marriages) to 9.48 (Gates); `jump=1.5` sits under the tightest real
    boundary with margin, while still catching every genuine jump. Returns 0.0
    when no gap ratio reaches `jump` — usually a header with no compound
    headings, where every gap already separates columns, but the same 0.0 also
    results if a table's real boundary ratio happens to fall under `jump`,
    which would silently join every header word into one column. When a table
    defeats this heuristic, pass `gap` to `detect_columns` explicitly instead
    of lowering `jump` further.
    """
    ordered = sorted(g for g in gaps if g > 0)
    for a, b in zip(ordered, ordered[1:]):
        if b / a >= jump:
            return math.sqrt(a * b)
    return 0.0


def detect_columns(header: list[Word], gap: float | None = None) -> list[Column]:
    """Derive columns from a header row.

    Header words closer together than the intra-heading threshold are joined
    into one heading. The threshold adapts to the file's own spacing unless
    `gap` is given explicitly. Each column spans from its first word's left
    edge to the next column's left edge; the last column extends to infinity.
    """
    if not header:
        return []
    gaps = [b.x0 - a.x1 for a, b in zip(header, header[1:])]
    threshold = gap if gap is not None else _intra_heading_threshold(gaps)

    groups: list[list[Word]] = [[header[0]]]
    for prev, cur in zip(header, header[1:]):
        if cur.x0 - prev.x1 <= threshold:
            groups[-1].append(cur)
        else:
            groups.append([cur])

    cols = []
    seen: dict[str, int] = {}
    for i, group in enumerate(groups):
        name = " ".join(w.text for w in group)
        # A genuinely duplicated heading (two spans sharing one name) must not
        # collapse in assign_columns's name-keyed dict -- that would silently
        # merge the spans and drop whichever value loses the collision. Real
        # headers never repeat a name, so this is a no-op for them.
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            name = f"{name} ({seen[name]})"
        x0 = group[0].x0
        x1 = groups[i + 1][0].x0 if i + 1 < len(groups) else float("inf")
        cols.append(Column(name=name, x0=x0, x1=x1))
    return cols


def assign_columns(row: list[Word], cols: list[Column]) -> dict[str, str]:
    """Map a row's words onto column headings by horizontal position.

    A word belongs to the column whose span contains its midpoint; words left of
    every column fall into the first one.
    """
    out: dict[str, list[str]] = {c.name: [] for c in cols}
    for w in row:
        mid = (w.x0 + w.x1) / 2
        target = cols[0]
        for c in cols:
            if c.x0 <= mid < c.x1:
                target = c
                break
        out[target.name].append(w.text)
    return {name: " ".join(parts) for name, parts in out.items()}


def iter_table_pages(pdf_path: Path, first_page: int = 1, last_page: int | None = None,
                     header_contains: str | None = None, gap: float | None = None):
    """Yield (page, columns, data_rows) for a table PDF.

    Columns are read from the header row on the first page that has one and
    reused for later pages, which carry data rows only. `first_page`/`last_page`
    restrict the range — a wide table is sometimes printed as two passes over the
    document, each pass carrying a different set of columns and its own header.
    `header_contains` names a word the header is known to carry, so leading
    title rows are skipped rather than mistaken for the header — some of these
    tables print a caption line above their column names. `gap` is forwarded
    to `detect_columns` as an explicit intra-heading threshold, overriding the
    per-file derived one, for the rare table that defeats the heuristic.

    Most of these tables reprint their column header on every page, not just
    the first. A repeated header is not a record, so any row whose word texts
    exactly match the detected header row is dropped, on whichever page it
    turns up.
    """
    end = page_count(pdf_path) if last_page is None else last_page
    cols = None
    header_texts = None
    for page in range(first_page, end + 1):
        rows = group_rows(extract_words(pdf_path, page))
        if not rows:
            continue
        start = 0
        if cols is None:
            header_idx = 0
            if header_contains is not None:
                header_idx = next(
                    (i for i, row in enumerate(rows)
                     if any(w.text == header_contains for w in row)),
                    None,
                )
                if header_idx is None:
                    raise ValueError(
                        f"{pdf_path.name} page {page}: no row contains the header "
                        f"word {header_contains!r}"
                    )
            cols = detect_columns(rows[header_idx], gap=gap)
            header_texts = tuple(w.text for w in rows[header_idx])
            start = header_idx + 1
        data_rows = [r for r in rows[start:]
                     if tuple(w.text for w in r) != header_texts]
        yield page, cols, data_rows


def find_header_page(pdf_path: Path, heading: list[str]) -> int | None:
    """Page whose first row of words matches `heading` exactly, or None.

    Used to locate a later pass's header in a wide table printed across
    several passes over the same page range (see vital.py and simple.py),
    so the split point is found by content rather than a hardcoded page
    number that would silently drift if the document were repaginated.
    """
    for page in range(1, page_count(pdf_path) + 1):
        rows = group_rows(extract_words(pdf_path, page))
        if rows and [w.text for w in rows[0]] == heading:
            return page
    return None
