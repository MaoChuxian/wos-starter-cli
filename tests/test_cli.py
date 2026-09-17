import json

import httpx

from wos_cli import cli
from wos_cli.client import WosClient
from wos_cli.errors import WosBadRequestError


def run(capsys, argv):
    code = cli.main(argv)
    out = capsys.readouterr().out
    return code, json.loads(out)


def patch_client(monkeypatch, mock):
    monkeypatch.setattr(cli, "build_client", lambda **kwargs: mock)


def test_capabilities(monkeypatch, capsys):
    code, env = run(capsys, ["capabilities"])
    assert code == 0
    assert env["ok"] is True
    assert env["schema_version"] == 1
    assert env["source"] == "web_of_science"
    assert len(env["declared_field_tags"]) == 18
    assert len(env["supported_field_tags"]) == 17
    assert env["disabled_field_tags"] == ["SUR"]
    assert env["unsupported_field_tags"] == ["WC"]
    assert env["max_page_size"] == 50
    assert env["supports"]["times_cited"] is True
    assert env["supports"]["abstract"] is False
    assert env["supports"]["pdf"] is False


def test_search_plain_wraps_ts(monkeypatch, capsys, make_client, fx):
    mock = make_client(search=fx("q_ts.json"))
    patch_client(monkeypatch, mock)
    code, env = run(capsys, ["search", "machine learning", "--limit", "2"])
    assert code == 0
    assert env["command"] == "search"
    assert env["query"] == "TS=(machine learning)"
    assert env["metadata"]["total"] == 687304
    assert len(env["records"]) == 2
    assert mock.calls[0]["query"] == "TS=(machine learning)"
    assert mock.calls[0]["sort_field"] is None
    assert "abstract" not in env["records"][0]


def test_search_raw_sends_query_verbatim_with_sort(monkeypatch, capsys, make_client, fx):
    mock = make_client(search=fx("q_combined.json"))
    patch_client(monkeypatch, mock)
    code, env = run(
        capsys,
        ["search", "--raw", "TS=(ITO AND ENZ) AND PY=(2022-2026)", "--sort", "TC", "--order", "D"],
    )
    assert code == 0
    assert env["query"] == "TS=(ITO AND ENZ) AND PY=(2022-2026)"
    assert mock.calls[0]["query"] == "TS=(ITO AND ENZ) AND PY=(2022-2026)"
    # Regression: never "TC DESC".
    assert mock.calls[0]["sort_field"] == "TC+D"


def test_search_wc_rejected(monkeypatch, capsys, make_client, fx):
    patch_client(monkeypatch, make_client(search=fx("q_ts.json")))
    code, env = run(capsys, ["search", "--raw", "TS=(a) AND WC=(b)"])
    assert code == 2
    assert env["ok"] is False
    assert env["error"]["code"] == "usage_error"
    assert "WC" in env["error"]["message"]


def test_search_sur_rejected(monkeypatch, capsys, make_client, fx):
    patch_client(monkeypatch, make_client(search=fx("q_ts.json")))
    code, env = run(capsys, ["search", "--raw", "SUR=(repo)"])
    assert code == 2
    assert "SUR" in env["error"]["message"]


def test_search_limit_out_of_range(monkeypatch, capsys, make_client, fx):
    patch_client(monkeypatch, make_client(search=fx("q_ts.json")))
    code, env = run(capsys, ["search", "machine learning", "--limit", "100"])
    assert code == 2
    assert env["error"]["code"] == "usage_error"


def test_search_plain_and_raw_conflict(monkeypatch, capsys, make_client, fx):
    patch_client(monkeypatch, make_client(search=fx("q_ts.json")))
    code, env = run(capsys, ["search", "x", "--raw", "TS=(y)"])
    assert code == 2
    assert env["error"]["code"] == "usage_error"


def test_search_no_results_warns(monkeypatch, capsys, make_client, fx):
    patch_client(monkeypatch, make_client(search=fx("q_noresult.json")))
    code, env = run(capsys, ["search", "TS=(zzz)"])
    assert code == 0
    assert env["records"] == []
    assert env["metadata"]["total"] == 0
    assert any("no records" in w for w in env["warnings"])


def test_search_all_pages_bounded(monkeypatch, capsys, make_client, fx):
    p1, p2 = fx("limit50_p1.json"), fx("limit50_p2.json")

    def search(**kwargs):
        return p1 if kwargs["page"] == 1 else p2

    mock = make_client(search=search)
    patch_client(monkeypatch, mock)
    code, env = run(capsys, ["search", "TS=(machine learning)", "--limit", "50", "--all-pages", "--max-pages", "2"])
    assert code == 0
    assert env["metadata"]["pages_fetched"] == 2
    assert env["metadata"]["truncated"] is True
    assert len(env["records"]) == 100
    assert len(mock.calls) == 2


def test_doi_lookup(monkeypatch, capsys, make_client, fx):
    patch_client(monkeypatch, make_client(search=fx("doi_plain.json")))
    code, env = run(capsys, ["doi", "10.1016/0031-9384(78)90070-7"])
    assert code == 0
    assert env["command"] == "doi"
    assert env["query"] == "DO=(10.1016/0031-9384(78)90070-7)"
    assert env["match_count"] == 1
    assert env["records"][0]["uid"] == "WOS:A1978EP88400013"


def test_doi_no_match_warns(monkeypatch, capsys, make_client, fx):
    patch_client(monkeypatch, make_client(search=fx("q_noresult.json")))
    code, env = run(capsys, ["doi", "10.9999/nope"])
    assert code == 0
    assert env["match_count"] == 0
    assert any("no WoS record" in w for w in env["warnings"])


def test_get_uid(monkeypatch, capsys, make_client, fx):
    mock = make_client(doc=fx("uid_lookup.json"))
    patch_client(monkeypatch, mock)
    code, env = run(capsys, ["get", "WOS:A1978EP88400013"])
    assert code == 0
    assert env["command"] == "get"
    assert env["metadata"] is None
    assert env["records"][0]["uid"] == "WOS:A1978EP88400013"
    assert env["records"][0]["times_cited"] == 570
    assert mock.calls[0]["uid"] == "WOS:A1978EP88400013"


def test_journal_by_issn(monkeypatch, capsys, make_client, fx):
    mock = make_client(journal_issn=fx("journals_issn.json"))
    patch_client(monkeypatch, mock)
    code, env = run(capsys, ["journal", "0028-0836"])
    assert code == 0
    assert env["records"][0]["id"] == "NATURE-2025"
    assert isinstance(env["records"][0]["links"], list)
    assert mock.calls[0]["issn"] == "0028-0836"


def test_journal_by_id(monkeypatch, capsys, make_client, fx):
    mock = make_client(journal_id=fx("journals_byid.json"))
    patch_client(monkeypatch, mock)
    code, env = run(capsys, ["journal", "NATURE-2025"])
    assert code == 0
    assert env["command"] == "journal"
    assert env["records"][0]["name"] == "NATURE"
    assert mock.calls[0]["journal_id"] == "NATURE-2025"


def test_doctor_missing_key(monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_api_key", lambda: "")
    code, env = run(capsys, ["doctor"])
    assert code == 1
    assert env["ok"] is False
    checks = {c["id"]: c for c in env["checks"]}
    assert checks["config.api_key"]["status"] == "fail"
    assert checks["api.documents"]["status"] == "skip"


def test_doctor_success(monkeypatch, capsys, make_client, fx):
    monkeypatch.setattr(cli, "get_api_key", lambda: "key")
    patch_client(monkeypatch, make_client(search=fx("q_ts.json")))
    code, env = run(capsys, ["doctor"])
    assert code == 0
    assert env["ok"] is True
    assert all(c["status"] == "pass" for c in env["checks"])


def test_smoke(monkeypatch, capsys, make_client, fx):
    monkeypatch.setattr(cli, "get_api_key", lambda: "key")
    mock = make_client(search=fx("connect_limit1.json"))
    patch_client(monkeypatch, mock)
    code, env = run(capsys, ["smoke"])
    assert code == 0
    assert env["http_status"] == 200
    assert env["endpoint_version"] == "v1"
    assert env["metadata"]["total"] == 687304
    assert "elapsed_ms" in env


def test_doctor_api_error_is_structured(monkeypatch, capsys, make_client, fx):
    monkeypatch.setattr(cli, "get_api_key", lambda: "key")

    def boom(**kwargs):
        raise WosBadRequestError("Invalid syntax", status=400, title="Invalid syntax")

    patch_client(monkeypatch, make_client())
    monkeypatch.setattr(cli, "build_client", boom)
    code, env = run(capsys, ["doctor"])
    assert code == 1
    checks = {c["id"]: c for c in env["checks"]}
    assert checks["api.documents"]["status"] == "fail"


def test_api_key_never_leaks_to_output(monkeypatch, capsys):
    secret = "SECRETKEY1234567890"

    def handler(request):
        return httpx.Response(401, json={"error": "invalid_request", "error_description": "bad token"})

    def build(**kwargs):
        return WosClient(secret, transport=httpx.MockTransport(handler), min_interval=0.0, sleeper=lambda _s: None)

    monkeypatch.setattr(cli, "get_api_key", lambda: secret)
    monkeypatch.setattr(cli, "build_client", build)
    code, env = run(capsys, ["smoke"])
    raw = json.dumps(env)
    assert code == 1
    assert secret not in raw
    assert "X-ApiKey" not in raw
