"""Parsers turning positioned table rows into person-appearances."""
from dataclasses import dataclass


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
