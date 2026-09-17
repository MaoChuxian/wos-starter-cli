from wos_cli import normalize


def test_times_cited_picks_wos_entry_not_first():
    citations = [{"db": "MEDLINE", "count": 999}, {"db": "WOS", "count": 17}]
    assert normalize.times_cited_from_citations(citations) == 17


def test_times_cited_none_without_wos():
    assert normalize.times_cited_from_citations([{"db": "MEDLINE", "count": 5}]) is None
    assert normalize.times_cited_from_citations([]) is None
    assert normalize.times_cited_from_citations(None) is None


def test_times_cited_does_not_sum():
    citations = [{"db": "WOS", "count": 3}, {"db": "WOS", "count": 4}]
    assert normalize.times_cited_from_citations(citations) == 3


def test_normalize_document_from_real_search(fx):
    data = fx("q_ts.json")
    record = normalize.normalize_document(data["hits"][0])
    assert record["uid"] == "WOS:A1978EP88400013"
    assert record["year"] == 1978 and isinstance(record["year"], int)
    assert record["journal"] == "PHYSIOLOGY & BEHAVIOR"
    assert record["doi"] == "10.1016/0031-9384(78)90070-7"
    assert record["times_cited"] == 570
    assert record["authors"][0] == "DOTY, RL"
    assert record["document_types"] == ["Article"]
    assert record["pages"] == {"range": "175-185", "begin": "175", "end": "185", "count": 11}
    assert record["wos_record_url"].startswith("https://www.webofscience.com/")


def test_pages_is_always_an_object(fx):
    data = fx("detail_short.json")
    record = normalize.normalize_document(data["hits"][0])
    # Regression: never treat pages as a string.
    assert isinstance(record["pages"], dict)
    assert set(record["pages"]) == {"range", "begin", "end", "count"}


def test_no_abstract_or_keywords_plus_invented(fx):
    data = fx("q_ts.json")
    record = normalize.normalize_document(data["hits"][0])
    # Regression: Starter has no abstract and no keywordsPlus.
    assert "abstract" not in record
    assert "keywords_plus" not in record
    assert "keywordsPlus" not in record


def test_keywords_empty_is_allowed(fx):
    data = fx("q_ts.json")
    record = normalize.normalize_document(data["hits"][0])
    assert record["keywords"] == []


def test_record_without_doi_is_kept(fx):
    data = fx("limit50_p1.json")
    hits = data["hits"]
    no_doi = [h for h in hits if not (h.get("identifiers") or {}).get("doi")]
    assert no_doi, "fixture should contain a DOI-less record"
    record = normalize.normalize_document(no_doi[0])
    assert record["doi"] is None
    assert record["uid"]  # still present, not dropped


def test_detail_short_record_survives_missing_fields(fx):
    data = fx("detail_short.json")
    record = normalize.normalize_document(data["hits"][0])
    # detail=short strips title/types/source/names; normalization must not crash.
    assert record["uid"]
    assert record["title"] is None
    assert record["authors"] == []
    assert record["pages"] == {"range": None, "begin": None, "end": None, "count": None}


def test_normalize_bare_document_object(fx):
    data = fx("uid_lookup.json")
    record = normalize.normalize_document(data)
    assert record["uid"] == "WOS:A1978EP88400013"
    assert record["times_cited"] == 570


def test_normalize_journal_links_is_list(fx):
    data = fx("journals_issn.json")
    journal = normalize.normalize_journal(data["hits"][0])
    assert journal["id"] == "NATURE-2025"
    assert journal["issn"] == "0028-0836"
    assert journal["eissn"] == "1476-4687"
    assert isinstance(journal["links"], list)
    assert journal["links"][0] == {
        "type": "Journal Citation Report record",
        "url": journal["links"][0]["url"],
    }


def test_normalize_metadata():
    assert normalize.normalize_metadata({"total": 5, "page": 1, "limit": 10}) == {
        "total": 5,
        "page": 1,
        "limit": 10,
    }
    assert normalize.normalize_metadata(None) is None
    assert normalize.normalize_metadata({}) is None
