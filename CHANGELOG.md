# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-04-20

### Added
- Full XBRL 2.1 validation with conformance suite support
- XBRL Dimensions 1.0 (XDT) full implementation
- Calculation 1.0 (classic) and Calculation 1.1 (2023)
- iXBRL 1.1 with full transform support (ixt-1 through ixt-5 + ixt-sec)
- XBRL Formula 1.0 engine
- Table Linkbase 1.0 with rendering
- Extensible Enumerations 2.0
- OIM support (XBRL-JSON, XBRL-CSV) with round-trip validation
- Generic Links 1.0
- Taxonomy Packages 1.0 with XML catalog support
- SEC EFM regulator module (~150 rules)
- ESEF regulator module (~80 rules including full anchoring)
- FERC regulator module with XULE engine
- HMRC, CIPC, MCA regulator modules
- Streaming parser for files > 100 MB with disk-spill
- Memory budget management (4 GB default)
- Zero-trust XML parsing (XXE, billion laughs, zip bomb protection)
- CLI with rich progress display
- FastAPI REST API with WebSocket progress
- Multiple report formats (JSON, SARIF, HTML, CSV, JUnit, Arelle-compat)
- AI-powered fix suggestions (deterministic + optional LLM)
- Decimal-everywhere numeric handling (no float in value paths)
