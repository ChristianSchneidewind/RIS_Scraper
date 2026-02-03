# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

**Prerequisites**

- Python 3.9+
- Recommended: create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate

# Install in editable mode
pip install -e .
```

**Lint/Test**

There are no dedicated lint or test commands configured in this repository. If you add tests, document how to run them here.

**CLI (after install)**

```bash
# Show version
ris-law version get

# Example GET request (Bundesrecht)
ris-law bundesrecht get \
  --param Applikation=BrKons \
  --param Seitennummer=1 \
  --param DokumenteProSeite=OneHundred \
  --param Fassung.FassungVom=2024-01-01 \
  --json

# Example POST with JSON body
ris-law judikatur post --body-file query.json --json
```

## Architecture Overview

`ris-law` is a lightweight Python library and CLI for fetching Austrian federal laws from the RIS (Rechtsinformationssystem des Bundes) and exporting them as JSONL.

### Core Package (`ris_law/`)

- `__init__.py` - Public API (exports `iter_law`, `write_jsonl`, `RisApiClient`)
- `api.py` - Facade for RIS API v2.6 requests
- `cli_main.py` - CLI entry point (`ris-law`)
- `types.py` - Datamodels (e.g., `LawItem`)
- `writer.py` - JSONL output helpers
- `toc_parser.py` / `html_parser.py` - RIS HTML/TOC parsing
- `index_scraper.py` - Optional fallback scraping mode
- `search.py`, `soap_client.py` - RIS search + SOAP integration
- `config.py` - Constants, default timeouts, and law lookup helpers

### Data Files

- `ris_law/data/laws.json` - Law metadata used for lookup and fallback ranges
- `ris_law/data/*.jsonl` - Optional bundled datasets

### Key Behaviors

- No caching layer is enabled by default; request delays are used for rate limiting.
- The library supports fetching data by paragraph or NOR level and writing JSONL output.
- The CLI is a thin wrapper around the API and writer helpers.
