# wos — Web of Science Starter CLI

A thin, single-purpose, Agent-friendly CLI for the **Clarivate Web of Science Starter API**.
It is a machine-callable client for WoS metadata verification, WoS coverage checks and
Times Cited — **not** a discovery engine.

- No LLM, no embeddings, no PaperSearch, no Zotero, no MinerU, no MCP.
- Stable JSON output, structured errors, Windows-friendly, no API key leakage.

## Install

```powershell
uv venv .venv
uv pip install --python .venv\Scripts\python.exe -e .
```

Requires Python >= 3.10. Runtime dependency: `httpx`.

## Configuration

```powershell
[Environment]::SetEnvironmentVariable("WOS_API_KEY", "<your-key>", "User")
```

The key is read **only** from the `WOS_API_KEY` environment variable. It is never
printed, logged, committed, or written to any file. Tools report only
`WOS_API_KEY: configured`.

Optional environment overrides:

| Variable | Default | Meaning |
|---|---|---|
| `WOS_API_VERSION` | `v1` | API version (`v1`; `v2` exists and behaves identically) |
| `WOS_BASE_URL` | `https://api.clarivate.com/apis/wos-starter` | base URL override |

## Commands

```
wos search <query>                       # plain terms -> TS=(...)
wos search --raw '<advanced query>'      # sent verbatim
wos doi <doi>
wos get <uid>
wos journal <issn-or-id>
wos doctor
wos smoke
wos capabilities
```

`wos search` options:

| Option | Default | Notes |
|---|---|---|
| `--limit` | `10` | locally validated to 1..50 |
| `--page` | `1` | |
| `--sort` | none | `LD` \| `PY` \| `RS` \| `TC` |
| `--order` | `D` | `A` \| `D`; emitted as `<field>+<order>` (e.g. `TC+D`) |
| `--all-pages` | off | follow pagination using `metadata.total` |
| `--max-pages` | `10` | safety cap for `--all-pages` (quota protection) |
| `--pretty` | off | indent JSON |

## Examples

```powershell
wos doctor
wos smoke
wos search "ITO ENZ"
wos search --raw 'TS=(ITO AND ENZ) AND PY=(2022-2026)' --sort TC --order D
wos search --raw 'TS=("machine learning")' --limit 50 --all-pages
wos doi "10.1038/s41586-020-2649-2"
wos get "WOS:A1978EP88400013"
wos journal "0028-0836"
wos capabilities --pretty
```

## JSON contract

Every command prints one JSON object. `schema_version` is stable from v1.

```jsonc
{
  "schema_version": 1,
  "ok": true,
  "source": "web_of_science",
  "command": "search",
  "query": "TS=(ITO AND ENZ)",
  "metadata": { "total": 111, "page": 1, "limit": 10 },
  "records": [],
  "warnings": [],
  "error": null
}
```

A normalized document record:

```jsonc
{
  "uid": "WOS:A1978EP88400013",
  "title": "...",
  "authors": ["DOTY, RL"],
  "year": 1978,                 // int (Starter publishYear is an int)
  "journal": "PHYSIOLOGY & BEHAVIOR",
  "doi": "10.1016/0031-9384(78)90070-7",  // may be null
  "document_types": ["Article"],
  "source_types": ["Article"],
  "times_cited": 570,           // citations[] entry with db == "WOS"
  "keywords": [],               // authorKeywords, may be []
  "identifiers": { "doi": "...", "issn": "...", "pmid": "..." },
  "volume": "20",
  "issue": "2",
  "pages": { "range": "175-185", "begin": "175", "end": "185", "count": 11 },
  "wos_record_url": "https://www.webofscience.com/..."
}
```

A normalized journal record:

```jsonc
{
  "id": "NATURE-2025", "name": "NATURE", "jcr_title": "NATURE", "iso_title": "Nature",
  "issn": "0028-0836", "eissn": "1476-4687", "previous_issn": [],
  "links": [ { "type": "Journal Citation Report record", "url": "..." } ]
}
```

Notes that follow the real Starter semantics:

- **No `abstract`** and **no `keywordsPlus`** field exists — they are not invented.
- `identifiers.doi` may be missing; a record without a DOI is still returned.
- `keywords` may be `[]`.
- `pages` is an object, `year` is an int.
- `times_cited` comes from the `citations[]` entry whose `db == "WOS"` (never `citations[0]`,
  never summed across databases), or `null` when absent.

### Error object

```jsonc
{ "code": "bad_request", "message": "...", "http_status": 400,
  "title": "...", "details": "..." }
```

Error codes: `config_error`, `usage_error`, `unauthorized`, `bad_request`, `not_found`,
`rate_limited`, `server_error`, `network_error`, `unexpected_response`.
Errors never contain the API key, request headers, or the full URL.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | runtime/API/network error |
| 2 | usage or configuration error |
| 130 | interrupted |

## Field-tag support

This CLI currently targets `db=WOS` (Web of Science Core Collection) only.

Starter declares **18** tags. On `db=WOS` this CLI supports **17**:

```
AI AU CS DO DOP DT FPY IS OG PG PMID PY SO TI TS UT VL
```

- `SUR` is **disabled** (declared, but returns HTTP 400 on `db=WOS`; DRCI-only).
- `WC` is **not supported** by the Starter API.
- A bare term query is rejected by the API, so plain input is wrapped as `TS=(...)`.
  Use `--raw` for advanced queries — the CLI never guesses.

## Reliability

- Query parameters are always passed via `httpx` `params=`; URLs are never built by hand
  (an unencoded DOI is rejected by the gateway with an HTML 400).
- Retries with exponential backoff on 408/429/5xx and network errors, honoring `Retry-After`.
- Client-side throttle of ~2 req/s; `--all-pages` is capped by `--max-pages` to protect the
  5,000 requests/day quota.

## Develop / test

```powershell
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
.venv\Scripts\python.exe -m pytest
```

Tests use sanitized fixtures in `tests/fixtures/`, derived from real Web of Science
Starter API responses, plus `httpx.MockTransport`; no live calls and no key are required.
