import httpx
import pytest

from wos_cli.client import WosClient
from wos_cli.errors import (
    WosAuthError,
    WosBadRequestError,
    WosConfigError,
    WosNetworkError,
    WosNotFoundError,
    WosRateLimitError,
    WosServerError,
)

KEY = "SECRET-KEY-DO-NOT-LEAK"


def make_client(handler, **kwargs):
    transport = httpx.MockTransport(handler)
    return WosClient(
        KEY,
        transport=transport,
        min_interval=0.0,
        sleeper=lambda _s: None,
        max_retries=kwargs.pop("max_retries", 2),
        **kwargs,
    )


def test_missing_key_raises_config_error():
    with pytest.raises(WosConfigError):
        WosClient("")


def test_search_params_and_doi_encoding():
    seen = {}

    def handler(request: httpx.Request):
        seen["params"] = request.url.params
        seen["raw"] = request.url.query.decode()
        return httpx.Response(200, json={"metadata": {"total": 1}, "hits": []})

    client = make_client(handler)
    client.search("DO=(10.1016/0031-9384(78)90070-7)", limit=1, page=1, sort_field="TC+D")

    assert seen["params"]["q"] == "DO=(10.1016/0031-9384(78)90070-7)"
    assert seen["params"]["db"] == "WOS"
    assert seen["params"]["limit"] == "1"
    assert seen["params"]["sortField"] == "TC+D"
    # Encoding happened exactly once (no double encoding).
    assert "%2F" in seen["raw"]
    assert "%252F" not in seen["raw"]


def test_search_omits_none_params():
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"metadata": {}, "hits": []})

    make_client(handler).search("TS=(x)")
    assert "sortField" not in seen["params"]


def test_get_document_path():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        return httpx.Response(200, json={"uid": "WOS:A1978EP88400013"})

    client = make_client(handler)
    client.get_document("WOS:A1978EP88400013")
    assert seen["path"].endswith("/documents/WOS:A1978EP88400013")


def test_get_journal_by_issn_uses_params():
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"metadata": {}, "hits": []})

    make_client(handler).get_journal_by_issn("0028-0836")
    assert seen["params"]["issn"] == "0028-0836"


def test_bad_request_json_error():
    def handler(request):
        return httpx.Response(
            400,
            json={
                "error": {
                    "status": 400,
                    "title": "Invalid syntax for the request",
                    "details": "MISS_TAGEQ",
                }
            },
        )

    with pytest.raises(WosBadRequestError) as exc:
        make_client(handler).search("machine learning")
    assert exc.value.status == 400
    assert exc.value.title == "Invalid syntax for the request"
    assert exc.value.details == "MISS_TAGEQ"
    assert KEY not in str(exc.value)
    assert "X-ApiKey" not in exc.value.to_dict().values()


def test_unauthorized_schema():
    def handler(request):
        return httpx.Response(
            401, json={"error": "invalid_request", "error_description": "The access token is missing"}
        )

    with pytest.raises(WosAuthError) as exc:
        make_client(handler).search("TS=(x)")
    assert exc.value.details == "The access token is missing"


def test_not_found():
    def handler(request):
        return httpx.Response(404, json={"error": {"status": 404, "title": "Resource couldn't be found"}})

    with pytest.raises(WosNotFoundError):
        make_client(handler).get_document("WOS:NOTAREAL")


def test_html_gateway_error_is_structured():
    def handler(request):
        return httpx.Response(400, text="<!doctype html><html><h1>HTTP Status 400</h1></html>",
                              headers={"content-type": "text/html"})

    with pytest.raises(WosBadRequestError) as exc:
        make_client(handler).search('DO=("x(y)")')
    assert "HTML" in exc.value.title


def test_429_is_retried_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {"status": 429}})
        return httpx.Response(200, json={"metadata": {"total": 2}, "hits": []})

    client = make_client(handler)
    data = client.search("TS=(x)")
    assert calls["n"] == 2
    assert data["metadata"]["total"] == 2


def test_rate_limit_exhausted_raises():
    def handler(request):
        return httpx.Response(429, json={"error": {"status": 429, "title": "too many"}})

    with pytest.raises(WosRateLimitError):
        make_client(handler, max_retries=1).search("TS=(x)")


def test_5xx_is_retried_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="boom")
        return httpx.Response(200, json={"metadata": {"total": 1}, "hits": []})

    client = make_client(handler, max_retries=3)
    assert client.search("TS=(x)")["metadata"]["total"] == 1
    assert calls["n"] == 3


def test_5xx_exhausted_raises_server_error():
    def handler(request):
        return httpx.Response(500, text="boom")

    with pytest.raises(WosServerError):
        make_client(handler, max_retries=1).search("TS=(x)")


def test_timeout_raises_network_error():
    def handler(request):
        raise httpx.ConnectTimeout("timeout")

    with pytest.raises(WosNetworkError):
        make_client(handler, max_retries=1).search("TS=(x)")


def test_last_status_recorded():
    def handler(request):
        return httpx.Response(200, json={"metadata": {}, "hits": []})

    client = make_client(handler)
    client.search("TS=(x)")
    assert client.last_status == 200
    assert isinstance(client.last_elapsed_ms, int)


def test_key_never_in_client_repr():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    client = WosClient(KEY, transport=transport, min_interval=0.0, sleeper=lambda _s: None)
    assert KEY not in repr(client)
    assert KEY not in str(client)
