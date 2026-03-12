"""Boilerplate removal: headers, footers, TOC, copyright, nav artifacts."""

import re
from typing import List

_COPYRIGHT_PATTERNS = [
    r"\b(copyright\s*©?\s*\d{4})\b",
    r"\b(all rights reserved\.?)\b",
    r"\b(©\s*\d{4})\b",
    r"\blegal notice\b",
    r"\bconfidential\b",
    r"\bproprietary\b",
]

_NAV_PATTERNS = [
    r"^\s*(previous|next|back|home|top)\s*$",
    r"^\s*page\s+\d+\s+of\s+\d+\s*$",
    r"^\s*\d+\s*$",
    r"^\s*-\s*\d+\s*-\s*$",
    r"^\s*\.{2,}\s*\d+\s*$",
]

_TOC_LINE = re.compile(
    r"^(\.{2,}|\s+)\d+\s*$|" r"^[\w\s]+\s+\.{2,}\s+\d+\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _is_repeated_line(line: str, line_counts: dict[str, int]) -> bool:
    key = line.strip().lower()
    if len(key) < 10:
        return False
    return line_counts.get(key, 0) > 2


def remove_boilerplate(text: str) -> str:
    """Remove boilerplate: headers, footers, copyright, TOC, nav. Returns cleaned text."""
    if not text or not text.strip():
        return text
    lines = text.split("\n")
    line_counts: dict[str, int] = {}
    for ln in lines:
        k = ln.strip().lower()
        if k:
            line_counts[k] = line_counts.get(k, 0) + 1
    cleaned: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append(line)
            continue
        if any(re.search(p, stripped, re.I) for p in _COPYRIGHT_PATTERNS):
            continue
        if any(re.match(p, stripped, re.I) for p in _NAV_PATTERNS):
            continue
        if _TOC_LINE.match(stripped):
            continue
        if _is_repeated_line(line, line_counts):
            continue
        cleaned.append(line)
    result = "\n".join(cleaned)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()
