"""Normalisers shared by every parser."""
import calendar
import hashlib
import re

from metaphone import doublemetaphone

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}

_DMY = re.compile(r"^(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})$")
_MY = re.compile(r"^([A-Za-z]{3,})\s+(\d{4})$")
_ISOISH = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_YEAR = re.compile(r"^(\d{4})$")


def _valid(year: int, month: int, day: int) -> bool:
    return 1 <= month <= 12 and 1 <= day <= calendar.monthrange(year, month)[1]


def parse_date(raw: str) -> str | None:
    """Normalise a source date to ISO, keeping whatever precision exists.

    Returns 'YYYY-MM-DD', 'YYYY-MM', 'YYYY', or None when unparseable. Partial
    dates are common in these records and must not be discarded or guessed at.
    """
    s = (raw or "").strip()
    if not s:
        return None

    if m := _DMY.match(s):
        day, mon, year = int(m[1]), MONTHS.get(m[2][:3].lower()), int(m[3])
        if mon and _valid(year, mon, day):
            return f"{year:04d}-{mon:02d}-{day:02d}"
        return None

    if m := _ISOISH.match(s):
        year, mon, day = int(m[1]), int(m[2]), int(m[3])
        if _valid(year, mon, day):
            return f"{year:04d}-{mon:02d}-{day:02d}"
        return None

    if m := _MY.match(s):
        mon = MONTHS.get(m[1][:3].lower())
        if mon:
            return f"{int(m[2]):04d}-{mon:02d}"
        return None

    if m := _YEAR.match(s):
        return m[1]

    return None


def surname_key(surname: str) -> str:
    """Phonetic key so Atwood, Attwood and Atwoode match one another.

    Computed at import time and stored in an indexed column, so search behaves
    identically wherever it runs.
    """
    s = (surname or "").strip()
    if not s:
        return ""
    return doublemetaphone(s)[0]


def import_key(filename: str, page: int, raw_line: str) -> str:
    """Stable fingerprint for 'this row came from that line'.

    Lets re-import update untouched rows in place while leaving hand-corrected
    rows alone.
    """
    payload = f"{filename}\x00{page}\x00{raw_line}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()
