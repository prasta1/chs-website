"""Word-level PDF text extraction with coordinates.

Uses `pdftotext -bbox-layout`, which emits XHTML with a bounding box per word.
Coordinates are what make column assignment reliable: the record tables mix
left-aligned name columns with right-aligned age columns, so character-offset
slicing of `-layout` output misparses them.
"""
import subprocess
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

XHTML = "{http://www.w3.org/1999/xhtml}"


class Word(NamedTuple):
    """A single word and its bounding box in PDF points."""
    text: str
    x0: float
    x1: float
    y0: float
    y1: float


@lru_cache(maxsize=None)
def page_count(pdf_path: Path) -> int:
    """Return the number of pages in the PDF."""
    out = subprocess.run(
        ["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=True
    ).stdout
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    raise ValueError(f"no page count in pdfinfo output for {pdf_path}")


@lru_cache(maxsize=None)
def extract_words(pdf_path: Path, page: int) -> list[Word]:
    """Extract every word on one 1-indexed page, with coordinates.

    Returns words in document order. Raises CalledProcessError if pdftotext fails.

    Cached: the same page gets re-extracted multiple times per pipeline run
    (a parser's own bound-finding prescan, then its real read; import then
    validate's reconcile recounting the same pages; the test suite calling
    the same parser repeatedly). Safe to cache because nothing mutates the
    returned list -- Word is an immutable NamedTuple, and every caller
    (group_rows via sorted(), and the tests) only reads it or builds new
    lists from it.
    """
    xml = subprocess.run(
        ["pdftotext", "-q", "-bbox-layout", "-f", str(page), "-l", str(page),
         str(pdf_path), "-"],
        capture_output=True, text=True, check=True,
    ).stdout
    root = ET.fromstring(xml)
    words = []
    for el in root.iter(f"{XHTML}word"):
        text = (el.text or "").strip()
        if not text:
            continue
        words.append(Word(
            text=text,
            x0=float(el.get("xMin")), x1=float(el.get("xMax")),
            y0=float(el.get("yMin")), y1=float(el.get("yMax")),
        ))
    return words
