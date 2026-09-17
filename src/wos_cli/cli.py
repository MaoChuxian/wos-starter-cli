"""Command-line interface for the WoS Starter API.

Machine-first JSON contract (see README.md for the full schema).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from typing import Any

from . import SCHEMA_VERSION, SOURCE, __version__
from .client import build_client, get_api_key
from .errors import WosConfigError, WosError, WosUsageError
from .normalize import normalize_document, normalize_journal, normalize_metadata
from .query import (
    DEFAULT_LIMIT,
    DEFAULT_MAX_PAGES,
    DECLARED_TAGS,
    DISABLED_TAGS,
    MAX_LIMIT,
    SORT_FIELDS,
    SORT_ORDERS,
    SUPPORTED_TAGS,
    UNSUPPORTED_TAGS,
    build_doi_query,
    build_plain_query,
    build_sort_field,
    is_issn,
    looks_like_advanced,
    validate_limit,
    validate_raw_query,
)

API_NAME = "Web of Science Starter"
# This CLI intentionally targets the Web of Science Core Collection only.
DB = "WOS"
KNOWN_COMMANDS = frozenset(
    {"search", "doi", "get", "journal", "doctor", "smoke", "capabilities"}
)


class WosArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that raises instead of printing + SystemExit(2).

    This lets :func:`main` route parse errors through the same JSON envelope as
    every other error. ``--help``/``--version`` still use argparse's normal
    ``SystemExit`` path.
    """

    def error(self, message: str) -> None:
        raise WosUsageError(message)


def _infer_command(argv: list[str]) -> str | None:
    """Best-effort command name for the envelope when parsing fails."""
    for token in argv:
        if token in KNOWN_COMMANDS:
            return token
        if not token.startswith("-"):
            return token
    return None


def _api_version() -> str:
    return os.environ.get("WOS_API_VERSION", "v1")


def _base_url_override() -> str | None:
    return os.environ.get("WOS_BASE_URL") or None


def _envelope(command: str, **extra: Any) -> dict[str, Any]:
    env: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "source": SOURCE,
        "command": command,
        "query": None,
        "metadata": None,
        "records": [],
        "warnings": [],
        "error": None,
    }
    env.update(extra)
    return env


def _emit(env: dict[str, Any], pretty: bool, stream: Any = None) -> None:
    stream = stream or sys.stdout
    stream.write(json.dumps(env, indent=2 if pretty else None, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def cmd_search(args: argparse.Namespace, client: Any) -> dict[str, Any]:
    warnings: list[str] = []
    if args.raw and args.query:
        raise WosUsageError("provide either a plain query or --raw, not both")
    if not args.raw and not args.query:
        raise WosUsageError("search requires a query or --raw '<advanced query>'")

    if args.raw:
        warnings.extend(validate_raw_query(args.raw))
        query = args.raw.strip()
    else:
        if looks_like_advanced(args.query):
            warnings.append(
                "query looks like an advanced WoS query; if intended, pass it via "
                "--raw so it is sent verbatim instead of being wrapped in TS=(...)"
            )
        query = build_plain_query(args.query)

    validate_limit(args.limit)
    if args.page < 1:
        raise WosUsageError("--page must be >= 1")
    if args.max_pages < 1:
        raise WosUsageError("--max-pages must be >= 1")
    sort_field = build_sort_field(args.sort, args.order)

    records: list[dict[str, Any]] = []
    total: int | None = None
    pages_fetched = 0
    truncated = False
    page = args.page

    while True:
        data = client.search(
            query, db=DB, limit=args.limit, page=page, sort_field=sort_field
        )
        md = normalize_metadata(data.get("metadata")) or {}
        total = md.get("total")
        hits = data.get("hits") or []
        records.extend(normalize_document(hit) for hit in hits)
        pages_fetched += 1

        if not args.all_pages:
            break
        if pages_fetched >= args.max_pages:
            truncated = total is None or len(records) < total
            break
        if not hits or len(hits) < args.limit:
            break
        if total is not None and len(records) >= total:
            break
        page += 1

    metadata: dict[str, Any] = {"total": total, "page": args.page, "limit": args.limit}
    if args.all_pages:
        metadata["pages_fetched"] = pages_fetched
        metadata["truncated"] = truncated
    if not records:
        warnings.append("no records matched the query")

    return _envelope(
        "search", query=query, metadata=metadata, records=records, warnings=warnings
    )


def cmd_doi(args: argparse.Namespace, client: Any) -> dict[str, Any]:
    doi = (args.doi or "").strip()
    if not doi:
        raise WosUsageError("DOI must not be empty")
    query = build_doi_query(doi)
    data = client.search(query, db=DB, limit=5, page=1)
    metadata = normalize_metadata(data.get("metadata"))
    records = [normalize_document(hit) for hit in (data.get("hits") or [])]
    warnings: list[str] = []
    if not records:
        warnings.append(f"no WoS record matched DOI {doi}")
    elif len(records) > 1:
        warnings.append(f"DOI matched {len(records)} records")
    return _envelope(
        "doi",
        query=query,
        metadata=metadata,
        records=records,
        match_count=len(records),
        warnings=warnings,
    )


def cmd_get(args: argparse.Namespace, client: Any) -> dict[str, Any]:
    uid = (args.uid or "").strip()
    if not uid:
        raise WosUsageError("UID must not be empty")
    record = normalize_document(client.get_document(uid))
    return _envelope("get", query=f"UID:{uid}", records=[record])


def cmd_journal(args: argparse.Namespace, client: Any) -> dict[str, Any]:
    identifier = (args.identifier or "").strip()
    if not identifier:
        raise WosUsageError("journal identifier must not be empty")
    if is_issn(identifier):
        data = client.get_journal_by_issn(identifier)
        metadata = normalize_metadata(data.get("metadata"))
        records = [normalize_journal(hit) for hit in (data.get("hits") or [])]
        query = f"ISSN:{identifier}"
    else:
        metadata = None
        records = [normalize_journal(client.get_journal_by_id(identifier))]
        query = f"JOURNAL_ID:{identifier}"
    warnings = [] if records else ["no journal matched"]
    return _envelope(
        "journal", query=query, metadata=metadata, records=records, warnings=warnings
    )


def cmd_capabilities(_: argparse.Namespace) -> dict[str, Any]:
    return _envelope(
        "capabilities",
        api=API_NAME,
        version=_api_version(),
        database=DB,
        max_page_size=MAX_LIMIT,
        min_page_size=1,
        default_limit=DEFAULT_LIMIT,
        declared_field_tags=sorted(DECLARED_TAGS),
        supported_field_tags=sorted(SUPPORTED_TAGS),
        disabled_field_tags=sorted(DISABLED_TAGS),
        unsupported_field_tags=sorted(UNSUPPORTED_TAGS),
        sort_fields=list(SORT_FIELDS),
        sort_orders=list(SORT_ORDERS),
        supports={
            "search": True,
            "doi": True,
            "uid": True,
            "journal": True,
            "pagination": True,
            "times_cited": True,
            "abstract": False,
            "full_text": False,
            "pdf": False,
        },
    )


def cmd_doctor(_: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(check_id: str, status: str, summary: str) -> None:
        checks.append({"id": check_id, "status": status, "summary": summary})

    if sys.version_info >= (3, 10):
        add("runtime.python", "pass", f"Python {platform.python_version()}")
    else:
        add("runtime.python", "fail", "Python >= 3.10 required")

    key = get_api_key()
    if key:
        add("config.api_key", "pass", "WOS_API_KEY: configured")
    else:
        add("config.api_key", "fail", "WOS_API_KEY: missing")

    version = _api_version()
    base = _base_url_override() or "https://api.clarivate.com/apis/wos-starter"
    add("config.endpoint", "pass", f"base URL {base} (version {version})")

    if key:
        try:
            with build_client(
                version=version, base_url=_base_url_override(), min_interval=0.0
            ) as client:
                data = client.search("TS=(machine learning)", limit=1, page=1)
                add("api.documents", "pass", f"HTTP {client.last_status}")
                md = data.get("metadata")
                schema_ok = (
                    isinstance(md, dict)
                    and isinstance(md.get("total"), int)
                    and isinstance(data.get("hits"), list)
                )
                add(
                    "schema.documents",
                    "pass" if schema_ok else "fail",
                    "documents response has metadata.total and hits[]"
                    if schema_ok
                    else "documents response schema did not match expectations",
                )
        except WosError as exc:
            add("api.documents", "fail", exc.message)
            add("schema.documents", "skip", "skipped: documents request failed")
    else:
        add("api.documents", "skip", "skipped: no API key")
        add("schema.documents", "skip", "skipped: no API key")

    warnings = [c["summary"] for c in checks if c["status"] != "pass"]
    ok = all(c["status"] != "fail" for c in checks)
    return _envelope("doctor", ok=ok, checks=checks, warnings=warnings)


def cmd_smoke(_: argparse.Namespace) -> dict[str, Any]:
    if not get_api_key():
        raise WosConfigError("WOS_API_KEY is not set")
    version = _api_version()
    with build_client(
        version=version, base_url=_base_url_override(), min_interval=0.0
    ) as client:
        start = time.monotonic()
        data = client.search("TS=(machine learning)", limit=1, page=1)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        total = (normalize_metadata(data.get("metadata")) or {}).get("total")
        return _envelope(
            "smoke",
            endpoint_version=version,
            http_status=client.last_status,
            elapsed_ms=elapsed_ms,
            metadata={"total": total},
        )


# --------------------------------------------------------------------------
# parser / dispatch
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--pretty", action="store_true", help="indent JSON output")

    parser = WosArgumentParser(
        prog="wos", description="Agent-friendly CLI for the Web of Science Starter API"
    )
    parser.add_argument("--version", action="version", version=f"wos {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", parents=[common], help="search documents")
    p.add_argument("query", nargs="?", help="plain terms (wrapped as TS=(...))")
    p.add_argument("--raw", metavar="QUERY", help="raw WoS advanced query (sent verbatim)")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="1..50 (default 10)")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--sort", choices=SORT_FIELDS, default=None, help="LD|PY|RS|TC")
    p.add_argument("--order", choices=SORT_ORDERS, default=None, help="A|D")
    p.add_argument("--all-pages", action="store_true", help="follow pagination")
    p.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)

    p = sub.add_parser("doi", parents=[common], help="look up a document by DOI")
    p.add_argument("doi")

    p = sub.add_parser("get", parents=[common], help="get a document by WoS UID")
    p.add_argument("uid")

    p = sub.add_parser("journal", parents=[common], help="look up a journal by ISSN or ID")
    p.add_argument("identifier")

    sub.add_parser("doctor", parents=[common], help="health check")
    sub.add_parser("smoke", parents=[common], help="one low-cost live request")
    sub.add_parser("capabilities", parents=[common], help="static capability description")
    return parser


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "capabilities":
        return cmd_capabilities(args)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "smoke":
        return cmd_smoke(args)

    with build_client(
        version=_api_version(), base_url=_base_url_override()
    ) as client:
        if args.command == "search":
            return cmd_search(args, client)
        if args.command == "doi":
            return cmd_doi(args, client)
        if args.command == "get":
            return cmd_get(args, client)
        if args.command == "journal":
            return cmd_journal(args, client)
    raise WosUsageError(f"unknown command {args.command!r}")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    pretty = "--pretty" in argv

    try:
        args = parser.parse_args(argv)
    except WosUsageError as exc:
        # Parse errors are reported through the same JSON envelope as everything
        # else. --help / --version still exit normally via SystemExit.
        env = _envelope(_infer_command(argv), ok=False, error=exc.to_dict())
        _emit(env, pretty)
        return exc.exit_code

    pretty = getattr(args, "pretty", False)
    try:
        env = dispatch(args)
        code = 0 if env.get("ok") else 1
    except WosError as exc:
        env = _envelope(args.command, ok=False, error=exc.to_dict())
        code = exc.exit_code
    except KeyboardInterrupt:  # pragma: no cover
        return 130
    _emit(env, pretty)
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
