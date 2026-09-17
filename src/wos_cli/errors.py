"""Structured errors for the WoS CLI.

Design rules:
- Never include request headers, the API key, or the full URL (which may carry
  the query) in error messages.
- Preserve the API's own ``{error: {status, title, details}}`` payload.
"""
from __future__ import annotations

from typing import Any


class WosError(Exception):
    code = "error"
    exit_code = 1

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        title: str | None = None,
        details: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.title = title
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "http_status": self.status,
            "title": self.title,
            "details": self.details,
        }


class WosConfigError(WosError):
    """Missing/invalid local configuration (e.g. no API key)."""

    code = "config_error"
    exit_code = 2


class WosUsageError(WosError):
    """The caller asked for something invalid/unsupported."""

    code = "usage_error"
    exit_code = 2


class WosAuthError(WosError):
    code = "unauthorized"


class WosBadRequestError(WosError):
    code = "bad_request"


class WosNotFoundError(WosError):
    code = "not_found"


class WosRateLimitError(WosError):
    code = "rate_limited"


class WosServerError(WosError):
    code = "server_error"


class WosNetworkError(WosError):
    code = "network_error"


class WosResponseError(WosError):
    code = "unexpected_response"


_STATUS_TO_CLASS: dict[int, type[WosError]] = {
    400: WosBadRequestError,
    401: WosAuthError,
    403: WosAuthError,
    404: WosNotFoundError,
    429: WosRateLimitError,
}


def error_from_response(status: int, content_type: str, body: str) -> WosError:
    """Build a structured error from an HTTP error response.

    Handles the two documented shapes plus non-JSON (HTML) gateway errors:
    - 400: ``{"error": {"status", "title", "details"}}``
    - 401: ``{"error": "invalid_request", "error_description": "..."}``
    - HTML (e.g. Tomcat 400 for an unencoded URL)
    """
    title: str | None = None
    details: str | None = None

    looks_json = "json" in (content_type or "").lower() or body.lstrip().startswith("{")
    if looks_json:
        import json

        try:
            data = json.loads(body)
        except ValueError:
            data = None
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                title = err.get("title")
                details = err.get("details")
            elif isinstance(err, str):
                title = err
                details = data.get("error_description")
            if title is None and data.get("error_description"):
                title = data.get("error_description")
    elif body.lstrip().lower().startswith(("<!doctype", "<html")):
        title = "Gateway returned an HTML error page (query string probably not encoded correctly)"
        details = "This is not the Starter API JSON error format; check that special characters were URL-encoded by the HTTP client."

    message = title or f"HTTP {status}"
    cls = _STATUS_TO_CLASS.get(status)
    if cls is None:
        cls = WosServerError if status >= 500 else WosError
    return cls(message, status=status, title=title, details=details)
