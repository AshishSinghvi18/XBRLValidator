# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Project scaffold with full build configuration
- Core domain models, enums, and error types
- Taxonomy loader with DTS discovery and LRU+disk caching
- XML, iXBRL, xBRL-JSON, and xBRL-CSV parsers
- XBRL 2.1 specification validators
- Dimensions 1.0 validation
- Formula 1.0 processor
- Extensible Enumerations 2.0 support
- Regulator rule packs: SEC EDGAR, ESMA ESEF, HMRC, CIPC
- Validation pipeline orchestrator with progress tracking
- Output formatters: JSON, HTML, CSV, SARIF
- FastAPI REST API with async validation endpoints
- Celery worker for batch processing
- CLI tools: `xbrl-validate`, `xbrl-taxonomy`, `xbrl-conform`
- Docker and Docker Compose deployment
- OpenTelemetry tracing and metrics
- Import architecture enforcement via import-linter
- Comprehensive test suite with conformance, security, and benchmark tests

## [1.0.0] - 2024-01-01

### Added
- Initial release of the XBRL Validator Engine
