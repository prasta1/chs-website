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
    for i, group in enumerate(groups):
        name = " ".join(w.text for w in group)
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


def iter_table_pages(pdf_path: Path):
    """Yield (page, columns, data_rows) for a table PDF.

    Columns are read from the header row on the first page that has one and
    reused for later pages, which carry data rows only.
    """
    cols = None
    for page in range(1, page_count(pdf_path) + 1):
        rows = group_rows(extract_words(pdf_path, page))
        if not rows:
            continue
        start = 0
        if cols is None:
            cols = detect_columns(rows[0])
            start = 1
        yield page, cols, rows[start:]
