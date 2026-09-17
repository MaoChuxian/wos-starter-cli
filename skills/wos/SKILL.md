---
name: wos
description: Query the Web of Science Starter API with the `wos` command - search WoS documents with advanced field tags, look up a paper by DOI or WoS UID, check whether a journal is indexed (ISSN/ID), and read Times Cited counts. Use to verify whether a paper or journal is covered by Web of Science, to obtain authoritative WoS metadata and citation counts, for precise advanced WoS searches, or to cross-check candidates found by other search tools. Not for open-ended discovery, abstracts, full text, or PDFs.
---

# Web of Science (Starter) from the shell

`wos` is a thin, single-purpose client for the Clarivate Web of Science Starter API.
It does one job: authoritative WoS metadata, coverage checks, and Times Cited.

Prefer it over adding a WoS MCP server while you have shell access.

## Readiness

Run before the first real call:

```powershell
wos doctor
```

It reports `WOS_API_KEY: configured` (never the key) and checks the live endpoint.
If the key is missing, ask the user to set `WOS_API_KEY` in their environment —
never paste the key into chat.

## Commands

```powershell
wos search "<plain terms>"                 # wrapped as TS=(...)
wos search --raw '<advanced query>'        # sent verbatim
wos doi <doi>
wos get <uid>
wos journal <issn-or-id>
wos capabilities
```

All commands print one JSON object (compact by default; add `--pretty`).
Exit codes: `0` ok, `1` runtime/API/network error, `2` usage/config error.

## Use WoS for

- Confirming whether a paper is indexed by Web of Science (by DOI / title / UID).
- Getting an authoritative **Times Cited** count (`times_cited`).
- Verifying metadata against WoS (DOI, journal, year, document type, WoS UID).
- Precise advanced searches that this API supports.
- Cross-checking candidates discovered by PaperSearch / OpenAlex / Crossref.

## Do NOT use WoS for

- Open-ended literature discovery or as the sole discovery source.
- Abstracts (the Starter API has no abstract field), full text, or PDFs.
- Replacing OpenAlex / Semantic Scholar / Crossref / PaperSearch for recall.

## Boundaries you must respect

- **"Not indexed in WoS" does not mean "not valuable".** Report it as a fact about
  indexing; never delete or down-rank a paper because WoS lacks it.
- `wos capabilities` describes the exact static surface. Trust it for routing.
- The Starter API supports **17 field tags on `db=WOS`** (`TI IS SO VL PG CS PY AU AI
  UT DO DT PMID OG TS + DOP FPY`); `SUR` is disabled and `WC` is unsupported. Use
  `--raw` for advanced queries — the CLI never guesses.

## Reading results

Every response has `ok`, `records`, `metadata`, `warnings`, and `error`.
A record carries `uid`, `title`, `authors`, `year`, `journal`, `doi` (may be `null`),
`document_types`, `times_cited`, `keywords` (may be `[]`), and `pages` (an object).
Do not expect `abstract`.

```powershell
wos doi "10.1038/s41586-020-2649-2" --pretty
wos get "WOS:A1978EP88400013"
wos search --raw 'TS=(ITO AND ENZ) AND PY=(2022-2026)' --sort TC --order D --limit 20
wos journal "0028-0836"
```

## Pagination and quota

- One page is at most 50 records. Use `--all-pages --max-pages N` to follow
  pagination (bounded on purpose: the plan allows 5,000 requests/day).
- Prefer small `--limit` for checks; reserve broad paging for deliberate batches.

## Safety

- Never hardcode, echo, commit, or log the API key. `wos` reads it only from
  `WOS_API_KEY` and prints at most `WOS_API_KEY: configured`.
- Structured errors (`error.code`, `error.http_status`, `error.details`) never
  contain the key or request headers.
