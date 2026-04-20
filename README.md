# XBRLValidator

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Enterprise-grade XBRL / iXBRL validation engine with streaming support, multi-format parsing, AI-powered fix suggestions, and regulator-specific rule profiles.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Environment Variables](#environment-variables)
- [Usage](#usage)
  - [CLI](#cli)
  - [REST API](#rest-api)
  - [Docker](#docker)
- [Validation Modules](#validation-modules)
- [Supported Formats](#supported-formats)
- [Regulator Profiles](#regulator-profiles)
- [Configuration](#configuration)
- [Development](#development)
  - [Running Tests](#running-tests)
  - [Linting & Type Checking](#linting--type-checking)
- [Roadmap](#roadmap)
- [License](#license)

---

## Features

- **Multi-format parsing** – XBRL XML, Inline XBRL (iXBRL HTML), XBRL-JSON, and XBRL-CSV.
- **Streaming / large-file support** – Memory-budgeted SAX parsing, disk-spill fact stores, memory-mapped I/O, and chunked readers for filings well beyond available RAM.
- **Comprehensive XBRL 2.1 validation** – Context, unit, fact, footnote, and tuple checks per the XBRL 2.1 specification.
- **Dimensional validation** – Hypercube/dimension relationship and typed/explicit dimension checks per the XBRL Dimensions 1.0 specification.
- **Calculation / presentation / definition link validation** – Summation-item, parent-child, and general-special link consistency checks.
- **Inline XBRL validation** – Transform verification, nested tuple support, `ix:header` / `ix:hidden` checks.
- **Formula / table validation** – XBRL Formula 1.0 assertion evaluation and Table Linkbase rendering validation.
- **Label validation** – Label linkbase completeness and language coverage checks.
- **Regulator profiles** – Pre-built rule sets for SEC (EFM), ESMA (ESEF), FERC, HMRC, CIPC, and MCA filings.
- **XULE rule engine** – Compile and execute XULE expressions for custom validation rules.
- **Plugin system** – Extensible architecture for adding custom regulator or organisation-specific rules.
- **AI-powered suggestions** – Optional OpenAI-backed fix suggestions, cross-document analysis, and tagging recommendations.
- **REST API & async workers** – FastAPI service with Celery + Redis task queue for background validation.
- **Rich CLI** – `typer`-based command-line interface with coloured, structured output via `rich`.
- **Multiple report formats** – JSON, HTML (Jinja2 templates), and extensible report generators.
- **Taxonomy management** – Catalog-based taxonomy resolution, HTTP caching, taxonomy package support, and a concept index for fast lookups.
- **Security hardened** – XXE prevention via `defusedxml`, entity-expansion limits, and input-size guards.

---

## Architecture

```
┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐
│   CLI (typer) │    │ REST API     │    │  Celery Workers      │
│              │    │ (FastAPI)    │    │  (async validation)  │
└──────┬───────┘    └──────┬───────┘    └──────────┬───────────┘
       │                   │                       │
       └───────────────────┼───────────────────────┘
                           │
                    ┌──────▼───────┐
                    │   Pipeline   │
                    └──────┬───────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
  ┌─────▼─────┐     ┌─────▼──────┐    ┌─────▼──────┐
  │  Parsers   │     │  Taxonomy  │    │ Validators │
  │ XML/iXBRL  │     │  Resolver  │    │ XBRL 2.1   │
  │ JSON/CSV   │     │  + Cache   │    │ Dimensions │
  │ SAX/Stream │     │  + Catalog │    │ Calc/Inline│
  └─────┬──────┘     └─────┬──────┘    │ Formula/...│
        │                  │           └─────┬──────┘
        └──────────────────┼─────────────────┘
                           │
                    ┌──────▼───────┐
                    │  XBRL Model  │
                    │  + Indexes   │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │   Reports    │
                    │  JSON / HTML │
                    └──────────────┘
```

---

## Project Structure

```
XBRLValidator/
├── config/
│   ├── default.yaml            # Runtime defaults (memory budget, thresholds)
│   ├── error_codes.yaml        # Error code registry with severity & fix hints
│   ├── profiles/               # Regulator-specific rule profiles
│   │   ├── efm/                #   SEC EFM rules
│   │   ├── esef/               #   ESMA ESEF rules
│   │   ├── ferc/               #   FERC rules
│   │   ├── hmrc/               #   HMRC rules
│   │   ├── cipc/               #   CIPC rules
│   │   └── mca/                #   MCA rules
│   └── transforms/             # iXBRL transformation registries
├── src/
│   ├── __init__.py
│   ├── core/
│   │   ├── constants.py        # Namespace URIs, spec constants
│   │   ├── types.py            # Enums (PeriodType, BalanceType, Severity, …)
│   │   ├── exceptions.py       # Custom exception hierarchy
│   │   ├── model/              # XBRL document object model
│   │   │   ├── xbrl_model.py   #   Top-level model dataclass
│   │   │   ├── indexes.py      #   Fact/concept/dimension indexes
│   │   │   ├── builder.py      #   DOM-based model builder
│   │   │   ├── builder_streaming.py  # SAX-based streaming builder
│   │   │   └── merge.py        #   Model merge utilities
│   │   ├── parser/             # Multi-format XBRL parsers
│   │   │   ├── format_detector.py    # Auto-detect input format
│   │   │   ├── xml_parser.py         # lxml-based XML parser
│   │   │   ├── ixbrl_parser.py       # Inline XBRL parser
│   │   │   ├── json_parser.py        # XBRL-JSON (OIM) parser
│   │   │   ├── csv_parser.py         # XBRL-CSV parser
│   │   │   ├── transform_registry.py # iXBRL transformation functions
│   │   │   └── streaming/            # Large-file streaming parsers
│   │   │       ├── memory_budget.py
│   │   │       ├── fact_index.py
│   │   │       ├── disk_spill.py
│   │   │       ├── fact_store.py
│   │   │       ├── mmap_reader.py
│   │   │       ├── chunked_reader.py
│   │   │       ├── sax_handler.py
│   │   │       ├── sax_ixbrl_handler.py
│   │   │       ├── json_streamer.py
│   │   │       └── csv_streamer.py
│   │   └── taxonomy/           # Taxonomy loading & caching
│   │       ├── catalog.py      #   XML Catalog support
│   │       ├── cache.py        #   HTTP taxonomy cache
│   │       ├── package.py      #   Taxonomy package loader
│   │       ├── resolver.py     #   URI resolver
│   │       └── concept_index.py#   Fast concept lookups
│   ├── validator/              # Validation rule modules
│   │   ├── message.py          #   ValidationMessage dataclass
│   │   ├── error_catalog.py    #   Error code registry loader
│   │   ├── base.py             #   Base validator class
│   │   └── spec/               #   Specification validators
│   │       ├── xbrl21.py       #     XBRL 2.1 core rules
│   │       ├── dimensions.py   #     Dimensions 1.0 rules
│   │       ├── calculation.py  #     Calculation linkbase rules
│   │       ├── inline.py       #     Inline XBRL rules
│   │       ├── formula.py      #     Formula 1.0 rules
│   │       ├── table.py        #     Table linkbase rules
│   │       ├── label.py        #     Label linkbase rules
│   │       ├── presentation.py #     Presentation linkbase rules
│   │       └── definition.py   #     Definition linkbase rules
│   ├── xule/                   # XULE rule engine
│   ├── plugin/                 # Plugin system
│   ├── ai/                     # AI-powered suggestions
│   ├── api/                    # FastAPI REST service
│   ├── cli/                    # Typer CLI application
│   ├── report/                 # Report generators
│   │   └── templates/          #   Jinja2 HTML report templates
│   └── utils/                  # Shared utilities
│       ├── qname.py            #   QName parsing
│       ├── datetime_utils.py   #   ISO 8601 date/time handling
│       ├── xml_utils.py        #   Secure XML helpers
│       ├── hash_utils.py       #   Content hashing
│       └── size_utils.py       #   Human-readable size formatting
├── tests/
│   ├── unit/                   # Unit tests
│   ├── integration/            # Integration tests
│   ├── e2e/                    # End-to-end tests
│   ├── conformance/            # XBRL conformance suite tests
│   ├── large_file/             # Large-file stress tests
│   └── fixtures/               # Shared test data
├── Dockerfile                  # API server image
├── Dockerfile.worker           # Celery worker image
├── docker-compose.yml          # Full stack (API + workers + Redis + Postgres)
├── Makefile                    # Common dev commands
├── pyproject.toml              # Project metadata & tool config
├── requirements.txt            # Production dependencies
├── requirements-dev.txt        # Development dependencies
└── .env.example                # Environment variable template
```

---

## Getting Started

### Prerequisites

- **Python 3.12+**
- **Redis** (for async task queue – optional for CLI usage)
- **PostgreSQL 16+** (for result persistence – optional for CLI usage)

### Installation

```bash
# Clone the repository
git clone https://github.com/AshishSinghvi18/XBRLValidator.git
cd XBRLValidator

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux / macOS
# .venv\Scripts\activate   # Windows

# Install in production mode
pip install -e .

# Or install with development tools
make dev
```

### Environment Variables

Copy `.env.example` and adjust values:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `DATABASE_URL` | `postgresql+asyncpg://xbrl:xbrl@localhost:5432/xbrl` | PostgreSQL connection URL |
| `TAXONOMY_CACHE_DIR` | `.tax_cache` | Local taxonomy cache directory |
| `MEMORY_BUDGET_MB` | `4096` | Maximum memory for streaming validation |
| `LARGE_FILE_THRESHOLD_MB` | `100` | File size that triggers streaming mode |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `OPENAI_API_KEY` | _(empty)_ | OpenAI key for AI suggestions (optional) |

---

## Usage

### CLI

```bash
# Validate an XBRL instance
xbrl-validate filing.xml

# Validate with a specific regulator profile
xbrl-validate filing.xml --profile esef

# Output results as JSON
xbrl-validate filing.xml --format json --output results.json
```

### REST API

```bash
# Start the API server
uvicorn src.api.routes:app --host 0.0.0.0 --port 8080

# Or use the Makefile
make docker
```

### Docker

```bash
# Build and run the full stack (API + 4 workers + Redis + PostgreSQL)
docker compose up --build

# The API is available at http://localhost:8080
# Health check: http://localhost:8080/health
```

---

## Validation Modules

| Module | Specification | Description |
|---|---|---|
| `xbrl21` | XBRL 2.1 | Core instance validation – contexts, units, facts, footnotes, tuples |
| `dimensions` | XBRL Dimensions 1.0 | Hypercube, dimension, and member relationship checks |
| `calculation` | Calculation Linkbase | Summation-item arithmetic consistency |
| `presentation` | Presentation Linkbase | Parent-child ordering and completeness |
| `definition` | Definition Linkbase | General-special / essence-alias / similar-tuples |
| `inline` | Inline XBRL 1.1 | iXBRL transform verification, hidden fact checks |
| `formula` | XBRL Formula 1.0 | Value / existence / consistency assertion evaluation |
| `table` | Table Linkbase 1.0 | Table rendering and structural checks |
| `label` | Label Linkbase | Label completeness and language coverage |

---

## Supported Formats

| Format | File Extensions | Parser |
|---|---|---|
| XBRL XML | `.xml`, `.xbrl` | `xml_parser.py` (lxml) |
| Inline XBRL | `.html`, `.htm` | `ixbrl_parser.py` |
| XBRL-JSON (OIM) | `.json` | `json_parser.py` (orjson / ijson streaming) |
| XBRL-CSV | `.csv` | `csv_parser.py` (polars) |

The `format_detector.py` module auto-detects the input format so you don't need to specify it manually.

---

## Regulator Profiles

Pre-built validation profiles for regulatory filings:

| Profile | Regulator | Region |
|---|---|---|
| `efm` | SEC (EDGAR Filer Manual) | United States |
| `esef` | ESMA (European Single Electronic Format) | European Union |
| `ferc` | Federal Energy Regulatory Commission | United States |
| `hmrc` | HM Revenue & Customs | United Kingdom |
| `cipc` | Companies and Intellectual Property Commission | South Africa |
| `mca` | Ministry of Corporate Affairs | India |

---

## Configuration

Runtime behaviour is controlled by `config/default.yaml`:

```yaml
validation:
  large_file_threshold_mb: 100   # Switch to streaming above this size
  memory_budget_mb: 4096         # Max memory for streaming parsers
  max_file_size_mb: 10240        # Reject files larger than this
  error_buffer_limit: 10000      # Cap on collected findings
  taxonomy_fetch_timeout_s: 30   # HTTP timeout for remote taxonomies

taxonomy:
  cache_dir: .tax_cache          # Local taxonomy cache path
  remote_timeout_s: 30

output:
  default_format: json           # json | html
  include_fix_suggestions: true  # Attach fix hints to findings
  include_ai: false              # Enable AI-powered suggestions
```

Error codes and their metadata are defined in `config/error_codes.yaml`.

---

## Development

### Running Tests

```bash
# Unit tests only
make test

# Streaming-specific tests
make test-streaming

# Integration tests (requires Redis + PostgreSQL)
make test-integration

# All tests with a 5-minute timeout
make test-all
```

### Linting & Type Checking

```bash
# Lint with ruff
make lint

# Auto-format
make format

# Type checking with mypy
make type-check

# Clean build artefacts
make clean
```

---

## Roadmap

The project is being built in phases. Current progress:

- [x] **Phase 0** – Project infrastructure (`pyproject.toml`, `.gitignore`, `Makefile`, `Dockerfile`, `docker-compose.yml`, `LICENSE`, requirements)
- [x] **Phase 1** – Foundation (`constants.py`, `types.py`, `exceptions.py`, utility modules, config files)
- [x] **Phase 2** – Streaming infrastructure (`memory_budget`, `fact_index`, `disk_spill`, `fact_store`, `mmap_reader`, `chunked_reader`)
- [x] **Phase 3** – Parsers (`format_detector`, `xml_parser`, `ixbrl_parser`, `transform_registry`, `json_parser`, `csv_parser`, SAX handlers, streaming parsers)
- [x] **Phase 4** – Taxonomy (`catalog`, `cache`, `package`, `resolver`, `concept_index`)
- [x] **Phase 5** – Model (`xbrl_model`, `indexes`, `builder`, `builder_streaming`, `merge`)
- [x] **Phase 6** – Validators (`message`, `error_catalog`, `base`, `xbrl21`, `dimensions`, `calculation`, `inline`, `formula`, `table`, `label`, `presentation`, `definition`)
- [ ] **Phase 7** – XULE engine (AST nodes, builtins, lexer, parser, compiler, query planner, evaluator)
- [ ] **Phase 8** – Plugin system & regulator profiles (profile loader, rule compiler, EFM, ESEF, FERC, HMRC, CIPC, MCA, custom)
- [ ] **Phase 9** – AI layer (fix suggester, business rules, cross-document analysis, tagging analyser)
- [ ] **Phase 10** – Pipeline, API, CLI & reports (`pipeline.py`, `routes.py`, `worker.py`, `cli/main.py`, report generators)
- [ ] **Phase 11** – Tests & fixtures
- [ ] **Phase 12** – Final validation (lint, build, test)

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.