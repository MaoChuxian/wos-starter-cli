"""Minimal httpx client for the 4 documented Starter endpoints.

URL encoding: all query parameters are passed via ``params=`` so httpx performs
encoding. Never build a query string by hand -- an unencoded DOI (which contains
``/``, parentheses, quotes) is rejected by the gateway with an HTML 400.
"""
from __future__ import annotations

import os
import time
import urllib.parse
from typing import Any, Callable

import httpx

from . import __version__
from .errors import (
    WosConfigError,
    WosNetworkError,
    WosResponseError,
    error_from_response,
)

RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})
DEFAULT_BASE_URL = "https://api.clarivate.com/apis/wos-starter"
USER_AGENT = f"wos-cli/{__version__} (+https://github.com/MaoChuxian/wos-starter-cli)"


def _require_object(data: Any, what: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise WosResponseError(f"{what}: expected a JSON object, got {type(data).__name__}")
    return data


def _validate_documents_list(data: Any) -> dict[str, Any]:
    data = _require_object(data, "documents search")
    if not isinstance(data.get("metadata"), dict):
        raise WosResponseError("documents search: 'metadata' is missing or not an object")
    if not isinstance(data.get("hits"), list):
        raise WosResponseError("documents search: 'hits' is missing or not a list")
    return data


def _validate_document(data: Any) -> dict[str, Any]:
    data = _require_object(data, "document lookup")
    if not data.get("uid"):
        raise WosResponseError("document lookup: 'uid' is missing")
    return data


def _validate_journals_list(data: Any) -> dict[str, Any]:
    data = _require_object(data, "journals search")
    if not isinstance(data.get("metadata"), dict):
        raise WosResponseError("journals search: 'metadata' is missing or not an object")
    if not isinstance(data.get("hits"), list):
        raise WosResponseError("journals search: 'hits' is missing or not a list")
    return data


def _validate_journal(data: Any) -> dict[str, Any]:
    data = _require_object(data, "journal lookup")
    if not (data.get("id") or data.get("name")):
        raise WosResponseError("journal lookup: neither 'id' nor 'name' is present")
    return data


def get_api_key() -> str:
    """Read the API key from the environment only. Never logged."""
    return (os.environ.get("WOS_API_KEY") or "").strip()


class WosClient:
    def __init__(
        self,
        api_key: str,
        *,
        version: str = "v1",
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        min_interval: float = 0.5,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise WosConfigError("WOS_API_KEY is not set")
        self.version = version
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/") + f"/{version}/"
        self.max_retries = max_retries
        self.min_interval = min_interval
        self._sleep = sleeper
        self._last_request = 0.0
        self.last_status: int | None = None
        self.last_elapsed_ms: int | None = None
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={
                "X-ApiKey": api_key,
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            timeout=httpx.Timeout(timeout),
            transport=transport,
        )

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "WosClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- internals ---------------------------------------------------------
    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            self._sleep(wait)

    def _sleep_backoff(self, attempt: int, retry_after: str | None) -> None:
        delay = min(2 ** attempt * 0.5, 8.0)
        if retry_after:
            try:
                delay = min(float(retry_after), 60.0)
            except ValueError:
                pass
        self._sleep(delay)

    def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        for attempt in range(self.max_retries + 1):
            self._throttle()
            start = time.monotonic()
            try:
                response = self._http.get(path, params=clean)
            except httpx.TimeoutException as exc:
                self._last_request = time.monotonic()
                if attempt < self.max_retries:
                    self._sleep_backoff(attempt, None)
                    continue
                raise WosNetworkError("Request timed out") from exc
            except httpx.TransportError as exc:
                self._last_request = time.monotonic()
                if attempt < self.max_retries:
                    self._sleep_backoff(attempt, None)
                    continue
                raise WosNetworkError(f"Network error: {type(exc).__name__}") from exc
            finally:
                pass

            self._last_request = time.monotonic()
            self.last_status = response.status_code
            self.last_elapsed_ms = int((time.monotonic() - start) * 1000)

            if response.status_code in RETRYABLE_STATUS and attempt < self.max_retries:
                self._sleep_backoff(attempt, response.headers.get("Retry-After"))
                continue

            if response.status_code >= 400:
                raise error_from_response(
                    response.status_code,
                    response.headers.get("content-type", ""),
                    response.text,
                )

            try:
                return response.json()
            except ValueError as exc:
                raise WosResponseError(
                    "Response was not valid JSON", status=response.status_code
                ) from exc

        raise WosNetworkError("Request failed after retries")

    @staticmethod
    def _path_segment(value: str) -> str:
        return urllib.parse.quote(value, safe="")

    # -- endpoints ---------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        db: str = "WOS",
        limit: int = 10,
        page: int = 1,
        sort_field: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "db": db,
            "q": query,
            "limit": limit,
            "page": page,
            "sortField": sort_field,
        }
        return _validate_documents_list(self._request("documents", params))

    def get_document(self, uid: str) -> dict[str, Any]:
        return _validate_document(self._request(f"documents/{self._path_segment(uid)}"))

    def get_journal_by_issn(self, issn: str) -> dict[str, Any]:
        return _validate_journals_list(self._request("journals", {"issn": issn}))

    def get_journal_by_id(self, journal_id: str) -> dict[str, Any]:
        return _validate_journal(self._request(f"journals/{self._path_segment(journal_id)}"))


def build_client(version: str = "v1", **kwargs: Any) -> WosClient:
    """Construct a client from the environment (raises WosConfigError if no key)."""
    return WosClient(get_api_key(), version=version, **kwargs)
