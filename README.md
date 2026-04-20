# XBRL/iXBRL Validator Engine

Production-grade XBRL/iXBRL validation engine — regulator-grade, competitive with Arelle.

## Features

- **Full XBRL specification coverage**: XBRL 2.1, Dimensions 1.0, Calculation 1.0/1.1, Formula 1.0, iXBRL 1.1, Table Linkbase 1.0, Enumerations 2.0, OIM (JSON/CSV), Generic Links, Versioning
- **Multi-regulator support**: SEC EFM, ESMA ESEF, FERC, HMRC, CIPC, MCA
- **Large file handling**: Streaming parser for multi-GB files with disk-spill to SQLite
- **Security-first**: Zero-trust XML parsing, zip bomb protection, SSRF prevention
- **Decimal precision**: No float in numeric value paths — all Decimal arithmetic
- **Conformance tested**: Against official XBRL International conformance suites

## Quick Start

```bash
pip install xbrl-validator

# Validate an XBRL instance
xbrl-validate validate filing.xml --regulator efm --output json

# Validate iXBRL
xbrl-validate validate report.html --regulator esef --output html

# Preload taxonomy cache
xbrl-taxonomy preload-package us-gaap-2024.zip
```

## Docker

```bash
docker-compose up -d
curl -X POST http://localhost:8000/v1/validate -F "file=@filing.xml"
```

## Development

```bash
make dev          # Install dev dependencies
make test         # Run unit tests
make lint         # Run linter
make typecheck    # Run mypy
make ci           # Run full CI pipeline
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for detailed architecture documentation.

## License

MIT
