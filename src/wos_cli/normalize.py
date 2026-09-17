"""Normalization of Starter API payloads into a stable, Agent-facing schema.

Ground truth this honors (docs/WOS_API_BASELINE.md §7):
- There is NO ``abstract`` and NO ``keywordsPlus`` field. Never invent them.
- ``identifiers.doi`` may be absent; a record without a DOI is still returned.
- ``keywords.authorKeywords`` may be ``[]``.
- ``source.pages`` is an object ``{range, begin, end, count}``, not a string.
- ``source.publishYear`` is an int; ``types``/``sourceTypes`` are arrays.
- Times Cited lives in ``citations[]``; take the entry whose ``db == "WOS"``.
  Do NOT take ``citations[0]`` and do NOT sum across databases.
"""
from __future__ import annotations

from typing import Any

PAGES_TEMPLATE: dict[str, Any] = {"range": None, "begin": None, "end": None, "count": None}


def _as_list(value: Any) -> list:
    return list(value) if isinstance(value, (list, tuple)) else []


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def times_cited_from_citations(citations: Any) -> int | None:
    """Return the db=="WOS" citation count, else None."""
    for entry in _as_list(citations):
        if isinstance(entry, dict) and str(entry.get("db", "")).upper() == "WOS":
            count = entry.get("count")
            return count if isinstance(count, int) else None
    return None


def _normalize_authors(names: Any) -> list[str]:
    authors: list[str] = []
    for author in _as_list(_as_dict(names).get("authors")):
        if isinstance(author, dict):
            value = author.get("displayName") or author.get("wosStandard")
            if value:
                authors.append(value)
        elif isinstance(author, str):
            authors.append(author)
    return authors


def _normalize_pages(source: dict) -> dict[str, Any]:
    pages = source.get("pages")
    if not isinstance(pages, dict):
        return dict(PAGES_TEMPLATE)
    return {
        "range": pages.get("range"),
        "begin": pages.get("begin"),
        "end": pages.get("end"),
        "count": pages.get("count"),
    }


def normalize_document(hit: Any) -> dict[str, Any]:
    """Normalize one document ``hit`` (or a bare /documents/{uid} object)."""
    hit = _as_dict(hit)
    source = _as_dict(hit.get("source"))
    identifiers = _as_dict(hit.get("identifiers"))
    keywords = _as_dict(hit.get("keywords"))
    links = _as_dict(hit.get("links"))

    return {
        "uid": hit.get("uid"),
        "title": hit.get("title"),
        "authors": _normalize_authors(hit.get("names")),
        "year": source.get("publishYear"),
        "journal": source.get("sourceTitle"),
        "doi": identifiers.get("doi") or None,
        "document_types": _as_list(hit.get("types")),
        "source_types": _as_list(hit.get("sourceTypes")),
        "times_cited": times_cited_from_citations(hit.get("citations")),
        "keywords": _as_list(keywords.get("authorKeywords")),
        "identifiers": dict(identifiers),
        "volume": source.get("volume"),
        "issue": source.get("issue"),
        "pages": _normalize_pages(source),
        "wos_record_url": links.get("record"),
    }


def normalize_journal(journal: Any) -> dict[str, Any]:
    """Normalize a Journal object.

    NOTE: a Journal's ``links`` is a LIST of ``{type, url}``; a Document's
    ``links`` is an OBJECT. Do not share a mapper between them.
    """
    journal = _as_dict(journal)
    links = []
    for link in _as_list(journal.get("links")):
        if isinstance(link, dict):
            links.append({"type": link.get("type"), "url": link.get("url")})
    return {
        "id": journal.get("id"),
        "name": journal.get("name"),
        "jcr_title": journal.get("jcrTitle"),
        "iso_title": journal.get("isoTitle"),
        "issn": journal.get("issn"),
        "eissn": journal.get("eIssn"),
        "previous_issn": _as_list(journal.get("previousIssn")),
        "links": links,
    }


def normalize_metadata(metadata: Any) -> dict[str, Any] | None:
    metadata = _as_dict(metadata)
    if not metadata:
        return None
    return {
        "total": metadata.get("total"),
        "page": metadata.get("page"),
        "limit": metadata.get("limit"),
    }
