"""Query construction and validation for the WoS Starter API.

Ground truth (see docs/WOS_API_BASELINE.md):
- The API declares 18 field tags. On ``db=WOS`` the CLI supports 17 of them.
- ``SUR`` is declared but rejected (400) on ``db=WOS`` -> disabled.
- ``WC`` is not supported by the Starter API -> rejected with guidance.
- A bare term query is a 400; plain input must be wrapped in ``TS=(...)``.
- ``sortField`` is ``<field>+<A|D>`` (e.g. ``TC+D``), NOT ``TC DESC``.
"""
from __future__ import annotations

import re

from .errors import WosUsageError

# 18 declared tags (from the API's own 400 message).
DECLARED_TAGS: frozenset[str] = frozenset(
    "AI AU CS DO DOP DT FPY IS OG PG PMID PY SO SUR TI TS UT VL".split()
)
# SUR is declared but returns 400 on db=WOS.
DISABLED_TAGS: frozenset[str] = frozenset({"SUR"})
# Not a Starter field tag at all.
UNSUPPORTED_TAGS: frozenset[str] = frozenset({"WC"})
SUPPORTED_TAGS: frozenset[str] = DECLARED_TAGS - DISABLED_TAGS  # 17 tags

SORT_FIELDS: tuple[str, ...] = ("LD", "PY", "RS", "TC")
SORT_ORDERS: tuple[str, ...] = ("A", "D")

MAX_LIMIT = 50
MIN_LIMIT = 1
DEFAULT_LIMIT = 10
DEFAULT_MAX_PAGES = 10

_TAG_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z]{2,5})\s*=")
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_ISSN_RE = re.compile(r"^\d{4}-\d{3}[\dXx]$")
_ISSN_NODASH_RE = re.compile(r"^\d{7}[\dXx]$")


def build_plain_query(term: str) -> str:
    """Wrap a plain term in the topic tag: ``machine learning`` -> ``TS=(...)``."""
    term = (term or "").strip()
    if not term:
        raise WosUsageError("search query must not be empty")
    return f"TS=({term})"


def build_doi_query(doi: str) -> str:
    doi = (doi or "").strip()
    if not doi:
        raise WosUsageError("DOI must not be empty")
    return f"DO=({doi})"


def looks_like_advanced(query: str) -> bool:
    return bool(_TAG_RE.search(query or ""))


def validate_raw_query(query: str) -> list[str]:
    """Validate a raw advanced query. Returns warnings (never auto-rewrites)."""
    query = (query or "").strip()
    if not query:
        raise WosUsageError("--raw requires a non-empty advanced query")

    tags = {m.group(1).upper() for m in _TAG_RE.finditer(query)}
    bad = tags & UNSUPPORTED_TAGS
    if bad:
        raise WosUsageError(
            f"field tag(s) {', '.join(sorted(bad))} are not supported by the "
            f"Web of Science Starter API. Use TS= (topic) or SO= (source) instead."
        )
    disabled = tags & DISABLED_TAGS
    if disabled:
        raise WosUsageError(
            f"field tag(s) {', '.join(sorted(disabled))} are disabled: SUR only works "
            f"against DRCI, not db=WOS. Supported tags: {' '.join(sorted(SUPPORTED_TAGS))}."
        )
    unknown = tags - DECLARED_TAGS
    if unknown:
        raise WosUsageError(
            f"unknown field tag(s): {', '.join(sorted(unknown))}. "
            f"Supported tags: {' '.join(sorted(SUPPORTED_TAGS))}."
        )
    if not tags:
        warnings = [
            "The advanced query has no recognized field tag; the API requires one "
            "(e.g. TS=, TI=, AU=) and will otherwise return HTTP 400."
        ]
        return warnings
    return []


def build_sort_field(sort: str | None, order: str | None) -> str | None:
    if not sort:
        return None
    sort = sort.upper()
    if sort not in SORT_FIELDS:
        raise WosUsageError(f"invalid --sort {sort!r}; choose from {', '.join(SORT_FIELDS)}")
    order = (order or "D").upper()
    if order not in SORT_ORDERS:
        raise WosUsageError(f"invalid --order {order!r}; choose from A or D")
    return f"{sort}+{order}"


def validate_limit(limit: int) -> int:
    if not (MIN_LIMIT <= limit <= MAX_LIMIT):
        raise WosUsageError(
            f"--limit must be between {MIN_LIMIT} and {MAX_LIMIT} (got {limit}). "
            f"The Starter API rejects values outside this range with a misleading "
            f"'db parameter' error."
        )
    return limit


def looks_like_doi(value: str) -> bool:
    return bool(_DOI_RE.match((value or "").strip()))


def is_issn(value: str) -> bool:
    value = (value or "").strip()
    return bool(_ISSN_RE.match(value) or _ISSN_NODASH_RE.match(value))
