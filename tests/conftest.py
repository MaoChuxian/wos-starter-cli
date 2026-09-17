import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    """Load a captured real API response (see bench/raw)."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class MockClient:
    """In-memory stand-in for WosClient used by CLI tests."""

    def __init__(self, *, search=None, doc=None, journal_issn=None, journal_id=None):
        self._search = search
        self._doc = doc
        self._journal_issn = journal_issn
        self._journal_id = journal_id
        self.calls = []
        self.last_status = 200
        self.last_elapsed_ms = 1

    def search(self, query, *, db="WOS", limit=10, page=1, sort_field=None):
        self.calls.append(
            {"query": query, "db": db, "limit": limit, "page": page, "sort_field": sort_field}
        )
        if callable(self._search):
            return self._search(query=query, limit=limit, page=page, sort_field=sort_field)
        return self._search

    def get_document(self, uid):
        self.calls.append({"uid": uid})
        return self._doc

    def get_journal_by_issn(self, issn):
        self.calls.append({"issn": issn})
        return self._journal_issn

    def get_journal_by_id(self, journal_id):
        self.calls.append({"journal_id": journal_id})
        return self._journal_id

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fx():
    return load


@pytest.fixture
def make_client():
    return MockClient
