# XBRL Validator Engine

**Regulator-grade XBRL/iXBRL validation engine** built in Python 3.12+.

Provides comprehensive validation of XBRL 2.1 instance documents, Inline XBRL (iXBRL), and xBRL-JSON, with full support for Dimensions 1.0, Formula 1.0, Table Linkbase, and Extensible Enumerations. Designed for financial regulators, filing agents, and data consumers who require deterministic, spec-compliant validation.

---

## Features

- **Multi-format support** — XBRL 2.1 XML, Inline XBRL 3.1, xBRL-JSON, and xBRL-CSV
- **Full specification coverage** — Dimensions 1.0, Formula 1.0, Table Linkbase 1.0, Extensible Enumerations 2.0
- **Regulator rule packs** — SEC EDGAR, ESMA ESEF, HMRC, CIPC, and more
- **Taxonomy management** — versioned taxonomy packages with LRU+disk caching
- **Async validation API** — FastAPI + Celery for high-throughput batch processing
- **CLI tools** — validate files, manage taxonomies, run conformance suites
- **Structured error reporting** — machine-readable JSON and human-readable rich output
- **Deterministic results** — identical input always produces identical output
- **OpenTelemetry integration** — built-in tracing, metrics, and logging
- **Security hardened** — defusedxml, entity expansion limits, zip-bomb protection

## Architecture

```
src/
├── core/           # Models, errors, enums, context — zero external deps
├── taxonomy/       # Taxonomy loader, resolver, DTS discovery, caching
├── parser/         # XML, iXBRL, JSON, CSV parsers with streaming support
├── validator/
│   ├── spec/       # Pure specification validators (XBRL 2.1, Dimensions, etc.)
│   └── regulator/  # Regulator-specific rule packs (SEC, ESEF, HMRC)
├── formula/        # XBRL Formula 1.0 processor
├── pipeline/       # Orchestration: phase runner, progress, cancellation
├── output/         # Report formatters (JSON, HTML, CSV, SARIF)
├── api/            # FastAPI REST endpoints + Celery workers
└── cli/            # Typer CLI commands
```

**Import discipline** is enforced via `import-linter`:
- `core` has zero internal imports (leaf module)
- `validator.spec` never imports from `validator.regulator`
- All layers depend inward toward `core`

## Quick Start

### Installation

```bash
# Production install
pip install -e .

# Development install (includes linting, testing, type-checking)
pip install -e ".[dev,conformance]"
```

### Validate a Filing

```bash
# Validate a single XBRL instance
xbrl-validate run filing.xbrl

# Validate an Inline XBRL document
xbrl-validate run report.html --format ixbrl

# Validate with SEC rules
xbrl-validate run filing.xbrl --rules sec

# JSON output
xbrl-validate run filing.xbrl --output results.json
```

### Manage Taxonomies

```bash
# Install a taxonomy package
xbrl-taxonomy install us-gaap-2024

# List installed taxonomies
xbrl-taxonomy list

# Update taxonomy cache
xbrl-taxonomy update
```

### Run Conformance Suite

```bash
# Run the XBRL 2.1 conformance suite
xbrl-conform run --suite xbrl21

# Run with parallel workers
xbrl-conform run --suite xbrl21 -n auto
```

### API Server

```bash
# Start the API server
make run-api

# Or with Docker Compose (includes Redis + PostgreSQL)
make docker-up
```

## Development

```bash
# Install dev dependencies
make dev

# Run linter
make lint

# Run type checker
make mypy

# Run all tests
make test

# Run tests with coverage
make test-cov

# Run fast tests only (skip slow/conformance)
make test-fast

# Run full CI pipeline
make ci

# Check import architecture constraints
make import-lint

# Format code
make format
```

## Docker

```bash
# Build images
make docker
make docker-worker

# Start full stack (API + Worker + Redis + PostgreSQL)
make docker-up

# View logs
make docker-logs

# Tear down
make docker-down
```

## Configuration

Configuration is loaded from environment variables, `.env` files, or CLI flags. See [`.env.example`](.env.example) for all available options.

Key settings:

| Variable | Default | Description |
|---|---|---|
| `XBRL_LOG_LEVEL` | `INFO` | Logging level |
| `XBRL_TAXONOMY_CACHE_DIR` | `~/.xbrl-validator/cache` | Taxonomy cache directory |
| `XBRL_MAX_FILE_SIZE_MB` | `500` | Maximum file size for validation |
| `XBRL_WORKER_CONCURRENCY` | `4` | Celery worker concurrency |
| `XBRL_DATABASE_URL` | `sqlite:///xbrl.db` | Database connection string |
| `XBRL_REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |

## Testing

The test suite includes:

- **Unit tests** — isolated tests for each module
- **Integration tests** — cross-module validation flows
- **Conformance tests** — official XBRL International conformance suites
- **Security tests** — malicious input handling, XXE prevention, zip-bomb detection
- **Benchmark tests** — performance regression tracking
- **Property-based tests** — Hypothesis-driven fuzz testing

```bash
# Run specific test categories
make test-fast          # Unit + integration (no slow tests)
make test-conformance   # XBRL conformance suites
make test-security      # Security test suite
make bench              # Performance benchmarks
```

## License

MIT License. See [LICENSE](LICENSE) for details.
