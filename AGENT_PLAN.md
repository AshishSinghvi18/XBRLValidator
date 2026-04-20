# XBRL/iXBRL Validator Engine — Agent Execution Plan

> **Version:** 3.0.0 | **Date:** 2026-04-20
> **Type:** Deterministic build plan for AI coding agent
> **Scope:** Full-spec XBRL/iXBRL validator — regulator-grade, competitive with Arelle
> **Estimated Output:** ~450 files, ~180,000 lines of code
> **Estimated Effort:** 18–24 months with a 4–6 engineer team (or equivalent agent time)
> **Language:** Python 3.12+ (primary), TypeScript (API SDK)

---

## 0. WHAT CHANGED FROM v2.0

This plan replaces v2.0 in full. Key differences:

**Added (previously missing):**
- Full XBRL Formula 1.0 engine (value/existence/consistency assertions, variable sets, filters, generators, XPath 2.0 subset)
- Full XBRL Dimensions 1.0 with hypercube inheritance, typed-dim schema validation, targetRole traversal
- Calculation 1.1 (2023 spec) alongside classic Calculation
- Full OIM semantic layer (XBRL-JSON, XBRL-CSV canonical model, round-trip equivalence)
- XBRL International conformance suites as the primary gate for every spec module
- Full EFM coverage (DEI, NEGVAL, period-of-report, share class, iXBRL 6.20.x)
- Full ESEF anchoring rules (30+ specific rules, not just BFS)
- Taxonomy Packages 1.0 with META-INF/catalog precedence and version-aware caching
- Taxonomy versioning (us-gaap yearly releases, version-aware concept mapping)
- Complete XULE implementation (aspect binding, factset ops, navigation, calendar arithmetic)
- Extensible Enumerations 2.0, Generic Links, Versioning Report
- Table Linkbase full rendering model (not just validation)
- LRR (Link Role Registry) validation
- SEC NEGVAL catalog integration
- Units Registry (UTR) validation
- Calculation 1.1 duplicate-fact rounding model

**Kept from v2.0 (the genuinely strong parts):**
- Decimal-everywhere rule
- Streaming-first with SAX/iterparse, disk spill to SQLite, mmap for SSDs
- Zero-trust XML parsing (defusedxml, entity expansion caps)
- Registered error code catalog with fix suggestions
- Regulator isolation via plugin loader
- Memory budget with component registration
- Byte-offset fact indexing with chunked reader for HDDs

**Explicitly rejected from v2.0:**
- "70% YAML / 30% Python for EFM" — wrong ratio, reversed to ~30/70
- "Assume SSD" fallback in mmap detection — changed to assume HDD
- `orjson` / `polars` as-is for numeric values — wrapped with Decimal-preserving layers
- Scope that suggested a 6-person team could deliver this in 6 months — now explicitly sized at 18–24 months

**Moved to separate tracks (still in-scope, not v1.0):**
- Celery/Redis/Postgres deployment stack — optional, ships after library+CLI
- Full AI layer — shipped in v1.2 after core stability
- Multi-regulator simultaneous parity — shipped as EFM-first, ESEF next, then FERC, HMRC, CIPC, MCA

---

## 1. AGENT OPERATING RULES (READ BEFORE ANY CODE GENERATION)

```text
RULE 1 — DECIMAL NEVER FLOAT
   ALL numeric XBRL values → Python `decimal.Decimal`.
   NEVER use `float` for: fact values, tolerances, rounding, scale multiplication,
   calculation summation, formula arithmetic, duplicate-fact comparison.
   Violation = critical defect. CI check: grep for `float(` in value paths fails build.

RULE 2 — STREAMING FIRST
   Every file-reading function MUST check file size first.
   ≤ 100 MB  → DOM parsing allowed (configurable per format).
   > 100 MB  → MUST use streaming / SAX / iterparse.
   > 1 GB    → MUST use streaming + disk-spilled fact index.
   NEVER load a file > 100 MB into memory as a single DOM.

RULE 3 — ZERO-TRUST PARSING
   All XML parsing MUST disable: external entities, DTD loading, network resolution,
   entity expansion (cap at 100). Use defusedxml or hardened lxml XMLParser.
   XXE / billion-laughs / quadratic-blowup tests in security test suite.

RULE 4 — REGISTERED ERROR CODES
   Every emitted message MUST have a code (PREFIX-NNNN), severity, spec clause ref,
   message template, fix suggestion, and at least one failing test fixture — all
   registered in config/error_codes.yaml. CI check: every code emitted in src/ must
   exist in registry; every registry entry must have a test that triggers it.

RULE 5 — REGULATOR ISOLATION
   src/core/* and src/validator/spec/* must NEVER import from src/validator/regulator/*.
   Regulators are loaded dynamically via src/plugin/profile_loader.py.
   CI check: import-linter contract enforces boundary.

RULE 6 — TYPE HINTS EVERYWHERE
   Every function: full parameter + return type hints.
   Every attribute: type annotation. Use dataclasses / Pydantic / TypedDict.
   CI: `mypy --strict src/` passes with zero errors.

RULE 7 — DOCSTRINGS WITH SPEC REFERENCES
   Every validation function docstring MUST cite: spec name + clause, what it checks,
   error codes emitted, fix suggestion category.
   Format: `Spec: XBRL 2.1 §5.2.5.2 | Emits: CALC-0002, CALC-0003 | Fix: rounding`.

RULE 8 — CONFORMANCE FIRST
   Every spec validator (xbrl21, dims, calc, formula, inline, table) MUST pass the
   official XBRL International conformance suite for that spec before being merged.
   Conformance results tracked in conformance/results.json, published in CI.
   A validator that passes unit tests but fails conformance is NOT done.

RULE 9 — TEST PER RULE
   Every validation rule needs ≥ 3 tests: valid-input, invalid-input, edge-case.
   Large-file code needs threshold-boundary tests (99 MB / 101 MB / 1 GB / 10 GB synthetic).
   Security code needs attack-vector tests.

RULE 10 — FAIL-SAFE RECOVERY
   On malformed input: log error, skip section, continue parsing.
   Never crash on attacker-controlled input. Never raise unhandled exception to caller.
   Exception: security violations (XXE detected) SHOULD abort with clear error.

RULE 11 — DETERMINISTIC
   Same input → same output. Sort order of errors deterministic (by source_line, then code).
   AI suggestions are the ONLY non-deterministic part and MUST be tagged source="AI"
   with a confidence score. Disable-able via --no-ai.

RULE 12 — MEMORY BUDGET
   Default 4 GB. Every accumulating component (fact index, error list, taxonomy cache,
   continuation chains) registers with MemoryBudget. Spills to disk (SQLite) on pressure.
   Peak RSS tracked via psutil, logged at end of each pipeline stage.

RULE 13 — STRUCTURED LOGGING
   Python logging module + structlog for JSON output.
   Every pipeline stage logs: name, start_ts, end_ts, items_processed, errors_found,
   memory_used_bytes, spill_occurred. One log line per fact is PROHIBITED (log storms).

RULE 14 — ARELLE COMPATIBILITY
   For every spec-level error, document the equivalent Arelle error code in
   docs/arelle_compat.md. When our behavior diverges from Arelle, document WHY.
   This is mandatory for customer migration stories.

RULE 15 — VERSION-AWARE TAXONOMIES
   Taxonomies have versions (us-gaap-2024, us-gaap-2025, ifrs-2023, ifrs-2024).
   Filings reference specific versions. Cache is keyed on (name, version, entry_point).
   Never silently substitute versions. Cross-version concept mapping is an explicit tool.

RULE 16 — NO SHORTCUTS ON NUMERIC PARSING
   `orjson`, `ijson`, `polars`, `pandas` all have float default behavior.
   Numeric fact values MUST go: source_bytes → str → Decimal, never through float.
   For orjson: use OPT_PASSTHROUGH_SUBCLASS and handle numerics as strings.
   For polars: read numeric columns with `dtype=pl.Utf8`, convert to Decimal in Python.
   For ijson: use `ijson.items_coro` with `use_float=False` or parse from raw string events.

RULE 17 — STORAGE ASSUMPTIONS ARE CONSERVATIVE
   Unknown disk → assume HDD (not SSD). Fall back to ChunkedReader.
   mmap is opt-in when SSD is detected reliably, not the default.

RULE 18 — NO HIDDEN NETWORK I/O
   Taxonomy fetches are explicit. Offline mode is supported and tested.
   All remote URLs must either (a) resolve via XML catalog, (b) exist in taxonomy
   package, or (c) be explicitly allowed via --allow-remote flag.
```

---

## 2. DEPENDENCIES

```toml
# pyproject.toml [project] section
[project]
name = "xbrl-validator"
version = "1.0.0"
requires-python = ">=3.12"
dependencies = [
  # XML / parsing
  "lxml>=5.1.0",              # XML parsing with iterparse
  "defusedxml>=0.7.1",        # XXE-safe DOM parsing
  "html5lib>=1.1",            # HTML5 iXBRL parsing fallback
  # JSON / data
  "ijson>=3.2.3",             # streaming JSON
  "orjson>=3.10.0",           # fast JSON writer (output only)
  "jsonschema>=4.21.0",       # JSON schema validation
  # Tabular
  "polars>=0.20.0",           # XBRL-CSV, streaming
  # Numeric
  "python-dateutil>=2.9.0",   # date/time parsing (XML Schema dateTime)
  "isodate>=0.6.1",           # ISO 8601 duration parsing
  # XPath / Formula
  "elementpath>=4.4.0",       # XPath 2.0 / 3.1 evaluator (used by Formula)
  # Caching / storage
  "msgpack>=1.0.8",           # fast cache serialization
  "diskcache>=5.6.3",         # taxonomy disk cache
  # Web
  "fastapi>=0.110.0",
  "uvicorn[standard]>=0.29.0",
  "python-multipart>=0.0.9",
  "httpx>=0.27.0",            # async HTTP for taxonomy fetch
  # Async tasks
  "celery[redis]>=5.3.6",
  "redis>=5.0.0",
  # DB
  "sqlalchemy>=2.0.29",
  "asyncpg>=0.29.0",
  "alembic>=1.13.0",
  # CLI / UX
  "typer[all]>=0.12.0",
  "rich>=13.7.0",
  "jinja2>=3.1.3",
  # Validation
  "pydantic>=2.6.0",
  # Observability
  "structlog>=24.1.0",
  "psutil>=5.9.8",
  "opentelemetry-api>=1.24.0",
  "opentelemetry-sdk>=1.24.0",
  # Archive
  "zipfile36>=0.1.3",
]

[project.optional-dependencies]
ai = [
  "anthropic>=0.25.0",
  "openai>=1.14.0",
]
dev = [
  "pytest>=8.1.0",
  "pytest-asyncio>=0.23.0",
  "pytest-cov>=5.0.0",
  "pytest-timeout>=2.3.1",
  "pytest-benchmark>=4.0.0",
  "pytest-xdist>=3.5.0",      # parallel test execution
  "hypothesis>=6.98.0",
  "mypy>=1.9.0",
  "ruff>=0.3.0",
  "import-linter>=2.0",       # enforce module boundaries (Rule 5)
  "black>=24.3.0",
]
conformance = [
  # Downloaded separately via scripts/download_conformance.sh, not pip
  # But test harness deps:
  "pytest-xdist>=3.5.0",
  "tabulate>=0.9.0",          # conformance result tables
]

[project.scripts]
xbrl-validate = "src.cli.main:app"
xbrl-taxonomy = "src.cli.taxonomy:app"
xbrl-conform  = "src.cli.conform:app"
```

**Dependency notes:**
- `elementpath` replaces the "implement XPath subset" from v2.0 — reinventing XPath 2.0 is a two-year project on its own.
- `html5lib` is required because real iXBRL filings are HTML5, not XHTML. lxml.html alone breaks on them.
- `isodate` for XML Schema `xs:duration` parsing — Python stdlib doesn't handle ISO 8601 durations.
- `diskcache` for taxonomy cache — handles concurrent access safely, unlike naive filesystem caching.
- `import-linter` enforces Rule 5 (regulator isolation) as a CI gate.

---
## 3. COMPLETE FILE TREE

The agent MUST create every file listed. Tree is organized by module.

```text
xbrl-validator/
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── Makefile
├── Dockerfile
├── Dockerfile.worker
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .importlinter              # enforces Rule 5
├── README.md
├── LICENSE                     # MIT
├── CHANGELOG.md
│
├── docs/
│   ├── architecture.md
│   ├── arelle_compat.md        # mandatory per Rule 14
│   ├── conformance.md          # conformance suite strategy
│   ├── error_codes.md          # generated from registry
│   ├── plugin_authoring.md
│   ├── regulator_profiles.md
│   ├── large_files.md          # streaming architecture
│   ├── performance.md          # benchmarks + tuning
│   └── security.md             # threat model
│
├── config/
│   ├── default.yaml
│   ├── error_codes.yaml        # FULL error registry (~800 entries)
│   ├── profiles/
│   │   ├── index.yaml
│   │   ├── efm/                # SEC EDGAR Filer Manual
│   │   │   ├── profile.yaml
│   │   │   ├── mandatory_elements.yaml
│   │   │   ├── dei_rules.yaml
│   │   │   ├── naming_rules.yaml
│   │   │   ├── negation_rules.yaml       # NEGVAL catalog
│   │   │   ├── structural_rules.yaml
│   │   │   ├── hidden_fact_rules.yaml
│   │   │   ├── period_rules.yaml
│   │   │   ├── share_class_rules.yaml
│   │   │   ├── role_hierarchy_rules.yaml
│   │   │   ├── presentation_rules.yaml
│   │   │   ├── label_rules.yaml
│   │   │   ├── ixbrl_rules.yaml          # EFM 6.20.x
│   │   │   ├── form_specific/
│   │   │   │   ├── 10-k.yaml
│   │   │   │   ├── 10-q.yaml
│   │   │   │   ├── 8-k.yaml
│   │   │   │   ├── s-1.yaml
│   │   │   │   └── 20-f.yaml
│   │   │   └── version_map.yaml          # EFM version ↔ us-gaap version
│   │   ├── esef/               # ESMA European Single Electronic Format
│   │   │   ├── profile.yaml
│   │   │   ├── mandatory_tags.yaml
│   │   │   ├── anchoring_rules.yaml
│   │   │   ├── package_rules.yaml
│   │   │   ├── block_tagging_rules.yaml
│   │   │   ├── lei_rules.yaml
│   │   │   ├── calc_1_1_rules.yaml       # Calc 1.1 required for ESEF 2024+
│   │   │   ├── signed_package_rules.yaml
│   │   │   └── version_map.yaml          # ESEF year ↔ IFRS version
│   │   ├── ferc/               # US FERC Forms 1/2/3/6/60/714
│   │   │   ├── profile.yaml
│   │   │   ├── xule_rules/
│   │   │   │   ├── form1.xule
│   │   │   │   ├── form2.xule
│   │   │   │   ├── form3.xule
│   │   │   │   ├── form6.xule
│   │   │   │   ├── form60.xule
│   │   │   │   ├── form714.xule
│   │   │   │   └── common.xule
│   │   │   └── mandatory_schedules.yaml
│   │   ├── hmrc/               # UK HMRC CT600
│   │   │   ├── profile.yaml
│   │   │   ├── mandatory_elements.yaml
│   │   │   ├── ct600_rules.yaml
│   │   │   └── companies_house_rules.yaml
│   │   ├── cipc/               # South Africa CIPC
│   │   │   ├── profile.yaml
│   │   │   ├── mandatory_elements.yaml
│   │   │   ├── entity_classification.yaml
│   │   │   └── ifrs_for_sme_rules.yaml
│   │   ├── mca/                # India MCA21
│   │   │   ├── profile.yaml
│   │   │   ├── mandatory_elements.yaml
│   │   │   ├── cin_rules.yaml
│   │   │   ├── din_rules.yaml
│   │   │   └── ind_as_rules.yaml
│   │   └── custom/             # user-defined profile template
│   │       ├── profile.yaml.template
│   │       └── README.md
│   ├── transforms/
│   │   ├── ixt-1.json          # legacy
│   │   ├── ixt-2.json
│   │   ├── ixt-3.json
│   │   ├── ixt-4.json
│   │   ├── ixt-5.json          # current
│   │   └── ixt-sec.json        # SEC-specific transforms
│   ├── utr/                    # Units Registry
│   │   ├── utr-iso4217.xml
│   │   ├── utr-non-iso.xml
│   │   └── utr-registry.yaml   # parsed/indexed form
│   ├── lrr/                    # Link Role Registry
│   │   └── lrr.xml
│   └── enumerations/
│       └── extensible-enumerations-2.0.xsd
│
├── src/
│   ├── __init__.py
│   │
│   ├── core/                   # no regulator imports allowed (Rule 5)
│   │   ├── __init__.py
│   │   ├── constants.py
│   │   ├── exceptions.py
│   │   ├── types.py
│   │   ├── qname.py
│   │   │
│   │   ├── parser/
│   │   │   ├── __init__.py
│   │   │   ├── format_detector.py
│   │   │   ├── xml_parser.py
│   │   │   ├── ixbrl_parser.py
│   │   │   ├── ixbrl_transforms.py       # applies ixt:* transforms
│   │   │   ├── ixbrl_continuation.py     # continuation chain resolver
│   │   │   ├── json_parser.py            # XBRL-JSON (OIM)
│   │   │   ├── csv_parser.py             # XBRL-CSV (OIM)
│   │   │   ├── transform_registry.py
│   │   │   ├── decimal_parser.py         # Rule 16: safe Decimal parsing
│   │   │   ├── datetime_parser.py        # XML Schema dateTime
│   │   │   ├── package_parser.py         # Taxonomy package ZIP
│   │   │   └── streaming/
│   │   │       ├── __init__.py
│   │   │       ├── sax_handler.py
│   │   │       ├── sax_ixbrl_handler.py
│   │   │       ├── json_streamer.py
│   │   │       ├── csv_streamer.py
│   │   │       ├── memory_budget.py
│   │   │       ├── fact_index.py
│   │   │       ├── fact_store.py
│   │   │       ├── disk_spill.py
│   │   │       ├── mmap_reader.py
│   │   │       ├── chunked_reader.py
│   │   │       ├── storage_detector.py   # SSD vs HDD detection
│   │   │       └── counting_wrapper.py   # byte-offset tracking
│   │   │
│   │   ├── taxonomy/
│   │   │   ├── __init__.py
│   │   │   ├── resolver.py
│   │   │   ├── cache.py                  # 3-tier cache
│   │   │   ├── cache_keys.py             # SHA256-based versioned keys
│   │   │   ├── catalog.py                # XML catalog (OASIS)
│   │   │   ├── package.py                # Taxonomy Packages 1.0
│   │   │   ├── package_metadata.py       # taxonomyPackage.xml parser
│   │   │   ├── concept_index.py
│   │   │   ├── dts.py                    # DTS discovery + closure
│   │   │   ├── version_map.py            # cross-version concept mapping
│   │   │   ├── lrr_registry.py           # Link Role Registry
│   │   │   ├── utr_registry.py           # Units Registry
│   │   │   └── fetcher.py                # HTTP fetch with allow-list
│   │   │
│   │   ├── model/
│   │   │   ├── __init__.py
│   │   │   ├── xbrl_model.py             # top-level model
│   │   │   ├── concept.py
│   │   │   ├── context.py
│   │   │   ├── unit.py
│   │   │   ├── fact.py
│   │   │   ├── footnote.py
│   │   │   ├── period.py
│   │   │   ├── entity.py
│   │   │   ├── arc.py
│   │   │   ├── linkbase.py
│   │   │   ├── hypercube.py
│   │   │   ├── dimension.py
│   │   │   ├── role_type.py
│   │   │   ├── arcrole_type.py
│   │   │   ├── label.py
│   │   │   ├── reference.py
│   │   │   ├── builder.py                # DOM builder
│   │   │   ├── builder_streaming.py      # streaming builder
│   │   │   ├── builder_oim.py            # OIM (JSON/CSV) builder
│   │   │   ├── indexes.py
│   │   │   ├── merge.py
│   │   │   ├── equivalence.py            # OIM fact equivalence
│   │   │   └── oim_model.py              # canonical OIM fact model
│   │   │
│   │   └── networks/                     # relationship networks
│   │       ├── __init__.py
│   │       ├── base_set.py               # base set computation
│   │       ├── relationship_set.py
│   │       ├── prohibition.py            # prohibition/override resolution
│   │       ├── presentation_network.py
│   │       ├── calculation_network.py
│   │       ├── definition_network.py
│   │       ├── label_network.py
│   │       ├── reference_network.py
│   │       └── generic_network.py        # Generic Links
│   │
│   ├── validator/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── pipeline.py
│   │   ├── pipeline_config.py
│   │   ├── error_catalog.py
│   │   ├── message.py
│   │   ├── self_check.py
│   │   ├── dedup.py                      # error deduplication
│   │   │
│   │   ├── spec/                         # no regulator imports (Rule 5)
│   │   │   ├── __init__.py
│   │   │   │
│   │   │   ├── xbrl21/                   # XBRL 2.1 (25 checks)
│   │   │   │   ├── __init__.py
│   │   │   │   ├── instance.py           # instance-level rules
│   │   │   │   ├── context.py            # context validation
│   │   │   │   ├── unit.py               # unit validation
│   │   │   │   ├── fact.py               # fact validation
│   │   │   │   ├── tuple.py              # tuple validation
│   │   │   │   ├── footnote.py
│   │   │   │   └── schema_ref.py
│   │   │   │
│   │   │   ├── dimensions/               # XDT 1.0 (FULL)
│   │   │   │   ├── __init__.py
│   │   │   │   ├── hypercube.py          # hypercube inheritance
│   │   │   │   ├── domain_member.py      # domain-member network walk
│   │   │   │   ├── typed_dimension.py    # xs:simpleType validation
│   │   │   │   ├── dimension_default.py
│   │   │   │   ├── target_role.py        # targetRole traversal
│   │   │   │   ├── usable.py             # usable attribute
│   │   │   │   ├── all_notall.py         # all/notAll arc semantics
│   │   │   │   ├── closed_hypercube.py
│   │   │   │   └── context_validator.py  # context against hypercube
│   │   │   │
│   │   │   ├── calculation/              # Calc 1.0 + Calc 1.1
│   │   │   │   ├── __init__.py
│   │   │   │   ├── classic.py            # XBRL 2.1 §5.2.5
│   │   │   │   ├── calc_1_1.py           # Calculation 1.1 (2023)
│   │   │   │   ├── tolerance.py          # decimal-based tolerance
│   │   │   │   ├── rounding.py
│   │   │   │   ├── duplicate_handler.py  # duplicate fact rounding (1.1)
│   │   │   │   └── network_walker.py     # inclusive / exclusive summation
│   │   │   │
│   │   │   ├── formula/                  # Formula 1.0 FULL
│   │   │   │   ├── __init__.py
│   │   │   │   ├── evaluator.py
│   │   │   │   ├── assertion.py          # value/existence/consistency
│   │   │   │   ├── variable_set.py
│   │   │   │   ├── variable.py
│   │   │   │   ├── precondition.py
│   │   │   │   ├── message.py            # formula messages
│   │   │   │   ├── filters/
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── concept_filter.py
│   │   │   │   │   ├── period_filter.py
│   │   │   │   │   ├── dimension_filter.py
│   │   │   │   │   ├── general_filter.py
│   │   │   │   │   ├── match_filter.py
│   │   │   │   │   ├── relative_filter.py
│   │   │   │   │   ├── tuple_filter.py
│   │   │   │   │   ├── unit_filter.py
│   │   │   │   │   ├── entity_filter.py
│   │   │   │   │   ├── boolean_filter.py
│   │   │   │   │   └── value_filter.py
│   │   │   │   ├── aspect_cover.py
│   │   │   │   ├── aspect_rule.py
│   │   │   │   ├── generator.py          # formula generators
│   │   │   │   ├── custom_function.py
│   │   │   │   ├── xpath_bridge.py       # elementpath integration
│   │   │   │   └── xpath_functions.py    # XBRL Functions Registry
│   │   │   │
│   │   │   ├── inline/                   # iXBRL 1.1 (FULL)
│   │   │   │   ├── __init__.py
│   │   │   │   ├── header.py
│   │   │   │   ├── non_fraction.py
│   │   │   │   ├── non_numeric.py
│   │   │   │   ├── fraction.py
│   │   │   │   ├── tuple.py
│   │   │   │   ├── continuation.py
│   │   │   │   ├── exclude.py
│   │   │   │   ├── reference.py
│   │   │   │   ├── relationship.py
│   │   │   │   ├── footnote.py
│   │   │   │   ├── hidden.py
│   │   │   │   ├── transforms.py         # validates transform applicability
│   │   │   │   └── target_document.py    # multi-target iXBRL
│   │   │   │
│   │   │   ├── table/                    # Table Linkbase 1.0 FULL
│   │   │   │   ├── __init__.py
│   │   │   │   ├── table_model.py
│   │   │   │   ├── breakdown.py
│   │   │   │   ├── axis.py
│   │   │   │   ├── rule_node.py
│   │   │   │   ├── concept_relationship_node.py
│   │   │   │   ├── dimension_relationship_node.py
│   │   │   │   ├── aspect_node.py
│   │   │   │   ├── structural_layout.py
│   │   │   │   ├── fact_layout.py
│   │   │   │   ├── renderer.py           # produces rendered table
│   │   │   │   └── validator.py
│   │   │   │
│   │   │   ├── label/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── label_validator.py
│   │   │   │   ├── uniqueness.py
│   │   │   │   └── language.py
│   │   │   │
│   │   │   ├── presentation/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── network_validator.py
│   │   │   │   ├── ordering.py
│   │   │   │   └── preferred_label.py
│   │   │   │
│   │   │   ├── definition/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── network_validator.py
│   │   │   │   ├── general_special.py
│   │   │   │   ├── essence_alias.py
│   │   │   │   ├── similar_tuples.py
│   │   │   │   └── requires_element.py
│   │   │   │
│   │   │   ├── reference/
│   │   │   │   ├── __init__.py
│   │   │   │   └── reference_validator.py
│   │   │   │
│   │   │   ├── generic/                  # Generic Links 1.0
│   │   │   │   ├── __init__.py
│   │   │   │   ├── generic_link.py
│   │   │   │   ├── generic_label.py
│   │   │   │   └── generic_reference.py
│   │   │   │
│   │   │   ├── enumerations/             # Extensible Enumerations 2.0
│   │   │   │   ├── __init__.py
│   │   │   │   ├── enum_validator.py
│   │   │   │   └── enum_set_validator.py
│   │   │   │
│   │   │   ├── oim/                      # Open Information Model
│   │   │   │   ├── __init__.py
│   │   │   │   ├── canonical_model.py
│   │   │   │   ├── fact_equivalence.py
│   │   │   │   ├── json_validator.py     # XBRL-JSON spec conformance
│   │   │   │   ├── csv_validator.py      # XBRL-CSV spec conformance
│   │   │   │   ├── round_trip.py         # XML↔JSON↔CSV round-trip check
│   │   │   │   └── report_info.py
│   │   │   │
│   │   │   └── versioning/               # Versioning Report 1.0
│   │   │       ├── __init__.py
│   │   │       └── versioning_validator.py
│   │   │
│   │   └── regulator/                    # dynamically loaded
│   │       ├── __init__.py
│   │       ├── efm/
│   │       │   ├── __init__.py
│   │       │   ├── efm_validator.py      # orchestrator
│   │       │   ├── dei.py                # cover page DEI rules
│   │       │   ├── cik.py                # CIK scheme + format
│   │       │   ├── negation.py           # NEGVAL logic
│   │       │   ├── naming.py             # extension naming
│   │       │   ├── period.py             # period-of-report rules
│   │       │   ├── share_class.py
│   │       │   ├── role_hierarchy.py
│   │       │   ├── presentation.py       # SEC-specific pres rules
│   │       │   ├── label.py              # SEC label uniqueness
│   │       │   ├── hidden_facts.py
│   │       │   ├── structural.py
│   │       │   ├── ixbrl.py              # EFM 6.20.x
│   │       │   ├── form_router.py        # routes by form type
│   │       │   └── forms/
│   │       │       ├── form_10k.py
│   │       │       ├── form_10q.py
│   │       │       ├── form_8k.py
│   │       │       ├── form_s1.py
│   │       │       └── form_20f.py
│   │       ├── esef/
│   │       │   ├── __init__.py
│   │       │   ├── esef_validator.py
│   │       │   ├── package.py
│   │       │   ├── signed_package.py     # XAdES signature verification
│   │       │   ├── anchoring.py          # full anchoring rules
│   │       │   ├── mandatory_tags.py
│   │       │   ├── block_tagging.py
│   │       │   ├── lei.py
│   │       │   ├── language.py
│   │       │   ├── html_profile.py       # ESEF HTML profile
│   │       │   └── report_package.py     # rp.json format
│   │       ├── ferc/
│   │       │   ├── __init__.py
│   │       │   ├── ferc_validator.py
│   │       │   ├── xule_runner.py
│   │       │   └── schedule_router.py
│   │       ├── hmrc/
│   │       │   ├── __init__.py
│   │       │   ├── hmrc_validator.py
│   │       │   ├── ct600.py
│   │       │   └── companies_house.py
│   │       ├── cipc/
│   │       │   ├── __init__.py
│   │       │   ├── cipc_validator.py
│   │       │   ├── entity_class.py
│   │       │   └── ifrs_sme.py
│   │       ├── mca/
│   │       │   ├── __init__.py
│   │       │   ├── mca_validator.py
│   │       │   ├── cin.py
│   │       │   ├── din.py
│   │       │   └── ind_as.py
│   │       └── custom.py
│   │
│   ├── xule/                             # FULL XULE implementation
│   │   ├── __init__.py
│   │   ├── lexer.py
│   │   ├── parser.py
│   │   ├── ast_nodes.py
│   │   ├── compiler.py
│   │   ├── evaluator.py
│   │   ├── query_planner.py
│   │   ├── factset.py                    # factset algebra
│   │   ├── aspect.py                     # aspect binding model
│   │   ├── navigation.py                 # linkbase navigation
│   │   ├── calendar.py                   # time-period arithmetic
│   │   ├── namespace_values.py
│   │   ├── custom_functions.py
│   │   ├── builtins.py
│   │   ├── output.py                     # XULE output/result model
│   │   ├── rule_set_loader.py
│   │   └── xpath_interop.py
│   │
│   ├── ai/                               # v1.2 scope, stub in v1.0
│   │   ├── __init__.py
│   │   ├── fix_suggester.py
│   │   ├── template_suggestions.py       # deterministic templates
│   │   ├── llm_suggestions.py            # optional LLM fallback
│   │   ├── cross_doc.py
│   │   ├── business_rules.py
│   │   ├── tagging_analyzer.py
│   │   └── confidence.py
│   │
│   ├── report/
│   │   ├── __init__.py
│   │   ├── generator.py
│   │   ├── json_report.py
│   │   ├── sarif_report.py
│   │   ├── html_report.py
│   │   ├── csv_report.py
│   │   ├── junit_report.py               # for CI pipelines
│   │   ├── arelle_compat_report.py       # Arelle-style output
│   │   └── templates/
│   │       ├── report.html.j2
│   │       ├── summary.html.j2
│   │       └── error_detail.html.j2
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── routes.py
│   │   ├── middleware.py
│   │   ├── auth.py
│   │   ├── rate_limit.py
│   │   ├── websocket.py
│   │   ├── worker.py                     # Celery tasks
│   │   ├── schemas.py
│   │   ├── health.py
│   │   └── metrics.py                    # Prometheus
│   │
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── main.py                       # xbrl-validate
│   │   ├── taxonomy.py                   # xbrl-taxonomy (preload/inspect)
│   │   ├── conform.py                    # xbrl-conform (run conformance)
│   │   ├── progress.py
│   │   ├── formatters.py
│   │   └── diagnostics.py                # --diag mode
│   │
│   ├── plugin/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── loader.py
│   │   ├── profile_loader.py
│   │   ├── rule_compiler.py
│   │   ├── yaml_rules/
│   │   │   ├── __init__.py
│   │   │   ├── mandatory_element.py
│   │   │   ├── value_constraint.py
│   │   │   ├── cross_concept.py
│   │   │   ├── naming_convention.py
│   │   │   ├── structural.py
│   │   │   └── negation.py
│   │   └── rule_types.py
│   │
│   ├── security/
│   │   ├── __init__.py
│   │   ├── xxe_guard.py
│   │   ├── zip_guard.py                  # zip bomb protection
│   │   ├── url_allowlist.py
│   │   └── entity_limits.py
│   │
│   └── utils/
│       ├── __init__.py
│       ├── datetime_utils.py
│       ├── xml_utils.py
│       ├── hash_utils.py
│       ├── size_utils.py
│       ├── decimal_utils.py              # Decimal helpers
│       ├── locale_utils.py
│       ├── zip_utils.py
│       └── logging_config.py
│
├── conformance/                          # conformance suite runner
│   ├── README.md
│   ├── suites/                           # downloaded, gitignored
│   │   ├── xbrl-2.1/
│   │   ├── dimensions-1.0/
│   │   ├── formula-1.0/
│   │   ├── calculation-1.1/
│   │   ├── inline-1.1/
│   │   ├── table-1.0/
│   │   ├── enumerations-2.0/
│   │   ├── taxonomy-packages-1.0/
│   │   ├── oim-1.0/
│   │   └── generic-links-1.0/
│   ├── runner.py
│   ├── suite_config.yaml
│   ├── result_comparator.py
│   ├── expected_results.py
│   ├── results.json                      # latest run results
│   ├── history/                          # historical results
│   └── reports/
│       ├── pass_rate.md                  # per-suite pass rates
│       └── diff_from_arelle.md           # where we differ from Arelle
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── factories.py
│   │
│   ├── unit/                             # mirror src/ structure
│   │   ├── core/
│   │   │   ├── parser/
│   │   │   │   ├── test_format_detector.py
│   │   │   │   ├── test_xml_parser.py
│   │   │   │   ├── test_ixbrl_parser.py
│   │   │   │   ├── test_ixbrl_transforms.py
│   │   │   │   ├── test_ixbrl_continuation.py
│   │   │   │   ├── test_json_parser.py
│   │   │   │   ├── test_csv_parser.py
│   │   │   │   ├── test_decimal_parser.py
│   │   │   │   ├── test_datetime_parser.py
│   │   │   │   ├── test_package_parser.py
│   │   │   │   └── streaming/
│   │   │   │       ├── test_sax_handler.py
│   │   │   │       ├── test_sax_ixbrl_handler.py
│   │   │   │       ├── test_json_streamer.py
│   │   │   │       ├── test_csv_streamer.py
│   │   │   │       ├── test_memory_budget.py
│   │   │   │       ├── test_fact_index.py
│   │   │   │       ├── test_fact_store.py
│   │   │   │       ├── test_disk_spill.py
│   │   │   │       ├── test_mmap_reader.py
│   │   │   │       ├── test_chunked_reader.py
│   │   │   │       └── test_storage_detector.py
│   │   │   ├── taxonomy/
│   │   │   │   ├── test_resolver.py
│   │   │   │   ├── test_cache.py
│   │   │   │   ├── test_catalog.py
│   │   │   │   ├── test_package.py
│   │   │   │   ├── test_dts.py
│   │   │   │   ├── test_version_map.py
│   │   │   │   ├── test_lrr_registry.py
│   │   │   │   └── test_utr_registry.py
│   │   │   ├── model/
│   │   │   │   ├── test_builder.py
│   │   │   │   ├── test_builder_streaming.py
│   │   │   │   ├── test_builder_oim.py
│   │   │   │   ├── test_merge.py
│   │   │   │   ├── test_equivalence.py
│   │   │   │   ├── test_context.py
│   │   │   │   ├── test_unit.py
│   │   │   │   └── test_fact.py
│   │   │   └── networks/
│   │   │       ├── test_base_set.py
│   │   │       ├── test_prohibition.py
│   │   │       ├── test_presentation_network.py
│   │   │       ├── test_calculation_network.py
│   │   │       └── test_definition_network.py
│   │   ├── validator/
│   │   │   ├── spec/
│   │   │   │   ├── test_xbrl21_*.py      # one per xbrl21/*.py
│   │   │   │   ├── test_dimensions_*.py
│   │   │   │   ├── test_calculation_classic.py
│   │   │   │   ├── test_calculation_1_1.py
│   │   │   │   ├── test_formula_*.py
│   │   │   │   ├── test_inline_*.py
│   │   │   │   ├── test_table_*.py
│   │   │   │   ├── test_label_*.py
│   │   │   │   ├── test_presentation_*.py
│   │   │   │   ├── test_definition_*.py
│   │   │   │   ├── test_enumerations.py
│   │   │   │   ├── test_oim_*.py
│   │   │   │   └── test_versioning.py
│   │   │   └── test_pipeline.py
│   │   ├── regulator/
│   │   │   ├── efm/
│   │   │   │   ├── test_efm_validator.py
│   │   │   │   ├── test_dei.py
│   │   │   │   ├── test_cik.py
│   │   │   │   ├── test_negation.py
│   │   │   │   ├── test_naming.py
│   │   │   │   ├── test_period.py
│   │   │   │   ├── test_share_class.py
│   │   │   │   ├── test_ixbrl.py
│   │   │   │   └── forms/
│   │   │   │       ├── test_form_10k.py
│   │   │   │       ├── test_form_10q.py
│   │   │   │       ├── test_form_8k.py
│   │   │   │       └── test_form_20f.py
│   │   │   ├── esef/
│   │   │   │   ├── test_esef_validator.py
│   │   │   │   ├── test_package.py
│   │   │   │   ├── test_signed_package.py
│   │   │   │   ├── test_anchoring.py
│   │   │   │   ├── test_mandatory_tags.py
│   │   │   │   ├── test_block_tagging.py
│   │   │   │   ├── test_lei.py
│   │   │   │   └── test_html_profile.py
│   │   │   ├── ferc/
│   │   │   │   ├── test_ferc_validator.py
│   │   │   │   ├── test_xule_runner.py
│   │   │   │   └── test_form1_rules.py
│   │   │   ├── hmrc/test_*.py
│   │   │   ├── cipc/test_*.py
│   │   │   └── mca/test_*.py
│   │   ├── xule/
│   │   │   ├── test_lexer.py
│   │   │   ├── test_parser.py
│   │   │   ├── test_compiler.py
│   │   │   ├── test_evaluator.py
│   │   │   ├── test_query_planner.py
│   │   │   ├── test_factset.py
│   │   │   ├── test_aspect.py
│   │   │   ├── test_navigation.py
│   │   │   ├── test_calendar.py
│   │   │   └── test_custom_functions.py
│   │   ├── ai/
│   │   │   ├── test_template_suggestions.py
│   │   │   ├── test_llm_suggestions.py
│   │   │   ├── test_cross_doc.py
│   │   │   ├── test_business_rules.py
│   │   │   └── test_tagging_analyzer.py
│   │   ├── report/
│   │   │   ├── test_json_report.py
│   │   │   ├── test_sarif_report.py
│   │   │   ├── test_html_report.py
│   │   │   ├── test_csv_report.py
│   │   │   ├── test_junit_report.py
│   │   │   └── test_arelle_compat_report.py
│   │   └── security/
│   │       ├── test_xxe_guard.py
│   │       ├── test_zip_guard.py
│   │       ├── test_url_allowlist.py
│   │       └── test_entity_limits.py
│   │
│   ├── integration/
│   │   ├── test_pipeline_efm.py
│   │   ├── test_pipeline_esef.py
│   │   ├── test_pipeline_ferc.py
│   │   ├── test_pipeline_hmrc.py
│   │   ├── test_pipeline_cipc.py
│   │   ├── test_pipeline_mca.py
│   │   ├── test_pipeline_inline.py
│   │   ├── test_pipeline_oim_json.py
│   │   ├── test_pipeline_oim_csv.py
│   │   ├── test_pipeline_multidoc.py
│   │   ├── test_round_trip_oim.py
│   │   ├── test_api_endpoints.py
│   │   ├── test_cli.py
│   │   └── test_taxonomy_preload.py
│   │
│   ├── large_file/
│   │   ├── conftest.py
│   │   ├── test_streaming_xml_200mb.py
│   │   ├── test_streaming_xml_1gb.py
│   │   ├── test_streaming_xml_5gb.py
│   │   ├── test_streaming_ixbrl_200mb.py
│   │   ├── test_streaming_json_500mb.py
│   │   ├── test_streaming_csv_1gb.py
│   │   ├── test_memory_budget_enforcement.py
│   │   ├── test_disk_spill_correctness.py
│   │   ├── test_disk_spill_performance.py
│   │   ├── test_mmap_random_access.py
│   │   ├── test_chunked_hdd_read.py
│   │   ├── test_million_facts.py
│   │   ├── test_10m_facts.py
│   │   ├── test_50m_facts.py
│   │   ├── test_threshold_boundaries.py  # 99MB / 101MB / 999MB / 1001MB
│   │   └── generators/
│   │       ├── xbrl_generator.py
│   │       ├── ixbrl_generator.py
│   │       ├── json_generator.py
│   │       ├── csv_generator.py
│   │       └── fact_generator.py
│   │
│   ├── security/
│   │   ├── test_xxe_attacks.py
│   │   ├── test_billion_laughs.py
│   │   ├── test_quadratic_blowup.py
│   │   ├── test_zip_bombs.py
│   │   ├── test_path_traversal.py
│   │   └── test_ssrf.py                  # taxonomy fetch SSRF
│   │
│   ├── conformance/                      # official suite harness
│   │   ├── conftest.py
│   │   ├── test_xbrl21_conformance.py
│   │   ├── test_dimensions_conformance.py
│   │   ├── test_calculation_11_conformance.py
│   │   ├── test_formula_conformance.py
│   │   ├── test_inline_conformance.py
│   │   ├── test_table_conformance.py
│   │   ├── test_enumerations_conformance.py
│   │   ├── test_oim_conformance.py
│   │   └── test_taxonomy_package_conformance.py
│   │
│   ├── e2e/
│   │   ├── test_real_sec_10k.py
│   │   ├── test_real_sec_10q.py
│   │   ├── test_real_sec_8k.py
│   │   ├── test_real_esef_annual.py
│   │   ├── test_real_ferc_form1.py
│   │   ├── test_real_ferc_form714.py
│   │   ├── test_real_hmrc_ct600.py
│   │   ├── test_real_cipc_afs.py
│   │   ├── test_real_mca_aoc4.py
│   │   └── corpus/                       # gitignored, downloaded
│   │
│   ├── property/                         # hypothesis-based
│   │   ├── test_decimal_arithmetic.py
│   │   ├── test_fact_equivalence.py
│   │   ├── test_oim_round_trip.py
│   │   └── test_context_equality.py
│   │
│   ├── benchmarks/
│   │   ├── bench_parsing.py
│   │   ├── bench_taxonomy_load.py
│   │   ├── bench_calculation.py
│   │   ├── bench_formula.py
│   │   ├── bench_xule.py
│   │   └── bench_pipeline.py
│   │
│   └── fixtures/
│       ├── valid/                        # curated valid instances
│       ├── invalid/                      # curated invalid instances, one per error code
│       ├── taxonomies/                   # small test taxonomies
│       ├── packages/                     # test taxonomy packages (ZIPs)
│       ├── catalogs/                     # test XML catalogs
│       └── security/                     # attack payloads
│
└── scripts/
    ├── download_conformance.sh           # downloads all XII conformance suites
    ├── download_corpus.sh                # downloads SEC/ESEF/FERC sample filings
    ├── preload_taxonomies.py             # preload us-gaap, IFRS, FERC, etc.
    ├── generate_rule_catalog.py          # generate docs/error_codes.md
    ├── generate_large_fixtures.py        # generate multi-GB test files
    ├── benchmark.py                      # run full benchmark suite
    ├── arelle_compare.py                 # diff our output vs Arelle
    ├── check_error_codes.py              # CI: registry ↔ emitted code cross-check
    ├── check_imports.py                  # CI: import-linter wrapper
    └── build_utr_cache.py                # parse UTR XML → YAML index
```

**File count breakdown:**
- Source (`src/`): ~280 files
- Config (`config/`): ~60 files
- Tests (`tests/`): ~200 files
- Conformance harness: ~15 files
- Docs + scripts + root: ~30 files
- **Total: ~585 files** (v2 claimed 145; this is realistic for scope)

---
## 4. CONSTANTS, TYPES, EXCEPTIONS

### 4A — `src/core/constants.py`

```text
NAMESPACES (all current spec versions):
  NS_XBRLI           = "http://www.xbrl.org/2003/instance"
  NS_LINK            = "http://www.xbrl.org/2003/linkbase"
  NS_XLINK           = "http://www.w3.org/1999/xlink"
  NS_XSD             = "http://www.w3.org/2001/XMLSchema"
  NS_XSI             = "http://www.w3.org/2001/XMLSchema-instance"
  NS_IX              = "http://www.xbrl.org/2013/inlineXBRL"
  NS_IXT_PREFIX      = "http://www.xbrl.org/inlineXBRL/transformation"
  NS_ISO4217         = "http://www.xbrl.org/2003/iso4217"
  NS_XBRLDI          = "http://xbrl.org/2006/xbrldi"
  NS_XBRLDT          = "http://xbrl.org/2005/xbrldt"
  NS_XL              = "http://www.xbrl.org/2003/XLink"
  NS_GEN             = "http://xbrl.org/2008/generic"
  NS_FORMULA         = "http://xbrl.org/2008/formula"
  NS_VARIABLE        = "http://xbrl.org/2008/variable"
  NS_VALIDATION      = "http://xbrl.org/2008/validation"
  NS_ASSERTION       = "http://xbrl.org/2008/assertion"
  NS_VA              = "http://xbrl.org/2008/assertion/value"
  NS_EA              = "http://xbrl.org/2008/assertion/existence"
  NS_CA              = "http://xbrl.org/2008/assertion/consistency"
  NS_TABLE           = "http://xbrl.org/2014/table"
  NS_ENUM2           = "http://xbrl.org/2020/extensible-enumerations-2.0"
  NS_ESEF_TAXONOMY   = "http://www.esma.europa.eu/taxonomy/"
  NS_ESEF_ARCROLE    = "http://www.esma.europa.eu/xbrl/esef/arcrole/"
  NS_UTR             = "http://www.xbrl.org/2009/utr"
  NS_LRR             = "http://www.xbrl.org/2005/lrr"
  NS_OIM             = "https://xbrl.org/2021"

ARCROLES (core + dimensions + ESEF + formula + table):
  ARCROLE_SUMMATION_ITEM     = "http://www.xbrl.org/2003/arcrole/summation-item"
  ARCROLE_SUMMATION_ITEM_1_1 = "https://xbrl.org/2023/arcrole/summation-item"  # Calc 1.1
  ARCROLE_PARENT_CHILD       = "http://www.xbrl.org/2003/arcrole/parent-child"
  ARCROLE_DOMAIN_MEMBER      = "http://xbrl.org/int/dim/arcrole/domain-member"
  ARCROLE_DIMENSION_DOMAIN   = "http://xbrl.org/int/dim/arcrole/dimension-domain"
  ARCROLE_DIMENSION_DEFAULT  = "http://xbrl.org/int/dim/arcrole/dimension-default"
  ARCROLE_HYPERCUBE_DIM      = "http://xbrl.org/int/dim/arcrole/hypercube-dimension"
  ARCROLE_ALL                = "http://xbrl.org/int/dim/arcrole/all"
  ARCROLE_NOT_ALL            = "http://xbrl.org/int/dim/arcrole/notAll"
  ARCROLE_WIDER_NARROWER     = "http://www.esma.europa.eu/xbrl/esef/arcrole/wider-narrower"
  ARCROLE_CONCEPT_LABEL      = "http://www.xbrl.org/2003/arcrole/concept-label"
  ARCROLE_CONCEPT_REFERENCE  = "http://www.xbrl.org/2003/arcrole/concept-reference"
  ARCROLE_FACT_FOOTNOTE      = "http://www.xbrl.org/2003/arcrole/fact-footnote"
  ARCROLE_GENERAL_SPECIAL    = "http://www.xbrl.org/2003/arcrole/general-special"
  ARCROLE_ESSENCE_ALIAS      = "http://www.xbrl.org/2003/arcrole/essence-alias"
  ARCROLE_SIMILAR_TUPLES     = "http://www.xbrl.org/2003/arcrole/similar-tuples"
  ARCROLE_REQUIRES_ELEMENT   = "http://www.xbrl.org/2003/arcrole/requires-element"
  # Formula arcroles
  ARCROLE_VARIABLE_SET       = "http://xbrl.org/arcrole/2008/variable-set"
  ARCROLE_VARIABLE_FILTER    = "http://xbrl.org/arcrole/2008/variable-filter"
  ARCROLE_VARIABLE_SET_FILTER = "http://xbrl.org/arcrole/2008/variable-set-filter"
  ARCROLE_VARIABLE_SET_PRECOND = "http://xbrl.org/arcrole/2008/variable-set-precondition"
  ARCROLE_CONSISTENCY_ASSERT = "http://xbrl.org/arcrole/2008/consistency-assertion-formula"
  ARCROLE_ASSERTION_SET      = "http://xbrl.org/arcrole/2008/assertion-set"
  # Table arcroles
  ARCROLE_TABLE_BREAKDOWN    = "http://xbrl.org/arcrole/2014/table-breakdown"
  ARCROLE_BREAKDOWN_TREE     = "http://xbrl.org/arcrole/2014/breakdown-tree"
  ARCROLE_TABLE_FILTER       = "http://xbrl.org/arcrole/2014/table-filter"
  ARCROLE_TABLE_PARAMETER    = "http://xbrl.org/arcrole/2014/table-parameter"
  # Generic
  ARCROLE_ELEMENT_LABEL      = "http://xbrl.org/arcrole/2008/element-label"
  ARCROLE_ELEMENT_REFERENCE  = "http://xbrl.org/arcrole/2008/element-reference"

STANDARD ROLES:
  ROLE_LABEL_STANDARD        = "http://www.xbrl.org/2003/role/label"
  ROLE_LABEL_TERSE           = "http://www.xbrl.org/2003/role/terseLabel"
  ROLE_LABEL_VERBOSE         = "http://www.xbrl.org/2003/role/verboseLabel"
  ROLE_LABEL_DOCUMENTATION   = "http://www.xbrl.org/2003/role/documentation"
  ROLE_LABEL_DEFINITION      = "http://www.xbrl.org/2003/role/definitionGuidance"
  ROLE_LABEL_NEGATED         = "http://www.xbrl.org/2009/role/negatedLabel"
  ROLE_LABEL_NEGATED_TERSE   = "http://www.xbrl.org/2009/role/negatedTerseLabel"
  ROLE_LABEL_PERIOD_START    = "http://www.xbrl.org/2003/role/periodStartLabel"
  ROLE_LABEL_PERIOD_END      = "http://www.xbrl.org/2003/role/periodEndLabel"
  ROLE_FOOTNOTE              = "http://www.xbrl.org/2003/role/footnote"
  # (plus full LRR list loaded at runtime from config/lrr/lrr.xml)

THRESHOLDS (all configurable via PipelineConfig):
  DEFAULT_LARGE_FILE_THRESHOLD_BYTES   = 100 * 1024 * 1024      # 100 MB
  DEFAULT_HUGE_FILE_THRESHOLD_BYTES    = 1024 * 1024 * 1024     # 1 GB (force disk spill)
  DEFAULT_MEMORY_BUDGET_BYTES          = 4 * 1024 * 1024 * 1024 # 4 GB
  DEFAULT_FACT_INDEX_SPILL_FACT_COUNT  = 5_000_000              # 5M facts
  DEFAULT_FACT_INDEX_SPILL_BYTES       = 500 * 1024 * 1024      # 500 MB
  DEFAULT_ERROR_BUFFER_LIMIT           = 10_000                 # spill to file after
  DEFAULT_MAX_FILE_SIZE_BYTES          = 10 * 1024 * 1024 * 1024 # 10 GB hard limit
  DEFAULT_IO_CHUNK_SIZE                = 64 * 1024 * 1024       # 64 MB
  DEFAULT_SAX_BUFFER_SIZE              = 8 * 1024 * 1024        # 8 MB
  DEFAULT_TAXONOMY_FETCH_TIMEOUT_S     = 30
  DEFAULT_MAX_ENTITY_EXPANSIONS        = 100
  DEFAULT_MAX_ZIP_UNCOMPRESSED_BYTES   = 5 * 1024 * 1024 * 1024 # zip bomb guard
  DEFAULT_MAX_ZIP_RATIO                = 100                    # zip bomb guard
  DEFAULT_MAX_ZIP_FILES                = 10_000                 # zip bomb guard
  DEFAULT_MAX_CONTINUATION_DEPTH       = 1000                   # iXBRL safety
  DEFAULT_MAX_HYPERCUBE_DEPTH          = 100                    # infinite-loop guard
  DEFAULT_FORMULA_TIMEOUT_S            = 600                    # per variable set
  DEFAULT_XULE_TIMEOUT_S               = 300                    # per XULE rule
```

### 4B — `src/core/types.py`

```text
ENUMS:
  PeriodType       → INSTANT, DURATION, FOREVER
  BalanceType      → DEBIT, CREDIT, NONE
  Severity         → ERROR, WARNING, INCONSISTENCY, INFO
  InputFormat      → XBRL_XML, IXBRL_HTML, IXBRL_XHTML,
                     XBRL_JSON, XBRL_CSV, TAXONOMY_SCHEMA, LINKBASE,
                     TAXONOMY_PACKAGE, REPORT_PACKAGE, UNKNOWN
  ParserStrategy   → DOM, STREAMING, HYBRID
  LinkbaseType     → CALCULATION, PRESENTATION, DEFINITION, LABEL,
                     REFERENCE, FORMULA, TABLE, GENERIC
  SpillState       → IN_MEMORY, SPILLING, ON_DISK
  StorageType      → SSD, HDD, NETWORK, UNKNOWN
  ConceptType      → ITEM, TUPLE, ABSTRACT, DOMAIN, HYPERCUBE,
                     DIMENSION, TYPED_DIMENSION
  FactType         → NUMERIC, NON_NUMERIC, NIL, FRACTION, TUPLE
  AssertionType    → VALUE, EXISTENCE, CONSISTENCY
  RegulatorId      → EFM, ESEF, FERC, HMRC, CIPC, MCA, CUSTOM
  CalculationMode  → CLASSIC, CALC_1_1

TYPE ALIASES:
  QName            = str          # "{ns}localName" canonical form
  ContextID        = str
  UnitID           = str
  FactID           = str
  ByteOffset       = int
  DimensionKey     = Tuple[Tuple[str, str], ...]  # sorted (dimQN, memberQN) pairs
  RoleURI          = str
  ArcroleURI       = str
  TaxonomyURL      = str

PROTOCOLS (for duck-typing):
  class FactSource(Protocol):
    def get_facts_by_concept(self, concept: QName) -> Iterable[Fact]: ...
    def get_facts_by_context(self, ctx: ContextID) -> Iterable[Fact]: ...
    # etc.
  class ValueReader(Protocol):
    def read_value(self, offset: ByteOffset, length: int) -> bytes: ...
```

### 4C — `src/core/exceptions.py`

```text
HIERARCHY (all inherit from XBRLValidatorError):

  XBRLValidatorError                    — base, carries: code, message, context
  ├── ParseError                        — attrs: file_path, line, column, snippet
  │   ├── XMLParseError
  │   ├── IXBRLParseError
  │   ├── JSONParseError
  │   ├── CSVParseError
  │   └── PackageParseError
  ├── SecurityError                     — attrs: attack_type
  │   ├── XXEError
  │   ├── BillionLaughsError
  │   ├── ZipBombError
  │   ├── PathTraversalError
  │   └── SSRFError                     — blocked outbound URL
  ├── FileTooLargeError                 — attrs: file_size, max_size
  ├── MemoryBudgetExceededError         — attrs: component, requested, available
  ├── TaxonomyResolutionError           — attrs: url, reason
  │   ├── TaxonomyNotFoundError
  │   ├── TaxonomyFetchError
  │   ├── TaxonomyVersionMismatchError
  │   └── CircularImportError
  ├── DiskSpillError                    — attrs: path, operation
  ├── UnsupportedFormatError            — attrs: detected_content
  ├── ProfileNotFoundError              — attrs: profile_id
  ├── RuleCompileError                  — attrs: rule_file, line
  ├── XULEError
  │   ├── XULESyntaxError               — attrs: file_path, line, column
  │   ├── XULECompileError
  │   ├── XULERuntimeError
  │   └── XULETimeoutError
  ├── FormulaError
  │   ├── FormulaCompileError
  │   ├── FormulaRuntimeError
  │   ├── FormulaTimeoutError
  │   └── XPathError                    — wraps elementpath errors
  ├── ConformanceError                  — attrs: suite, test_case, expected, got
  └── PipelineAbortError                — critical, stops pipeline

  # Not all errors are exceptions. Most validation findings are ValidationMessage
  # objects accumulated into the result; exceptions are only for unrecoverable
  # conditions or security violations.
```

---

## 5. FORMAT DETECTOR — `src/core/parser/format_detector.py`

```text
CLASS: FormatDetector
  __init__(self, config: PipelineConfig)
  detect(self, file_path: str) -> DetectionResult
  detect_batch(self, file_paths: List[str]) -> List[DetectionResult]
  detect_package(self, zip_path: str) -> PackageDetectionResult

DATACLASS: DetectionResult
  format: InputFormat
  strategy: ParserStrategy
  encoding: str
  file_path: str
  file_size_bytes: int
  is_compressed: bool
  mime_type: Optional[str]
  declared_namespaces: Dict[str, str]
  root_qname: Optional[QName]
  entry_points: List[str]              # for packages
  storage_type: StorageType            # SSD/HDD/UNKNOWN
  detection_confidence: float          # 0.0 – 1.0

DATACLASS: PackageDetectionResult
  package_format: str                  # "taxonomy-package" / "report-package" / "filing-zip"
  catalog_path: Optional[str]          # META-INF/catalog.xml
  metadata_path: Optional[str]         # META-INF/taxonomyPackage.xml
  entry_points: List[str]
  instance_documents: List[str]        # inside the package
  contained_files: List[str]

DETECTION ALGORITHM:
  1. os.path.getsize → reject if > max_file_size_bytes (FileTooLargeError)
  2. Read first 4 bytes:
       b"PK\x03\x04" → ZIP archive → detect_package()
       b"\x1f\x8b"   → gzip → (for streaming XBRL-JSON variants)
  3. Read first 8192 bytes, detect BOM:
       EF BB BF → UTF-8
       FF FE    → UTF-16LE
       FE FF    → UTF-16BE
  4. Content sniffing (in this priority):
       "<?xml" or "<" at pos 0  → XML; go to XML sub-classification
       "{" (after whitespace)    → XBRL-JSON (threshold 50 MB for streaming)
       CSV header pattern        → XBRL-CSV (threshold 200 MB for streaming)
       "<!DOCTYPE html"          → HTML sub-classification
       "<html"                   → HTML sub-classification
       else                      → UNKNOWN → UnsupportedFormatError
  5. XML sub-classification (first root tag):
       {NS_XBRLI}xbrl            → XBRL_XML
       {NS_XSD}schema             → TAXONOMY_SCHEMA
       {NS_LINK}linkbase          → LINKBASE
       html[xmlns=xhtml]          → IXBRL_XHTML (if ix: ns present)
       otherwise                  → further sniffing
  6. HTML sub-classification:
       Scan first 64KB for `xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"`
       AND either `<ix:header` or `<ix:nonFraction` or `<ix:nonNumeric`
       → IXBRL_HTML (HTML5) or IXBRL_XHTML (XHTML)
       else → UNKNOWN
  7. Package detection (ZIP):
       Has META-INF/taxonomyPackage.xml → TAXONOMY_PACKAGE
       Has reportPackage.json            → REPORT_PACKAGE (OIM)
       Has single .xml at root           → FILING_ZIP (ESEF-style)
       else                              → unknown zip
  8. Strategy selection:
       file_size ≤ large_file_threshold → DOM
       file_size > large_file_threshold → STREAMING
       file_size > huge_file_threshold  → STREAMING + forced disk spill
  9. Storage detection:
       Linux: /sys/block/{dev}/queue/rotational → 0=SSD, 1=HDD
       macOS: diskutil info <device> → "Solid State: Yes/No"
       Windows: Get-PhysicalDisk | Select MediaType
       Unknown → StorageType.UNKNOWN (caller defaults to HDD, per Rule 17)

ERROR CODES: PARSE-0001..0012
```

---

## 6. LARGE-FILE STREAMING INFRASTRUCTURE

This is one of the system's key differentiators vs Arelle. Every file-reading path
has both a DOM and a streaming implementation.

### 6A — `src/core/parser/streaming/memory_budget.py`

```text
CLASS: MemoryBudget (one instance per pipeline run, thread-safe)

  __init__(self, total_bytes: int)
  register(self, component: str, max_bytes: int) -> MemoryAllocation
  can_allocate(self, component: str, additional_bytes: int) -> bool
  record_allocation(self, component: str, bytes_added: int) -> None
  record_deallocation(self, component: str, bytes_freed: int) -> None
  request_spill(self, component: str) -> None
  get_total_used(self) -> int
  get_system_rss(self) -> int           # psutil.Process().memory_info().rss
  pressure_ratio(self) -> float         # total_used / total_bytes
  snapshot(self) -> Dict[str, int]      # for logging
  enforce(self) -> None                 # raise if hard limit exceeded

DATACLASS: MemoryAllocation
  component: str
  allocated_bytes: int
  used_bytes: int
  spill_state: SpillState
  last_allocated_at: datetime
  spill_callback: Optional[Callable[[], None]]

DEFAULT BUDGET SPLIT (for 4 GB total):
  Python runtime + libs       200 MB   (fixed overhead)
  Taxonomy model              500 MB   (fixed after load; us-gaap is ~300MB)
  Context/Unit registries      50 MB   (fixed after parse)
  Fact index                  500 MB   (spills at threshold)
  Active fact values          500 MB   (LRU eviction)
  Validation state            200 MB   (spills error list at 10K)
  Formula evaluation          400 MB   (variable sets during eval)
  XULE evaluation             300 MB   (factsets)
  Error accumulator           100 MB   (spills to file)
  I/O buffers                 150 MB   (fixed)
  Safety margin              1100 MB   (absorbs spikes)

BEHAVIOR UNDER PRESSURE:
  pressure_ratio >= 0.80 → log warning, trigger voluntary spill in registered components
  pressure_ratio >= 0.90 → force spill in largest component
  pressure_ratio >= 0.95 → abort new allocations, spill everything spillable
  pressure_ratio >= 1.00 → MemoryBudgetExceededError
```

### 6B — `src/core/parser/streaming/fact_index.py`

```text
DATACLASS: FactReference (frozen=True, slots=True for memory efficiency)
  index: int                          # ordinal position in source doc
  concept: QName
  context_ref: ContextID
  unit_ref: Optional[UnitID]
  byte_offset: ByteOffset             # start byte of element in source file
  value_length: int                   # length of value text in bytes
  value_preview: Optional[bytes]      # first 64 bytes for small string facts
  is_numeric: bool
  is_nil: bool
  is_tuple: bool
  decimals: Optional[str]             # str form preserves "INF"
  precision: Optional[str]
  id: Optional[FactID]
  source_line: int
  source_column: int
  period_type: Optional[PeriodType]
  balance_type: Optional[BalanceType]
  language: Optional[str]             # xml:lang
  parent_tuple_ref: Optional[int]     # for tuple children

  @property
  def estimated_memory_bytes(self) -> int:
      # base object ~160 bytes + strings
      return 160 + sum(len(s) for s in (self.concept, self.context_ref,
                                         self.unit_ref or "", self.id or ""))

CLASS: InMemoryFactIndex
  __init__(self, budget: MemoryBudget, spill_threshold: int)

  # mutation
  add(self, ref: FactReference) -> bool               # False if at capacity
  add_batch(self, refs: List[FactReference]) -> int

  # queries (all return List, never iterator, for in-memory)
  count -> int
  should_spill -> bool
  get(self, idx: int) -> FactReference
  get_by_concept(self, concept: QName) -> List[FactReference]
  get_by_context(self, ctx_id: ContextID) -> List[FactReference]
  get_by_unit(self, unit_id: UnitID) -> List[FactReference]
  get_by_concept_and_context(self, concept: QName, ctx_id: ContextID) -> List[FactReference]
  get_duplicate_groups(self) -> Dict[Tuple, List[FactReference]]
  get_tuple_children(self, parent_idx: int) -> List[FactReference]

  # iteration
  iter_all(self) -> Iterator[FactReference]
  iter_batches(self, batch_size: int) -> Iterator[List[FactReference]]
  iter_by_concept(self) -> Iterator[Tuple[QName, List[FactReference]]]

  # memory
  estimated_bytes -> int

INTERNAL INDEXES (store int indices, not FactReference copies):
  _facts: List[FactReference]
  _by_concept: Dict[QName, List[int]]
  _by_context: Dict[ContextID, List[int]]
  _by_unit:    Dict[UnitID, List[int]]
  _by_cc:      Dict[Tuple[QName, ContextID], List[int]]
  _duplicate_groups: Dict[Tuple, List[int]]  # computed lazily

MEMORY MATH:
  FactReference ~240 bytes average (vs v2's 200 — corrected for parent_tuple, language)
  Index entries ~80 bytes per fact (five indexes × ~16 bytes avg)
  500 MB budget → ~1.56M facts in memory
  Spill at 5M facts OR 500 MB used, whichever comes first
```

### 6C — `src/core/parser/streaming/disk_spill.py`

```text
CLASS: DiskSpilledFactIndex
  Same interface as InMemoryFactIndex, backed by SQLite.

  __init__(self, db_path: Optional[str] = None, budget: MemoryBudget)
  add(self, ref: FactReference) -> bool
  add_batch(self, refs: List[FactReference]) -> None    # 10K per transaction
  + all query methods from InMemoryFactIndex
  close(self) -> None
  __del__(self) → best-effort cleanup

SQLITE SCHEMA:
  PRAGMA journal_mode=WAL;
  PRAGMA synchronous=NORMAL;
  PRAGMA cache_size=-64000;           -- 64 MB cache
  PRAGMA temp_store=MEMORY;
  PRAGMA mmap_size=268435456;         -- 256 MB mmap

  CREATE TABLE facts (
    idx             INTEGER PRIMARY KEY,
    concept         TEXT NOT NULL,
    context_ref     TEXT NOT NULL,
    unit_ref        TEXT,
    byte_offset     INTEGER NOT NULL,
    value_length    INTEGER NOT NULL,
    value_preview   BLOB,
    is_numeric      INTEGER NOT NULL,
    is_nil          INTEGER NOT NULL,
    is_tuple        INTEGER NOT NULL,
    decimals        TEXT,
    precision       TEXT,
    fact_id         TEXT,
    source_line     INTEGER NOT NULL,
    source_column   INTEGER NOT NULL,
    period_type     TEXT,
    balance_type    TEXT,
    language        TEXT,
    parent_tuple    INTEGER
  );
  CREATE INDEX idx_concept      ON facts(concept);
  CREATE INDEX idx_context      ON facts(context_ref);
  CREATE INDEX idx_unit         ON facts(unit_ref);
  CREATE INDEX idx_cc           ON facts(concept, context_ref);
  CREATE INDEX idx_parent       ON facts(parent_tuple);
  CREATE INDEX idx_offset       ON facts(byte_offset);
  CREATE INDEX idx_fact_id      ON facts(fact_id) WHERE fact_id IS NOT NULL;

BATCHING:
  Insert in 10K-row transactions (executemany).
  Lookup batched when possible: SELECT ... WHERE concept IN (?, ?, ...).

PERFORMANCE (measured targets, tested in tests/large_file/):
  Insert:      ~500K facts/sec (batched)
  Point query: ~200 µs
  Range query: ~100K facts/sec scan
  50M facts:   ~2 GB SQLite file, ~3 min load
```

### 6D — `src/core/parser/streaming/fact_store.py`

```text
CLASS: FactStore
  Unified interface. Transparently switches InMemory → DiskSpilled.

  __init__(self, budget: MemoryBudget, config: PipelineConfig,
           force_mode: Optional[SpillState] = None)
  storage_mode -> SpillState
  count -> int
  add(self, ref: FactReference) -> None
    # if mode == IN_MEMORY and (count >= spill_threshold or memory pressure):
    #   create DiskSpilledFactIndex
    #   transfer all in-memory facts via add_batch in 10K chunks
    #   free InMemoryFactIndex
    #   emit log event: "fact_store.spilled"
    #   switch mode
  + all query methods (delegates to active backend)
  iter_batches(self, batch_size: int) -> Iterator[List[FactReference]]
  close(self) -> None

SPILL DECISION ALGORITHM:
  On every add():
    if mode == IN_MEMORY:
      if count == spill_threshold: spill()
      elif count % 10000 == 0 and budget.pressure_ratio() >= 0.85: spill()

  force_mode bypasses auto-detection (useful for tests and --force-streaming flag).
```

### 6E — `src/core/parser/streaming/mmap_reader.py`

```text
CLASS: MMapReader
  For SSD storage ONLY. Memory-mapped random access.

  __init__(self, file_path: str)
  read_value(self, byte_offset: int, length: int) -> bytes
  read_values_batch(self, locations: List[Tuple[int, int]]) -> Dict[int, bytes]
    # sorts by offset internally for page-cache friendliness
  close(self) -> None
  __enter__/__exit__ — context manager

IMPLEMENTATION:
  mmap.mmap(fd, 0, access=mmap.ACCESS_READ)
  64-bit offsets supported on 64-bit platforms.

USAGE GUARD:
  Created only via StorageDetector.is_ssd() returning True.
  Default for unknown: HDD (use ChunkedReader). Per Rule 17.
```

### 6F — `src/core/parser/streaming/chunked_reader.py`

```text
CLASS: ChunkedReader
  For HDD / network storage. Sequential I/O only.

  __init__(self, file_path: str, chunk_size: int = 64 * 1024 * 1024)
  read_values(self, locations: List[Tuple[int, int]]) -> Dict[int, bytes]
    # 1. Sort locations by offset
    # 2. Read file in chunk_size blocks sequentially (f.read(chunk_size))
    # 3. Extract values as chunks pass over their offsets
    # 4. Handle values spanning chunk boundaries (hold tail over)
    # 5. Release chunk memory as soon as last value in chunk is extracted
  close(self) -> None

HDD BENEFIT:
  Random I/O on HDD: ~5 MB/s effective
  Sequential I/O:    ~150 MB/s
  30× speedup on multi-GB files with scattered offsets.
```

### 6G — `src/core/parser/streaming/storage_detector.py`

```text
CLASS: StorageDetector
  @staticmethod
  detect(file_path: str) -> StorageType

  Linux:   resolve file → device → /sys/block/{dev}/queue/rotational
  macOS:   diskutil info (parse "Solid State: Yes/No")
  Windows: Get-PhysicalDisk via PowerShell subprocess
  Network: stat + check for nfs/smb/cifs mount → NETWORK
  Fallback: StorageType.UNKNOWN

  Caller treats UNKNOWN as HDD (Rule 17).
  Network treated as HDD-equivalent (sequential preferred).

  Results cached by device path (LRU, max 64 entries).
```

### 6H — `src/core/parser/streaming/counting_wrapper.py`

```text
CLASS: CountingFileWrapper
  Wraps a file object to track byte position for offset recording.

  __init__(self, file_obj: BinaryIO)
  read(self, size: int = -1) -> bytes      # delegates, updates .position
  readline(self) -> bytes                   # delegates, updates .position
  @property position -> int
  tell(self) -> int                         # returns self.position

USED BY sax_handler.py to record approximate byte offsets per element start event.
Not byte-exact (lxml buffers), but close enough for mmap/chunked value reads that
parse a few hundred bytes around the offset.
```

### 6I — `src/core/parser/streaming/sax_handler.py`

```text
CLASS: XBRLSAXHandler
  SAX/iterparse handler for XBRL instance XML > 100 MB.

  __init__(self, file_path: str, fact_store: FactStore, budget: MemoryBudget,
           security: SecurityGuard)
  parse(self) -> StreamingParseResult

ALGORITHM (two-pass):

  PASS 1 — structure + fact index
    wrapper = CountingFileWrapper(open(file_path, 'rb'))
    context = etree.iterparse(wrapper, events=("start","end"),
                               huge_tree=True,
                               resolve_entities=False,
                               no_network=True,
                               load_dtd=False)

    ON "start" EVENT:
      record byte_offset = wrapper.position for candidate fact elements

    ON "end" EVENT for each element:
      if tag is {NS_XBRLI}context  → _handle_context(elem) → store fully in dict
      if tag is {NS_XBRLI}unit     → _handle_unit(elem) → store fully in dict
      if tag is {NS_LINK}schemaRef → _handle_schema_ref(elem)
      if tag is {NS_LINK}linkbaseRef → _handle_linkbase_ref(elem)
      if tag is {NS_LINK}footnoteLink → _handle_footnote_link(elem)
      if tag is a FACT (not in xbrli/link/xbrldi namespaces):
        → _handle_fact(elem, start_offset)
        → Build FactReference (concept, contextRef, unitRef, decimals,
          byte_offset, value_length, is_nil, source_line, etc.)
        → Store value_preview (first 64 bytes) if string-type fact
        → fact_store.add(ref)
        → Do NOT store elem.text for numeric facts > preview size

      CRITICAL MEMORY CLEANUP after each "end":
        elem.clear(keep_tail=True)
        while elem.getprevious() is not None:
            del elem.getparent()[0]

      Without this cleanup, lxml accumulates the full tree despite iterparse.

  PASS 2 — classify via taxonomy
    After PASS 1 completes, taxonomy is loaded, and builder_streaming walks
    fact_store to set period_type, balance_type on FactReferences.
    (This is a backfill via UPDATE if on disk, or field assignment if in memory.)

DATACLASS: StreamingParseResult
  namespaces: Dict[str, str]
  schema_refs: List[SchemaRef]
  linkbase_refs: List[LinkbaseRef]
  contexts: Dict[ContextID, Context]
  units: Dict[UnitID, Unit]
  fact_store: FactStore
  footnote_links: List[FootnoteLinkRef]
  parse_errors: List[ValidationMessage]
  total_facts: int
  total_bytes_scanned: int
  elapsed_seconds: float
  spill_occurred: bool
  peak_memory_bytes: int

SECURITY: disabled DTD, entity expansion capped, external entities blocked.
          Byte offset accuracy: ±buffer_size (8 MB default) worst case;
          actual offsets are close because iterparse tokens are at reader position.
```

### 6J — `src/core/parser/streaming/sax_ixbrl_handler.py`

```text
CLASS: IXBRLStreamingHandler
  For large iXBRL HTML > 100 MB.

  Strategy selection on open:
    If first bytes are "<?xml" or well-formed XHTML → use iterparse (like sax_handler)
    If HTML5 (no XML declaration, loose tags) → use html5lib.treebuilders.etree
                                                 with incremental parsing

  Must handle:
    ix:header extraction (contexts, units, schemaRefs) — full DOM of header (small)
    ix:nonFraction / ix:nonNumeric fact extraction — streaming
    ix:fraction fact — streaming, compute numerator/denominator
    ix:tuple — build tuple hierarchy (parent-child via parent_tuple_ref)
    Continuation chain IDs — collect, resolve in post-pass
    Transform info (format attribute) — stored in FactReference for pass 2
    Short display values (< 100 chars) in FactReference.value_preview
    Escape: ix:exclude regions remembered as offset ranges, skipped on read

POST-PROCESSING:
  continuation resolution walks chains across stored IDs.
  transform application delayed until fact classification (builder phase).
```

### 6K — `src/core/parser/streaming/json_streamer.py`

```text
CLASS: XBRLJSONStreamer
  ijson-based streaming XBRL-JSON parser. Threshold: 50 MB.

  parse(self) -> StreamingParseResult
    events = ijson.parse(file)
    Use prefixed parsing:
      "documentInfo" → parse fully (small, always)
      "facts"        → stream, one fact at a time → FactStore

  RULE 16 COMPLIANCE:
    ijson with use_float=False forces Decimal for numbers.
    String preservation for scientific notation.
    Fact `value` field: always parse as string first, convert to Decimal
    only after type is known from taxonomy (post-pass).
```

### 6L — `src/core/parser/streaming/csv_streamer.py`

```text
CLASS: XBRLCSVStreamer
  polars-based XBRL-CSV streamer. Threshold: 200 MB.

  parse(self) -> StreamingParseResult
    metadata = json.load(metadata.json)  # always small, full parse
    lf = polars.scan_csv(data_csv_path,
                         dtype={col: polars.Utf8 for col in numeric_cols},
                         has_header=True)
    for batch in lf.collect(streaming=True).iter_slices(100_000):
        for row in batch.iter_rows(named=True):
            ref = _build_fact_reference(row, metadata)
            fact_store.add(ref)

  RULE 16 COMPLIANCE:
    All columns read as Utf8. Decimal conversion happens in builder_oim
    after taxonomy classification says "this column is numeric".
```

---
## 7. DOM PARSERS (files ≤ 100 MB)

### 7A — `src/core/parser/xml_parser.py`

```text
CLASS: XMLParser
  __init__(self, config: Optional[PipelineConfig], security: SecurityGuard)
  parse(self, file_path: str) -> RawXBRLDocument
  parse_bytes(self, data: bytes, source_name: str = "<bytes>") -> RawXBRLDocument

SECURITY (hardcoded, cannot be disabled):
  parser = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    dtd_validation=False,
    load_dtd=False,
    huge_tree=False,                   # DOM path, small files only
    collect_ids=True,
  )

  Entity expansion capped at DEFAULT_MAX_ENTITY_EXPANSIONS (100).
  On XXE detection → XXEError (subclass of SecurityError).

DATACLASS: RawXBRLDocument
  root: etree._Element
  namespaces: Dict[str, str]
  source_file: str
  source_size: int
  declared_schema_refs: List[SchemaRef]
  declared_linkbase_refs: List[LinkbaseRef]
  doc_encoding: str

ERROR CODES: PARSE-0001..0012
```

### 7B — `src/core/parser/ixbrl_parser.py`

```text
CLASS: IXBRLParser
  parse(self, file_path: str) -> InlineXBRLDocument
  parse_multiple(self, file_paths: List[str]) -> List[InlineXBRLDocument]  # ESEF multi-doc
  to_xbrl_instance(self, doc: InlineXBRLDocument) -> RawXBRLDocument

PHASES:
  1. Parse document:
     - Well-formed XHTML → lxml.etree (with XXE protection)
     - HTML5             → html5lib, convert to etree representation
  2. Extract ix:header (contexts, units, schemaRefs, roleRefs, arcroleRefs).
     ix:header MAY appear in <ix:hidden> or visible; both must work.
  3. Walk body for:
     - ix:nonFraction
     - ix:nonNumeric
     - ix:fraction (with ix:numerator, ix:denominator)
     - ix:tuple (building tuple hierarchy)
     - ix:continuation (register by id for later resolution)
     - ix:footnote
     - ix:relationship (fact-footnote, additional relationships)
     - ix:references (for role/arcrole references)
  4. Apply transforms: format attribute → TransformRegistry
     Final value = transform(displayValue) × 10^scale × (-1 if sign="-")
  5. Resolve continuations (separate module: ixbrl_continuation.py)
  6. Classify hidden facts (under ix:hidden)
  7. Resolve target document attribute (ix:nonFraction@target for multi-target)

TRANSFORMS (delegated to ixbrl_transforms.py):
  Full ixt-1 through ixt-5 + ixt-sec support.

CONTINUATION (delegated to ixbrl_continuation.py):
  Walk fact.continuedAt → locate ix:continuation id=
    → concat content, skip ix:exclude subtrees
    → handle nested continuation (continuation pointing to another)
  Detect:
    - broken chain (missing target id) → IXBRL-0002
    - circular chain                   → IXBRL-0003
    - exceeds MAX_CONTINUATION_DEPTH   → IXBRL-0004

HIDDEN FACTS:
  Facts under <div style="display:none"> or <ix:hidden> treated specially.
  EFM has specific rules about when hidden is permitted (EFM 6.12.x).

MULTI-TARGET (iXBRL 1.1 §4.2):
  Facts can declare target="foo" to be in a different output document.
  Each target produces a distinct RawXBRLDocument.

ERROR CODES: IXBRL-0001..0045
```

### 7C — `src/core/parser/ixbrl_transforms.py`

```text
CLASS: IXBRLTransformEngine
  __init__(self, registry: TransformRegistry)
  apply(self, format_qname: str, display_value: str,
        scale: int = 0, sign: Optional[str] = None) -> TransformResult

DATACLASS: TransformResult
  xbrl_value: str          # canonical XBRL representation
  error_code: Optional[str]
  original_display: str

TRANSFORMS REQUIRED (minimum, per ixt-5 + ixt-sec):
  Numeric:
    ixt:numdotdecimal, ixt:numcommadecimal
    ixt:numdotdecimalin, ixt:numunitdecimal
    ixt:num-dot-decimal, ixt:num-comma-decimal  (v5 hyphenated form)
    ixt:zerodash, ixt:fixedzero, ixt:fixedempty
    ixt:nocontent (v5)
    ixt-sec:numwordsen, ixt-sec:numtenthousand, ixt-sec:numsextillion
  Boolean:
    ixt:booleanfalse, ixt:booleantrue
    ixt:fixed-false, ixt:fixed-true
  Date:
    ixt:dateslashus, ixt:dateslasheu
    ixt:datedotus, ixt:datedoteu
    ixt:datelongus, ixt:datelonguk, ixt:datelongdaymonthyear
    ixt:dateshortus, ixt:dateshortuk
    ixt:dateerayearmonthdayjp (Japanese era)
    ixt-sec:datequarterend
  Duration:
    ixt:durday, ixt:durmonth, ixt:duryear
    ixt:dur-day, ixt:dur-month, ixt:dur-year
    ixt-sec:duryear, ixt-sec:durmonth, ixt-sec:durweek
  String:
    ixt:fixedzero, ixt:nocontent
    ixt-sec:stateprovnameen

ERROR CODES: IXT-0001..0010
  IXT-0001 Unknown transform
  IXT-0002 Format mismatch (value doesn't match format pattern)
  IXT-0003 Overflow (numeric too large)
  IXT-0004 Invalid date
  IXT-0005 Transform version mismatch
```

### 7D — `src/core/parser/decimal_parser.py`

```text
MODULE: decimal_parser

  parse_xbrl_decimal(text: str, whitespace: bool = True) -> Decimal
    # XBRL uses XML Schema xs:decimal — strict, no float semantics.
    # Leading/trailing whitespace: allowed if whitespace=True
    # Scientific notation: NOT allowed in xs:decimal (but IS in xs:double/xs:float)
    # Thousands separators: NOT allowed
    # Raises: InvalidDecimalError (subclass of ParseError)

  parse_xbrl_double(text: str) -> Decimal
    # xs:double — scientific notation allowed.
    # Still parsed as Decimal (Rule 1), never float.
    # "1E6" → Decimal("1E+6"); "1.5E-3" → Decimal("0.0015")
    # Special values: "INF", "-INF", "NaN" permitted.

  parse_scale(text: str) -> int
    # iXBRL scale attribute: integer, may be negative.

  parse_decimals(text: str) -> Union[int, Literal["INF"]]
    # XBRL decimals: integer or "INF".
    # Return type preserves the distinction.

  parse_precision(text: str) -> Union[int, Literal["INF"]]
    # XBRL precision: positive integer or "INF".

  apply_scale(value: Decimal, scale: int) -> Decimal
    # Uses Decimal.scaleb (never multiplication with floats).
    return value.scaleb(scale)

  round_to_decimals(value: Decimal, decimals: Union[int, str]) -> Decimal
    # If decimals == "INF": return value unchanged.
    # Else: ROUND_HALF_UP or ROUND_HALF_EVEN per XBRL 2.1 convention.
    # All arithmetic via Decimal context with prec ≥ 28.
```

### 7E — `src/core/parser/datetime_parser.py`

```text
MODULE: datetime_parser

  parse_xml_date(text: str) -> date
    # xs:date: YYYY-MM-DD, optional timezone.

  parse_xml_datetime(text: str) -> datetime
    # xs:dateTime: YYYY-MM-DDThh:mm:ss(.sss)?(Z|±hh:mm)?
    # Timezone-aware always. Naive inputs assumed UTC.

  parse_xml_duration(text: str) -> timedelta | relativedelta
    # xs:duration: P1Y2M3DT4H5M6S
    # Uses isodate library. Months+years need calendar math (relativedelta).

  parse_xbrl_period(xml_elem) -> Period
    # Handles <startDate>/<endDate>, <instant>, <forever>
    # XBRL 2.1 §4.7.2: instant dates are END-OF-DAY (23:59:59 semantics for comparisons).

  period_contains(period: Period, instant: date) -> bool
    # Period containment check per XBRL 2.1.

  periods_equal(a: Period, b: Period) -> bool
    # Date equality honoring end-of-day semantics.

ERROR CODES: DT-0001..0005
```

### 7F — `src/core/parser/package_parser.py`

```text
CLASS: PackageParser
  Parses Taxonomy Packages 1.0 and Report Packages.

  __init__(self, security: SecurityGuard)
  parse_taxonomy_package(self, zip_path: str) -> TaxonomyPackage
  parse_report_package(self, zip_path: str) -> ReportPackage
  parse_filing_zip(self, zip_path: str) -> FilingZip

TAXONOMY PACKAGE STRUCTURE (Tax Pkg 1.0):
  /META-INF/taxonomyPackage.xml    — required, metadata
  /META-INF/catalog.xml            — required, URL rewrite rules
  /{package-name}/**/*.xsd         — schemas
  /{package-name}/**/*.xml         — linkbases

  Parser must:
    1. Unzip to temp dir (with zip_guard.py protection)
    2. Read META-INF/taxonomyPackage.xml, validate against TPE schema
    3. Read META-INF/catalog.xml
    4. Enumerate entry points (from metadata)
    5. Map URLs via catalog
    6. Validate: all referenced files exist in package
    7. Validate: versioning (pt:version element)
    8. Extract languages, names, descriptions, publisher

REPORT PACKAGE (OIM):
  /META-INF/reportPackage.json     — metadata
  /reports/{report.xml | report.xhtml | report.json | report.csv}

FILING ZIP (ESEF-style):
  Root contains one or more .xhtml (iXBRL) + /reports/{subfolder}/**
  Signed packages: detached XAdES signature in /META-INF/signatures.xml

SECURITY:
  zip_guard enforces:
    max uncompressed size (5 GB)
    max compression ratio (100:1)
    max file count (10K)
    no absolute paths, no ".." segments
    no symlinks

DATACLASSES:
  TaxonomyPackage
    package_name: str
    version: str
    publisher: str
    languages: List[str]
    entry_points: List[EntryPoint]
    catalog_rewrites: List[CatalogRewrite]
    root_path: str                        # extracted temp dir
    original_zip: str

  ReportPackage
    format: str                           # xml / xhtml / json / csv
    reports: List[str]                    # paths within package
    metadata: Dict

ERROR CODES: PKG-0001..0020
```

---

## 8. TAXONOMY RESOLUTION

The taxonomy subsystem is substantially bigger than v2 described. It must handle:
version-aware caching, full DTS closure, LRR, UTR, cross-version mapping, signed
packages, and offline mode.

### 8A — `src/core/taxonomy/resolver.py`

```text
CLASS: TaxonomyResolver
  __init__(self, cache: TaxonomyCache, catalog: XMLCatalog,
           fetcher: TaxonomyFetcher, config: PipelineConfig)
  resolve(self, entry_points: List[str]) -> TaxonomyModel
  resolve_from_package(self, pkg: TaxonomyPackage) -> TaxonomyModel
  resolve_from_instance(self, instance: RawXBRLDocument) -> TaxonomyModel

DTS DISCOVERY ALGORITHM (XBRL 2.1 §3.1):
  visited = set()
  queue = deque(entry_points)
  dts = TaxonomyModel()

  while queue:
    url = queue.popleft()
    if url in visited:
      continue
    visited.add(url)

    resolved_url = catalog.resolve(url)        # XML catalog rewrites
    content = cache.get_or_fetch(resolved_url)

    if content.mime == "application/xml" and content.root_tag == "{xs}schema":
      schema = parse_schema(content)
      dts.add_schema(schema)
      # discover DTS expansions:
      for imp in schema.imports:            queue.append(imp.schemaLocation)
      for inc in schema.includes:           queue.append(inc.schemaLocation)
      for lbref in schema.linkbaseRefs:     queue.append(lbref.href)
      for role in schema.role_types:        dts.add_role_type(role)
      for arcrole in schema.arcrole_types:  dts.add_arcrole_type(arcrole)
      # concept extraction:
      for element in schema.elements:
        if derives_from_item_or_tuple(element):
          dts.add_concept(build_concept(element))

    elif content.root_tag == "{link}linkbase":
      linkbase = parse_linkbase(content)
      dts.add_linkbase(linkbase)
      for roleRef in linkbase.roleRefs:       queue.append(roleRef.href)
      for arcroleRef in linkbase.arcroleRefs: queue.append(arcroleRef.href)
      # arcs discovered via XLink resolution

  # Post-processing:
  dts.resolve_all_xlink()                  # resolve locators
  dts.apply_prohibition_override()         # XBRL 2.1 §3.5.3
  dts.build_networks()                     # per role/arcrole
  dts.validate_closure()                   # DTS-0002 if circular
  return dts

PROHIBITION/OVERRIDE:
  Per XBRL 2.1 §3.5.3, arcs with higher priority override lower.
  use="prohibited" cancels arcs it equivalently-matches on lower priority.
  Equivalence key: (from, to, arcrole, order).

ERROR CODES: DTS-0001..0015
```

### 8B — `src/core/taxonomy/cache.py` — Three-Tier Cache

```text
CLASS: TaxonomyCache

  __init__(self, cache_dir: str, catalog: XMLCatalog,
           fetcher: TaxonomyFetcher, budget: MemoryBudget)
  get_or_fetch(self, url: str) -> CachedResource
  preload_package(self, pkg: TaxonomyPackage) -> None
  clear(self) -> None
  stats(self) -> CacheStats

LEVELS:
  L1 HOT   — in-memory LRU, msgpack-serialized parsed schemas
             budget: 300 MB default
             load time: ~50 ms per taxonomy

  L2 WARM  — disk: cache_dir/{sha256}.msgpack (parsed form)
                  + cache_dir/_raw/{sha256}.xsd|xml (raw form)
             load time: ~200 ms per taxonomy from parsed form
                       ~15s per taxonomy if only raw exists

  L3 COLD  — HTTP fetch via fetcher (only if allow-list permits)
             30–60s for remote taxonomy download

CACHE KEY (critical — per Rule 15):
  Composite: SHA256(url + taxonomy_package_hash_if_known + version)
  Reason: us-gaap-2024 and us-gaap-2025 may have same URL but different content
  if fetched from different mirrors. Always prefer package-provided content.

INVALIDATION:
  - TTL: 30 days for remote resources (configurable)
  - Package-provided content never expires
  - ETag/Last-Modified checks on refresh
  - Hash mismatch with package → TaxonomyVersionMismatchError

OFFLINE MODE:
  If --offline: L3 disabled. L2 miss + no package → TaxonomyNotFoundError.
```

### 8C — `src/core/taxonomy/catalog.py` — OASIS XML Catalog

```text
CLASS: XMLCatalog
  __init__(self, catalog_files: List[str])
  resolve(self, url: str) -> str
  resolve_system(self, system_id: str) -> Optional[str]
  resolve_public(self, public_id: str) -> Optional[str]
  resolve_rewrite(self, url: str) -> Optional[str]

SUPPORTED ENTRIES (OASIS XML Catalog 1.1):
  <system systemId="..." uri="..."/>
  <rewriteSystem systemIdStartString="..." rewritePrefix="..."/>
  <uri name="..." uri="..."/>
  <rewriteURI uriStartString="..." rewritePrefix="..."/>
  <nextCatalog catalog="..."/>                 # chained catalogs
  <delegateSystem systemIdStartString="..." catalog="..."/>
  <group xml:base="...">                       # group with base URI

PRECEDENCE (OASIS spec):
  system > rewriteSystem (longest prefix) > nextCatalog > delegateSystem
  Within a taxonomy package: package catalog takes precedence over user catalogs.

PACKAGE CATALOGS:
  Taxonomy Package 1.0 mandates /META-INF/catalog.xml in each package.
  When a package is loaded, its catalog is merged first.
```

### 8D — `src/core/taxonomy/package.py` + `package_metadata.py`

```text
CLASS: TaxonomyPackage (richer than v2)
  package_uri: str
  name: str
  description: Dict[str, str]         # language-keyed
  version: str
  license_href: Optional[str]
  publisher: str
  publisher_url: Optional[str]
  publisher_country: Optional[str]
  publication_date: date
  entry_points: List[EntryPoint]
  supersedes: List[str]               # superseded package URIs
  superseded_by: List[str]
  catalog: XMLCatalog                 # parsed META-INF/catalog.xml
  root_path: Path                     # extracted temp dir
  files: List[Path]                   # all files in package
  signed: bool
  signature_valid: Optional[bool]     # None if unsigned, bool if signed+verified

DATACLASS: EntryPoint
  name: Dict[str, str]                # language-keyed
  description: Dict[str, str]
  version: Optional[str]
  entry_point_documents: List[str]    # URLs of entry schemas
  languages: List[str]

METADATA PARSER (package_metadata.py):
  Validates taxonomyPackage.xml against official TPE schema.
  Extracts all metadata. Errors on missing required fields.

ERROR CODES: TPE-0001..0015
```

### 8E — `src/core/taxonomy/lrr_registry.py`

```text
CLASS: LRRRegistry
  Registers the official Link Role Registry per XBRL International.

  __init__(self, lrr_file: str = "config/lrr/lrr.xml")
  is_registered_role(self, role_uri: str) -> bool
  is_registered_arcrole(self, arcrole_uri: str) -> bool
  get_role_info(self, role_uri: str) -> Optional[LRRRoleInfo]
  all_roles() -> List[LRRRoleInfo]

Used by label validators (which roles are "standard") and presentation validators.
```

### 8F — `src/core/taxonomy/utr_registry.py`

```text
CLASS: UTRRegistry
  Units Registry — XBRL International's official unit registry.

  __init__(self, utr_files: List[str])
  is_registered_unit(self, unit: Unit) -> bool
  get_unit_info(self, unit_qname: QName) -> Optional[UTRUnitInfo]
  validate_for_concept_type(self, unit: Unit, data_type: QName) -> Optional[str]
    # Returns error message if unit doesn't match type constraints.
    # e.g., unit "shares" with data type "monetaryItemType" → UTR-0003

DATACLASS: UTRUnitInfo
  unit_id: str
  unit_name: str
  ns_unit: str
  item_type: QName                     # concept type this unit is valid for
  numerator_item_type: Optional[QName] # for divide units
  denominator_item_type: Optional[QName]
  symbol: Optional[str]
  status: str                          # "REC", "CR", "WD"
```

### 8G — `src/core/taxonomy/version_map.py` (NEW — not in v2)

```text
CLASS: ConceptVersionMap
  Cross-taxonomy-version concept mapping.
  Supports us-gaap yearly releases, IFRS revisions, etc.

  __init__(self, map_file: Optional[str])
  concept_between_versions(self, qname: QName, from_version: str,
                            to_version: str) -> Optional[QName]
  is_superseded(self, qname: QName, version: str) -> bool
  successor(self, qname: QName, version: str) -> Optional[QName]

DATA SOURCES:
  us-gaap: FASB publishes "Release Notes" with concept additions/deprecations/renames
  IFRS: IFRS Foundation publishes concept mapping files with each taxonomy release
  ESEF: ESMA publishes anchoring-related mappings

USAGE:
  Primarily used by:
    AI tagging analyzer (recommend migration to newer concept)
    Regulator profiles (period-over-period consistency)
```

### 8H — `src/core/taxonomy/fetcher.py`

```text
CLASS: TaxonomyFetcher
  __init__(self, config: PipelineConfig, allow_list: URLAllowList)
  fetch(self, url: str) -> FetchResult
  fetch_async(self, urls: List[str]) -> List[FetchResult]  # httpx async

SECURITY:
  URL allow-list checked BEFORE any network call:
    Default allow-list:
      xbrl.fasb.org            (us-gaap)
      xbrl.ifrs.org            (IFRS)
      xbrl.sec.gov             (SEC taxonomies)
      www.xbrl.org             (XBRL International)
      ferc.gov                 (FERC)
      www.esma.europa.eu       (ESMA)
      xbrl.frc.org.uk          (UK FRC)
      cipc.co.za               (CIPC)
      mca.gov.in               (MCA)
    User-provided allow-list extends default.
    All other URLs → SSRFError.

  Timeouts: 30s default, configurable.
  Redirects: followed up to 5 times, each target re-checked against allow-list.
  HTTPS only (HTTP requests → error unless --allow-http).
  User-Agent identifies validator + version.
```

---

## 9. MODEL

### 9A — `src/core/model/xbrl_model.py`

```text
This module defines dataclasses. ALL numeric values use Decimal. ALL fields have type hints.

  Period
    period_type: PeriodType
    instant: Optional[date]
    start_date: Optional[date]
    end_date: Optional[date]

    def equals(self, other: 'Period') -> bool  # end-of-day aware

  EntityIdentifier
    scheme: str                         # URI
    identifier: str

  DimensionMember                       # one dim-member binding in a context
    dimension: QName
    member: Optional[QName]             # for explicit dims
    typed_value: Optional[str]          # raw text for typed dims
    is_typed: bool
    typed_schema_ref: Optional[QName]   # schema type for typed dim

  Context
    id: ContextID
    entity: EntityIdentifier
    period: Period
    segment_dims: Dict[QName, DimensionMember]
    scenario_dims: Dict[QName, DimensionMember]
    segment_non_xdt: Optional[etree.Element]   # preserved for non-XDT segment content
    scenario_non_xdt: Optional[etree.Element]
    source_line: int

    @property
    def dimension_key(self) -> DimensionKey      # sorted tuple for equality
    @property
    def all_dimensions(self) -> Dict[QName, DimensionMember]
    def is_dimensional_equivalent(self, other: 'Context') -> bool

  UnitMeasure
    namespace: str
    local_name: str

  Unit
    id: UnitID
    measures: List[UnitMeasure]         # for simple unit
    numerator_measures: List[UnitMeasure]   # for divide
    denominator_measures: List[UnitMeasure]
    source_line: int

    @property is_divide -> bool
    @property is_monetary -> bool      # single iso4217:* measure
    @property is_shares -> bool
    @property is_pure -> bool
    def is_equal(self, other: 'Unit') -> bool

  Fact
    id: Optional[FactID]
    concept_qname: QName
    concept: ConceptDefinition
    context_ref: ContextID
    context: Context
    unit_ref: Optional[UnitID]
    unit: Optional[Unit]
    raw_value: str                      # original text
    numeric_value: Optional[Decimal]    # None for non-numeric or nil
    is_nil: bool
    is_numeric: bool
    is_tuple: bool
    decimals: Optional[Union[int, str]]
    precision: Optional[Union[int, str]]
    language: Optional[str]
    source_line: int
    source_file: str
    is_hidden: bool                     # iXBRL under ix:hidden
    footnote_refs: List[str]
    parent_tuple: Optional['Fact']      # None if top-level
    tuple_children: List['Fact']        # only populated for tuples

    # iXBRL-specific:
    transform_format: Optional[QName]   # ix:nonFraction@format
    transform_scale: Optional[int]
    transform_sign: Optional[str]
    continuation_id: Optional[str]

    @property duplicate_key -> Tuple    # (concept, context_ref, unit_ref, xml_lang)
    @property rounded_value -> Decimal  # per decimals

  Footnote
    id: str
    role: RoleURI
    language: str
    content: str
    fact_refs: List[FactID]
    source_line: int

  ValidationMessage
    code: str                           # e.g., "XBRL21-0008"
    severity: Severity
    message: str
    concept_qname: Optional[QName]
    context_id: Optional[ContextID]
    unit_id: Optional[UnitID]
    fact_id: Optional[FactID]
    source_file: Optional[str]
    source_line: Optional[int]
    source_column: Optional[int]
    details: Dict[str, Any]             # structured data
    fix_suggestion: Optional[str]
    rule_source: str                    # "spec" / "regulator:efm" / "xule:rule.xule:42"
    arelle_equivalent_code: Optional[str]   # per Rule 14

  ConceptDefinition
    qname: QName
    namespace: str
    local_name: str
    data_type: QName
    period_type: PeriodType
    balance_type: Optional[BalanceType]
    abstract: bool
    nillable: bool
    substitution_group: QName
    type_is_numeric: bool
    type_is_textblock: bool
    type_is_enum: bool
    type_is_enum_set: bool
    is_hypercube: bool
    is_dimension: bool
    is_typed_dimension: bool
    typed_domain_ref: Optional[str]
    labels: Dict[Tuple[RoleURI, str], List[Label]]   # (role, lang) → labels
    references: List[Reference]
    source_taxonomy_version: Optional[str]

  ArcModel
    arc_type: str                       # localName of arc element
    arcrole: ArcroleURI
    role: RoleURI                       # containing extended link role
    from_concept: QName
    to_concept: QName
    order: Decimal
    weight: Optional[Decimal]           # calculation
    priority: int
    use: str                            # "optional" / "prohibited"
    preferred_label: Optional[RoleURI]  # presentation
    contextElement: Optional[str]       # dimensions: "segment"/"scenario"
    closed: Optional[bool]              # has-hypercube
    targetRole: Optional[RoleURI]       # dimensions
    usable: bool                        # domain-member
    source_line: int

  LinkbaseModel
    linkbase_type: LinkbaseType
    role_uri: RoleURI
    arcs: List[ArcModel]
    source_file: str

  HypercubeModel
    qname: QName
    dimensions: List[QName]             # in order
    is_closed: bool
    context_element: str                # "segment" or "scenario"
    targetRole: Optional[RoleURI]
    domain_members_by_dim: Dict[QName, List[QName]]

  TaxonomyModel
    concepts: Dict[QName, ConceptDefinition]
    role_types: Dict[RoleURI, RoleType]
    arcrole_types: Dict[ArcroleURI, ArcroleType]
    calc_networks: Dict[RoleURI, LinkbaseModel]
    calc_11_networks: Dict[RoleURI, LinkbaseModel]
    pres_networks: Dict[RoleURI, LinkbaseModel]
    def_networks: Dict[RoleURI, LinkbaseModel]
    label_linkbases: List[LinkbaseModel]
    ref_linkbases: List[LinkbaseModel]
    formula_linkbases: List[LinkbaseModel]
    table_linkbases: List[LinkbaseModel]
    generic_linkbases: List[LinkbaseModel]
    namespaces: Dict[str, str]
    dimension_defaults: Dict[QName, QName]
    hypercubes: Dict[QName, HypercubeModel]
    source_package: Optional[TaxonomyPackage]
    source_version: Optional[str]

  XBRLInstance
    file_path: str
    format_type: InputFormat
    contexts: Dict[ContextID, Context]
    units: Dict[UnitID, Unit]
    facts: List[Fact]                   # DOM mode only
    footnotes: List[Footnote]
    taxonomy: TaxonomyModel
    schema_refs: List[SchemaRef]
    linkbase_refs: List[LinkbaseRef]    # explicit linkbaseRef in instance
    namespaces: Dict[str, str]

    # Indexes (DOM mode)
    facts_by_concept: Dict[QName, List[Fact]]
    facts_by_context: Dict[ContextID, List[Fact]]
    facts_by_unit: Dict[UnitID, List[Fact]]
    dimensional_facts: List[Fact]

    # Streaming mode (mutually exclusive with facts list)
    fact_store: Optional[FactStore]
    value_reader: Optional[ValueReader]    # MMapReader or ChunkedReader

    mode: SpillState

    # Unified query interface (works in both modes)
    def get_facts_by_concept(self, concept: QName) -> Iterable[Fact]
    def get_facts_by_context(self, ctx_id: ContextID) -> Iterable[Fact]
    def iter_facts(self) -> Iterator[Fact]
    def get_fact_count(self) -> int
    def hydrate_fact(self, ref: FactReference) -> Fact    # streaming only, LRU cached
```

### 9B — `src/core/model/builder.py`, `builder_streaming.py`, `builder_oim.py`

```text
builder.py — DOM mode:
  ModelBuilder.build(raw: RawXBRLDocument, taxonomy: TaxonomyModel) -> XBRLInstance
  ModelBuilder.build_from_inline(inline: InlineXBRLDocument, taxonomy) -> XBRLInstance
    For iXBRL: first apply transforms, then build as XBRL, then mark hidden.

builder_streaming.py — streaming mode:
  StreamingModelBuilder.build(parse: StreamingParseResult, taxonomy, source_file) -> XBRLInstance
    Creates store-backed XBRLInstance.
    PASS 2: iterates fact_store, classifies each FactReference (period_type, balance_type).
      In-memory mode: update objects in place.
      Disk mode: UPDATE facts SET period_type=?, balance_type=? WHERE idx=?; batched 10K.
    Sets up value_reader (MMapReader if SSD confirmed, ChunkedReader otherwise).

builder_oim.py — OIM (JSON/CSV) mode:
  OIMModelBuilder.build_json(doc, taxonomy) -> XBRLInstance
  OIMModelBuilder.build_csv(doc, taxonomy) -> XBRLInstance
    OIM has a canonical fact model — facts have named aspects, not refs to contexts/units.
    This builder constructs synthetic Context and Unit objects to fit the XBRLInstance shape,
    so downstream validators are format-agnostic.
    Equivalence: OIM round-trip to XML must produce OIM-equivalent facts.
```

### 9C — `src/core/model/merge.py`

```text
CLASS: ModelMerger
  merge(self, instances: List[XBRLInstance]) -> XBRLInstance

VALIDATION:
  - All instances same entity (else MERGE-0001)
  - No context ID collisions (else MERGE-0002)
  - No unit ID collisions (else MERGE-0003)
  - No fact ID collisions (else MERGE-0004)
  - Cross-document continuation chains (ESEF multi-doc):
      collect all ix:continuation declarations, resolve chains that span documents.

USAGE:
  ESEF filings can have multiple iXBRL documents (report + notes).
  SEC multi-doc filings (exhibits).
  Merger unifies them into one XBRLInstance for validation.

ERROR CODES: MERGE-0001..0010
```

### 9D — `src/core/model/equivalence.py`

```text
MODULE: equivalence (for OIM round-trip validation)

  def facts_equivalent(a: Fact, b: Fact) -> bool
    # Per OIM §5.3 fact equivalence:
    # - same concept (after QName canonicalization)
    # - same dimension set (key equal)
    # - same period
    # - same unit (normalized)
    # - same language (for non-numeric)
    # - same numeric value within decimals tolerance

  def instances_round_trip_equivalent(orig: XBRLInstance, roundtrip: XBRLInstance,
                                       tolerance_mode: str = "strict") -> List[str]
    # Returns list of diff descriptions, empty if equivalent.
    # tolerance_mode = "strict" | "decimals" | "lossy"
```

### 9E — `src/core/networks/` (new in v3, was implicit in v2)

```text
base_set.py — computes "base set" per XBRL 2.1 §4.11.1.2:
  For each (role, arcrole), collect all arcs from all linkbases in DTS that share
  the same role+arcrole. Apply prohibition/override to produce the "effective" arc set.

prohibition.py:
  Implements XBRL 2.1 §3.5.3:
    arcs with higher priority override equivalent arcs with lower priority
    use="prohibited" at priority P cancels all equivalent arcs with priority <= P
    Equivalence key: (from, to, arcrole, plus non-exempt attributes — see spec)

presentation_network.py:
  Builds tree(s) for parent-child arcrole.
  Handles preferredLabel for each arc.
  Cycle detection (presentation cycles are errors).

calculation_network.py:
  Summation-item arcs. Handles weights.
  Calculation 1.0 and 1.1 use different arcroles — separate networks.

definition_network.py:
  Dimension arcs (all/notAll, hypercube-dimension, dimension-domain, domain-member,
  dimension-default), plus general-special, essence-alias, similar-tuples,
  requires-element.

label_network.py / reference_network.py:
  concept-label and concept-reference arcs.
  Resolves locators to concepts.

generic_network.py:
  Generic Links arcs (element-label, element-reference, and any custom arc).
```

---
## 10. VALIDATION PIPELINE

### 10A — `src/validator/pipeline_config.py` + `pipeline.py`

```text
DATACLASS: PipelineConfig
  # inputs
  input_files: List[str]
  taxonomy_packages: List[str]
  catalog_files: List[str]

  # regulator
  regulator: Optional[RegulatorId]
  auto_detect_regulator: bool = True

  # spec toggles (all default True for regulator-grade)
  enable_xbrl21: bool = True
  enable_dimensions: bool = True
  enable_calculation_classic: bool = True
  enable_calculation_1_1: bool = True
  enable_formula: bool = True
  enable_table: bool = True
  enable_inline: bool = True
  enable_label: bool = True
  enable_presentation: bool = True
  enable_definition: bool = True
  enable_enumerations: bool = True
  enable_oim: bool = True
  enable_versioning: bool = True

  # extras
  enable_ai: bool = False
  enable_cross_document: bool = False
  enable_arelle_compat_output: bool = True
  enable_xule: bool = True

  # large-file
  large_file_threshold_bytes: int = 100 * MB
  huge_file_threshold_bytes: int = 1 * GB
  memory_budget_bytes: int = 4 * GB
  fact_index_spill_fact_count: int = 5_000_000
  fact_index_spill_bytes: int = 500 * MB
  io_chunk_size: int = 64 * MB
  force_streaming: bool = False
  force_disk_spill: bool = False

  # limits
  max_file_size_bytes: int = 10 * GB
  max_errors: int = 100_000
  max_zip_uncompressed_bytes: int = 5 * GB
  max_continuation_depth: int = 1000

  # timeouts
  taxonomy_fetch_timeout_s: int = 30
  formula_timeout_s: int = 600
  xule_timeout_s: int = 300

  # behavior
  treat_warnings_as_errors: bool = False
  offline: bool = False
  allow_remote_taxonomies: bool = True
  allow_http: bool = False

  # parallelism
  parallel_spec_validators: bool = True
  parallel_workers: int = 4

  # paths
  taxonomy_cache_dir: str = "~/.xbrl-validator/cache"
  temp_dir: str = tempfile.gettempdir()

  # extensions
  custom_rule_paths: List[str] = []
  xule_rule_sets: List[str] = []

  # output
  output_format: str = "json"           # json | sarif | html | csv | junit | arelle
  output_file: Optional[str] = None

CLASS: ValidationPipeline
  STAGES (in order, each wraps its own try/except and timing):
    1. detect          — format detection + storage type
    2. parse           — DOM or streaming parse
    3. dts_resolve     — taxonomy via TaxonomyResolver (with cache warmup)
    4. model_build     — build XBRLInstance (DOM, streaming, or OIM builder)
    5. spec_validate   — run ALL spec validators (parallel where safe)
    6. formula_eval    — formula assertions (may be large, separate stage)
    7. table_render    — table layout (if enabled and tables present)
    8. regulator_rules — load profile, run regulator validators
    9. xule_eval       — run XULE rule sets (if any)
    10. oim_roundtrip  — XBRL↔OIM round-trip check (if enabled)
    11. ai_reasoning   — fix suggestions, business rules (if enabled)
    12. self_check     — dedup, severity verification, sort
    13. report         — format output

  run(self) -> PipelineResult
    For each stage:
      - record start_ts, memory_before
      - try: stage.execute()
      - except: accumulate as ValidationMessage (or abort if critical)
      - record end_ts, memory_after, items_processed
      - log structured event
    PipelineAbortError skips remaining stages.
    Non-critical exceptions continue pipeline with error logged.

  PARALLEL SPEC VALIDATION:
    Some spec validators are independent (dimensions, labels, presentation).
    Others depend on model state set by earlier ones (calculation depends on
    fact value hydration). Dependency graph:
      xbrl21 → (dimensions, label, presentation, definition, enumerations) → calculation → oim_roundtrip
    Parallelized within each level via ProcessPoolExecutor.
    Formula runs sequentially after (uses all prior context).

DATACLASS: PipelineResult
  success: bool
  messages: List[ValidationMessage]
  error_count: int
  warning_count: int
  info_count: int
  inconsistency_count: int
  facts_validated: int
  concepts_used: int
  contexts_count: int
  elapsed_seconds: float
  stages_completed: List[str]
  stage_timings: Dict[str, float]
  memory_peak_bytes: int
  spill_occurred: bool
  files_processed: List[str]
  parsing_strategy: ParserStrategy
  instance: Optional[XBRLInstance]      # if retained

  to_json() -> dict
  to_sarif() -> dict
  to_html() -> str
  to_csv() -> str
  to_junit() -> str
  to_arelle_compat() -> str
```

---

## 11. SPECIFICATION VALIDATORS

Every spec validator MUST pass the corresponding XBRL International conformance suite
before merge (Rule 8).

### 11A — XBRL 2.1 — `src/validator/spec/xbrl21/`

```text
Full XBRL 2.1 validation. ~40 checks (v2 had 25; this covers the spec completely).
Error codes: XBRL21-0001..0040. Spec: XBRL 2.1 (2003-12-31, errata 2013-02-20).

instance.py:
  XBRL21-0001 Missing xbrl root element
  XBRL21-0002 Invalid XML Schema location
  XBRL21-0022 Missing schemaRef
  XBRL21-0026 xsi:schemaLocation references without schemaRef (WARN)
  XBRL21-0027 linkbaseRef with role extended-link-role-not-allowed

context.py:
  XBRL21-0001 Missing entity identifier
  XBRL21-0002 Missing period
  XBRL21-0003 Invalid instant date
  XBRL21-0004 startDate > endDate
  XBRL21-0005 Duplicate context ID
  XBRL21-0019 Invalid entity identifier scheme URI
  XBRL21-0028 S-Equal context check (duplicate contexts with same content)
  XBRL21-0029 Segment without dimension AND without non-XDT content
  XBRL21-0030 Scenario empty

unit.py:
  XBRL21-0006 Duplicate unit ID
  XBRL21-0007 Unit missing measure
  XBRL21-0016 Monetary fact requires ISO 4217 unit
  XBRL21-0017 Shares fact requires xbrli:shares unit
  XBRL21-0018 Pure fact requires xbrli:pure unit
  XBRL21-0031 Unit divide missing numerator
  XBRL21-0032 Unit divide missing denominator
  XBRL21-0033 UTR mismatch (if UTR enforcement on)

fact.py:
  XBRL21-0008 Fact references unknown context
  XBRL21-0009 Numeric fact missing unitRef
  XBRL21-0010 Numeric fact missing decimals AND precision
  XBRL21-0011 Both decimals AND precision specified
  XBRL21-0012 Nil fact has value
  XBRL21-0013 Concept not in taxonomy
  XBRL21-0014 Fact type mismatch (numeric fact with non-numeric concept)
  XBRL21-0015 Period type mismatch (instant vs duration)
  XBRL21-0020 Conflicting duplicate facts (same concept+context+unit, different values
              beyond decimals tolerance) — this is the "c-equal duplicates" rule
  XBRL21-0023 Missing xml:lang for string concept
  XBRL21-0034 xml:lang not a valid BCP 47 tag
  XBRL21-0035 Fact value fails type restriction (xs:positiveInteger negative, etc.)
  XBRL21-0036 Nil fact on concept with nillable=false

tuple.py:
  XBRL21-0021 Tuple ordering violation (children out of schema-declared order)
  XBRL21-0037 Tuple content model violation (missing required child)
  XBRL21-0038 Tuple cardinality violation

footnote.py:
  XBRL21-0024 Invalid footnote role
  XBRL21-0025 Missing footnote xml:lang
  XBRL21-0039 Footnote link with no footnotes
  XBRL21-0040 Fact-footnote arc references non-existent fact

schema_ref.py:
  Validates schemaRef/linkbaseRef/roleRef/arcroleRef XLink attributes.

LARGE-FILE HANDLING:
  All fact iteration uses fact_store.iter_batches(10000).
  Duplicate detection:
    In-memory: computed via fact_index.get_duplicate_groups()
    On-disk:   SELECT concept, context_ref, unit_ref, language, COUNT(*)
               FROM facts GROUP BY ... HAVING COUNT(*) > 1
  Both load values only for facts in duplicate groups (via value_reader).
```

### 11B — XBRL Dimensions (XDT) 1.0 — `src/validator/spec/dimensions/`

```text
FULL XDT 1.0 implementation. Arelle-competitive. This is a LOT more than v2's 10 checks.

Error codes: DIM-0001..0030.
Spec: XBRL Dimensions 1.0 (2012-01-25).

hypercube.py:
  DIM-0001 Member not in domain
  DIM-0003 Hypercube violated (fact has dim not in its applicable hypercube)
  DIM-0008 has-hypercube violated
  DIM-0010 all/notAll arc violation (closed hypercube with disallowed dim)
  DIM-0015 Hypercube declared without has-hypercube in context
  DIM-0016 Multiple has-hypercube for same concept with same role (ambiguity)

domain_member.py:
  Walks domain-member network from each hypercube's dimension-domain targets.
  Applies usable=false to exclude non-usable members.
  Handles targetRole to cross roles mid-traversal.
  DIM-0002 Member not in domain for dim D (specific to fact)
  DIM-0017 Circular domain-member relationship
  DIM-0018 Domain-member depth exceeds MAX_HYPERCUBE_DEPTH

typed_dimension.py:
  DIM-0002 Typed dim value invalid (doesn't match xs:simpleType)
  For each typed dim used in a context:
    - Locate typedDomainRef from dim declaration
    - Resolve to xs:simpleType in DTS
    - Validate typed value against simpleType
      (facets: enumeration, pattern, minInclusive, maxInclusive, length, etc.)
    - Handle xs:union, xs:list types
  Uses xmlschema or lxml.etree.XMLSchema for validation.

dimension_default.py:
  DIM-0005 Default member explicitly used (XDT §2.8.1: default must not appear in context)
  DIM-0007 Multiple dimension-default arcs from same dimension
  DIM-0019 Default member is not a valid member for dimension

target_role.py:
  DIM-0020 targetRole resolved to non-existent role
  Handles recursive targetRole chains (with cycle detection).

usable.py:
  Implements usable attribute on domain-member arcs (XDT §2.4.1.3).
  Handles priority/prohibition interaction.
  DIM-0021 Usable overridden inconsistently across networks

all_notall.py:
  DIM-0004 Undeclared dimension in context (all arc closure violated)
  DIM-0010 Dimension present that notAll forbids
  DIM-0022 contextElement mismatch (segment/scenario)

closed_hypercube.py:
  DIM-0023 Closed hypercube with extra dimension
  DIM-0024 Closed="false" when MUST be true per structure

context_validator.py:
  Entry point: validate_context_against_hypercubes(context, concept, taxonomy).
  Pre-computed mapping: concept → [(role, hypercube, is_closed)]
  For each applicable hypercube:
    Check all context dims are in hypercube (closed) or compatible (open).
    Check required dims present (unless has default).
    Check no prohibited dims (notAll).

OPTIMIZATION:
  Pre-compute concept → applicable hypercubes mapping ONCE per instance.
  Pre-compute hypercube → allowed dimension members ONCE.
  Context-level checks: O(facts × dims) not O(facts × dims × hypercubes).
  For large files: contexts stay in memory; only fact iteration is streaming.

DIMENSIONS CONFORMANCE:
  Must pass XBRL Dimensions 1.0 conformance suite 200+ test cases.
```

### 11C — XBRL Calculation — `src/validator/spec/calculation/`

```text
BOTH Calculation 1.0 (classic) AND Calculation 1.1 (2023).

classic.py (Calc 1.0, XBRL 2.1 §5.2.5):
  CALC-0001 Zero weight
  CALC-0002 Summation inconsistency (|Σ weighted_children − parent| > tolerance)
  CALC-0003 Rounding inconsistency exceeded
  CALC-0004 Missing contributing fact (parent exists but children don't)
  CALC-0005 Cross-unit calculation (children in different units than parent)
  CALC-0006 Circular calculation (detected during network build)

calc_1_1.py (Calc 1.1, 2023):
  NEW ARCROLE: https://xbrl.org/2023/arcrole/summation-item
  NEW RULES for duplicate-fact handling (below).
  CALC11-0001..0010

  Calc 1.1 introduces:
    - "Inclusive" vs "Exclusive" models for duplicate facts
    - Explicit Y/N consistency flag per binding
    - Rounded-value semantics (duplicates rounded to min decimals before compare)
    - New "summation" vs "summation-item" naming

tolerance.py:
  Per XBRL 2.1 §5.2.5.2:
    child_tol_i = 0.5 × 10^(-decimals_i)   if decimals_i != "INF"
    child_tol_i = 0                         if decimals_i == "INF"
    total_child_tol = sum(|weight_i| × child_tol_i)
    parent_tol = 0.5 × 10^(-decimals_parent)
    allowed = total_child_tol + parent_tol
    ALL Decimal. precision=28.

rounding.py:
  round_to_decimals(value: Decimal, decimals: Union[int, Literal["INF"]]) -> Decimal
    Uses ROUND_HALF_UP per XBRL 2.1 convention.

duplicate_handler.py (Calc 1.1):
  For "inclusive" model:
    If multiple facts for same (concept, context, unit):
      - Compute min(decimals) across dupes
      - Round each to min decimals
      - If all agree → use common value
      - If disagree → emit CALC11-0003, use any one
  For "exclusive" model:
    If duplicates exist → skip this binding (no consistency check).

network_walker.py:
  BFS from each root concept in calc network.
  For each parent binding (parent fact + its descendant arc path):
    - Collect child facts with matching context+unit
    - Apply weights, sum, compare
    - Emit CALC-0002 if exceeds tolerance

LARGE-FILE VALUE LOADING:
  1. Walk calc linkbase → identify (parent_concept, [child_concept]) groups per role
  2. Get parent fact refs: fact_store.get_by_concept(parent)
  3. For each parent fact: find children with matching context+unit:
     refs = fact_store.get_by_concept_and_context(child, ctx)
  4. Pre-sort ALL needed byte offsets across all calc checks
  5. Use ChunkedReader or MMapReader to batch-read values
  6. Convert to Decimal (value_reader returns bytes → str → Decimal per Rule 16)
  7. Compute check, emit message
  8. LRU cache of loaded values (10K capacity) for re-use across checks

CALC CONFORMANCE:
  Calc 1.0 via XBRL 2.1 conformance suite.
  Calc 1.1 via separate Calculation 1.1 conformance suite (2024).
```

### 11D — XBRL Formula 1.0 — `src/validator/spec/formula/`

**This was a single file in v2. In reality, it is a major subsystem.**

```text
SPEC: Formula 1.0 (2009-06-22, plus subsequent errata).
SUBORDINATE SPECS implemented:
  - Formula 1.0 (variable-set, assertions, filters, generators, messages)
  - XPath 2.0 / 3.1 (via elementpath)
  - XBRL Functions Registry
  - Aspect Cover Filter 1.0
  - Generic Messages 1.0
  - Custom Functions 1.0

evaluator.py:
  CLASS: FormulaEvaluator
    __init__(self, instance: XBRLInstance, config: PipelineConfig)
    evaluate_all(self) -> List[FormulaResult]
    evaluate_variable_set(self, vs: VariableSet) -> List[FormulaResult]

  ALGORITHM for each variable set:
    1. Resolve variables (fact variables, general variables)
    2. Apply filters to each fact variable to get fact bindings
    3. Compute cross-product of bindings (matching on aspects per aspectModel)
    4. For each binding combination:
       a. Evaluate preconditions (skip if false)
       b. Evaluate assertion:
          - ValueAssertion: eval test XPath → boolean → emit message if false
          - ExistenceAssertion: count facts matching → compare → emit
          - ConsistencyAssertion: formula output vs fact values → compare
       c. Accumulate results
    5. Apply assertion-set-level aggregation if in assertion set

assertion.py:
  ValueAssertion
    test: XPath expression
    evaluates: boolean
  ExistenceAssertion
    test: XPath (operates on count)
  ConsistencyAssertion
    formula: reference to a Formula
    strict: bool
    proportionalAcceptanceRadius: Optional[Decimal]
    absoluteAcceptanceRadius: Optional[Decimal]

variable_set.py:
  VariableSet
    implicitFiltering: bool
    aspectModel: "dimensional" | "non-dimensional"
    variables: List[Variable]
    filters: List[Filter]
    preconditions: List[Precondition]
    assertion: Optional[Assertion]        # or formula if variable-set-formula

variable.py:
  FactVariable
    fallbackValue: Optional[XPath]
    matches: bool                         # matches filter specifies sequence vs single
    nils: bool                            # include/exclude nil facts
    bindAsSequence: bool
  GeneralVariable
    select: XPath

filters/concept_filter.py + 10 more filter types:
  Each filter has evaluate(candidate_facts: Iterable[Fact]) → filtered facts.
  Filters compose via intersection (AND semantics within a variable set).

filters/period_filter.py:
  Many sub-types: instant, instant-duration, period, period-start, period-end,
  period-instant, forever, duration, single-period, multiple-periods.

filters/dimension_filter.py:
  explicit-dimension, typed-dimension.
  With filter members specified by QName reference or by XPath expression.

filters/general_filter.py:
  Arbitrary XPath boolean filter over fact context.

filters/match_filter.py:
  match-concept, match-location, match-period, match-unit, match-dimension.
  Binds across variables (e.g., "fact B must match fact A's concept").

filters/relative_filter.py:
  Filter that references another variable for comparison.

filters/boolean_filter.py:
  and-filter, or-filter — compose sub-filters.

filters/aspect_cover.py:
  Aspect Cover Filter 1.0 — declares which aspects this filter affects.

aspect_rule.py:
  For formula output: specifies how output aspect values are computed.

generator.py:
  Formula generators: functions produce filtered fact sets dynamically.

custom_function.py:
  Custom XPath functions declared in DTS + implemented by user.
  Registry maps QName → Python callable.

xpath_bridge.py:
  Integrates elementpath.XPath2Parser.
  Exposes XBRL-specific contexts:
    $fact, $context, $period, $unit, $concept
    xfi:* functions (XBRL Functions Registry)

xpath_functions.py:
  XFI function implementations:
    xfi:fact-has-explicit-dimension
    xfi:fact-explicit-dimension-value
    xfi:fact-typed-dimension-value
    xfi:concept-balance
    xfi:concept-period-type
    xfi:concept-substitutions
    xfi:period-start
    xfi:period-end
    xfi:unit-numerator
    xfi:unit-denominator
    xfi:u-equal, xfi:uv-equal, xfi:v-equal, xfi:c-equal, xfi:identical-set
    xfi:duplicate-item
    xfi:precision, xfi:decimals, xfi:nilled
    ... (50+ functions)

PERFORMANCE:
  Query planner (similar to XULE) pushes concept/context filters into fact_store lookups.
  Worst case (general-filter only) falls back to full scan.
  Timeout per variable set: 600s default. FormulaTimeoutError on exceed.

ERROR CODES: FORMULA-0001..0020
CONFORMANCE: Formula 1.0 suite has ~1000 test cases. Target 95%+ pass rate.
```

### 11E — iXBRL 1.1 — `src/validator/spec/inline/`

```text
SPEC: iXBRL 1.1 (2013-11-18). Arelle-parity expected.
Error codes: IXBRL-0001..0045.

header.py:
  IXBRL-0001 Missing ix:header
  IXBRL-0005 ix:header in wrong location
  IXBRL-0006 Multiple ix:header elements (only one per target allowed)
  IXBRL-0007 Missing ix:references (if any roleRef/arcroleRef needed)

non_fraction.py:
  IXBRL-0010 ix:nonFraction missing format attribute for transform-needing content
  IXBRL-0011 ix:nonFraction missing unitRef for numeric concept
  IXBRL-0012 ix:nonFraction nested (not allowed)
  IXBRL-0013 scale without format

non_numeric.py:
  IXBRL-0014 ix:nonNumeric for numeric concept

fraction.py:
  IXBRL-0015 ix:fraction without numerator
  IXBRL-0016 ix:fraction without denominator
  IXBRL-0017 ix:fraction nested inside ix:nonFraction

tuple.py:
  IXBRL-0018 ix:tuple with mixed namespaces
  IXBRL-0019 ix:tuple ordering violation
  IXBRL-0020 ix:tuple with non-fact child

continuation.py:
  IXBRL-0002 Broken continuation chain (continuedAt references non-existent id)
  IXBRL-0003 Circular continuation chain
  IXBRL-0004 Continuation chain exceeds max depth
  IXBRL-0021 Continuation target not ix:continuation
  IXBRL-0022 ix:continuation used but not referenced

exclude.py:
  IXBRL-0023 ix:exclude outside of fact content

reference.py:
  IXBRL-0024 ix:references missing required schemaRef
  IXBRL-0025 ix:references with roleRef missing xlink:href

relationship.py:
  IXBRL-0026 ix:relationship invalid arcrole
  IXBRL-0027 ix:relationship from/to references non-existent id

footnote.py:
  IXBRL-0028 ix:footnote missing xml:lang

hidden.py:
  IXBRL-0029 ix:hidden with non-numeric/non-fact content
  IXBRL-0030 ix:hidden in wrong location (not a direct child of ix:header)

transforms.py:
  IXT-0001 Unknown transform format
  IXT-0002 Transform format does not match value
  IXBRL-0031 format declared but value parses unchanged
  IXBRL-0032 Transform version mismatch with declared ix:* namespace

target_document.py:
  IXBRL-0033 Multi-target document: target attribute references undeclared target
  IXBRL-0034 Target document missing ix:references

CONTINUATION ALGORITHM (detailed):
  1. Collect all ix:continuation elements by id
  2. For each fact with continuedAt:
     chain = [fact]
     visited = set()
     current = fact.continuedAt
     while current is not None:
       if current in visited: → IXBRL-0003
       visited.add(current)
       cont = continuations.get(current)
       if cont is None: → IXBRL-0002
       chain.append(cont)
       if len(chain) > max_continuation_depth: → IXBRL-0004
       current = cont.continuedAt
     # Now concat content, skipping ix:exclude subtrees
     fact.full_content = "".join(c.text_content for c in chain)

CONFORMANCE: iXBRL 1.1 conformance suite, ~300 test cases.
```

### 11F — Table Linkbase — `src/validator/spec/table/`

**v2 budgeted one file; this is a full subsystem.**

```text
SPEC: Table Linkbase 1.0 (2014-03-18).
Purpose: validates table structure AND produces rendered output for reporting.

table_model.py:
  Table, Breakdown, AxisBreakdown, Node hierarchy.

breakdown.py, axis.py, rule_node.py,
concept_relationship_node.py, dimension_relationship_node.py, aspect_node.py:
  Node types from spec.

structural_layout.py:
  Builds structural axes from breakdown definitions.
  Resolves filters per axis, yielding layout nodes.

fact_layout.py:
  Given a structural layout and the instance, binds facts into cells.
  Produces the logical rendered table (rows × cols × facts).

renderer.py:
  Produces HTML/JSON/CSV rendering of the table (used by report generator).

validator.py:
  TBL-0001 Breakdown missing tree
  TBL-0002 Axis without nodes
  TBL-0003 Circular concept-relationship-node
  TBL-0004 Fact not bound to any cell (warning)
  TBL-0005 Multiple facts in a single cell conflict
  TBL-0006 Axis filter inconsistent with breakdown
  TBL-0007 Table parameter undefined
  TBL-0008 Aspect node with invalid aspect QName
  TBL-0009 Rule node rule references undeclared member

CONFORMANCE: Table Linkbase 1.0 suite, ~400 test cases.
```

### 11G — Label / Presentation / Definition / Reference

```text
label/label_validator.py:
  LBL-0001 Duplicate (role, lang) labels for same concept
  LBL-0002 Missing standard label
  LBL-0003 Label role not in LRR and not declared in DTS
  LBL-0004 Label language not valid BCP 47
  LBL-0005 Arc from concept to non-label element
  LBL-0006 Circular label arcs (shouldn't happen but guard)

label/uniqueness.py:
  Enforces (concept, role, lang) uniqueness per XBRL 2.1.

label/language.py:
  BCP 47 language tag validation.

presentation/network_validator.py:
  PRES-0001 Cycle in presentation tree
  PRES-0002 Child appears under multiple parents within same role (warn)
  PRES-0003 order attribute duplicated for siblings
  PRES-0004 preferredLabel role not declared

presentation/ordering.py:
  Builds tree per role, validates order attributes.

presentation/preferred_label.py:
  Validates preferredLabel roles exist in label linkbase.

definition/network_validator.py:
  DEF-0001 Cycle in general-special
  DEF-0002 Cycle in essence-alias
  DEF-0003 Similar-tuples on non-tuple
  DEF-0004 Requires-element violated (concept required but fact missing)

definition/general_special.py, essence_alias.py, similar_tuples.py, requires_element.py:
  Specific validator for each arcrole.

reference/reference_validator.py:
  REF-0001 Reference arc to non-reference element
  REF-0002 Reference missing required parts (per role)
```

### 11H — Generic Links — `src/validator/spec/generic/`

```text
SPEC: Generic Links 1.0.
Used by: formula, table, custom extensions.

GEN-0001 Generic arc outside generic link
GEN-0002 Generic arc with XLink href that doesn't resolve
GEN-0003 Generic label arc arcrole mismatch
GEN-0004 Generic reference arcrole mismatch
```

### 11I — Extensible Enumerations 2.0 — `src/validator/spec/enumerations/`

```text
SPEC: Extensible Enumerations 2.0.
Concept type is xbrlenum2:enumerationItemType or enumerationSetItemType.
Fact value must be a QName (or list of QNames) referencing allowed domain members.

enum_validator.py:
  ENUM-0001 Enum fact value not a valid QName
  ENUM-0002 Enum fact value references undeclared concept
  ENUM-0003 Enum fact value not in declared domain
  ENUM-0004 Enum concept missing enum:linkrole annotation
  ENUM-0005 Enum concept missing enum:domain annotation

enum_set_validator.py:
  ENUM-0006 Enum set fact duplicates values
  ENUM-0007 Enum set fact values not lexically sorted (warning)
```

### 11J — OIM (XBRL-JSON / XBRL-CSV) — `src/validator/spec/oim/`

**v2 treated OIM as parser-only. It's actually a semantic validation layer.**

```text
SPEC: OIM 1.0 (2021-10-13), plus XBRL-JSON 1.0 and XBRL-CSV 1.0.

canonical_model.py:
  Defines the OIM canonical fact model (aspect-based, not context-based).
  Conversion XBRLInstance ↔ OIMModel.

fact_equivalence.py:
  Full OIM fact equivalence algorithm (§5.3):
    - Aspect equality: concept, entity, period, unit, language, noteId, dimensions
    - Numeric equality honoring decimals
    - C-equal, U-equal checks

json_validator.py:
  Validates XBRL-JSON structural requirements:
    OIM-JSON-0001 Missing documentInfo
    OIM-JSON-0002 Invalid namespaces section
    OIM-JSON-0003 Fact without concept aspect
    OIM-JSON-0004 Unknown dimension QName
    OIM-JSON-0005 Fact value wrong type for concept
  Validates JSON schema conformance (against official OIM JSON schema).

csv_validator.py:
  Validates XBRL-CSV:
    OIM-CSV-0001 Missing metadata.json
    OIM-CSV-0002 Undeclared column
    OIM-CSV-0003 Row aspect value inconsistent with column definition
    OIM-CSV-0004 Decimal precision loss in CSV encoding
    OIM-CSV-0005 Missing required aspect column

round_trip.py:
  Round-trip check:
    1. Parse input as format X (XML/JSON/CSV)
    2. Convert to canonical OIM model
    3. Serialize to format Y
    4. Re-parse
    5. Canonical OIM model must be equivalent
  Finds lossy conversion bugs.

report_info.py:
  Validates reportInfo / documentInfo metadata:
    OIM-INFO-0001 Unknown taxonomy
    OIM-INFO-0002 Conflicting namespace declarations
    OIM-INFO-0003 Missing required metadata field

CONFORMANCE: OIM 1.0 conformance suite.
```

### 11K — Versioning Report — `src/validator/spec/versioning/`

```text
SPEC: Versioning 1.0 (2013-02-13).
Validates versioning reports describing differences between taxonomies.

VER-0001 Versioning report references non-existent concept
VER-0002 Circular aliasing
VER-0003 Inconsistent dimensional-change report
```

---
## 12. REGULATOR MODULES

Loaded dynamically via `src/plugin/profile_loader.py`. `src/core/*` and `src/validator/spec/*`
must NEVER import from these (Rule 5, enforced by import-linter).

Each regulator has its own subdirectory. The combined regulator code is ~40% of the
codebase — v2 drastically under-sized this.

### 12A — SEC EDGAR Filer Manual (EFM) — `src/validator/regulator/efm/`

**The EFM is a 600+ page manual. v2's "~30 rules" is wrong; full EFM is ~150 rules.**

```text
efm_validator.py (orchestrator):
  EFMValidator.__init__(self, instance, profile: EFMProfile)
  EFMValidator.validate() → List[ValidationMessage]

  Orchestration:
    form_type = form_router.detect(instance)
    form_rules = profile.rules_for_form(form_type)
    results = []
    for rule_category in [dei, cik, negation, naming, period, share_class,
                          role_hierarchy, presentation, label, hidden_facts,
                          structural, ixbrl, form_specific]:
      results.extend(rule_category.validate(instance, profile, form_type))
    return results

dei.py (Document and Entity Information — EFM 6.5.x):
  EFM-DEI-0001 Missing DocumentType
  EFM-DEI-0002 Missing EntityRegistrantName
  EFM-DEI-0003 Missing EntityCentralIndexKey
  EFM-DEI-0004 EntityCentralIndexKey not 10 digits
  EFM-DEI-0005 DocumentPeriodEndDate missing or invalid
  EFM-DEI-0006 DocumentFiscalYearFocus inconsistent
  EFM-DEI-0007 DocumentFiscalPeriodFocus not in {FY, Q1, Q2, Q3}
  EFM-DEI-0008 AmendmentFlag not boolean
  EFM-DEI-0009 DocumentType not in permitted set for form type
  EFM-DEI-0010 EntityFilerCategory missing (10-K/10-Q/20-F)
  EFM-DEI-0011 EntityEmergingGrowthCompany missing
  EFM-DEI-0012 EntityAddressesLineItems mandatory (for specific forms)
  EFM-DEI-0013 EntityCommonStockSharesOutstanding missing (10-K/10-Q)
  EFM-DEI-0014 EntityRegistrantName contains improper characters
  EFM-DEI-0015 TradingSymbol for each security listed
  EFM-DEI-0016 Security12bTitle for each listed security
  EFM-DEI-0017 SecurityExchangeName from permitted set
  EFM-DEI-0018 EntityAddressPostalZipCode format for country
  EFM-DEI-0019 EntityIncorporationStateCountryCode ISO 3166-2
  EFM-DEI-0020 EntityTaxIdentificationNumber format
  EFM-DEI-0021 EntityFileNumber SEC file number format
  EFM-DEI-0022 DEI facts use dei/us-gaap namespaces only (no custom extension for DEI)
  EFM-DEI-0023 DocumentPeriodEndDate context must match DocumentPeriodEndDate value
  EFM-DEI-0024 CoverPage role used for DEI facts
  EFM-DEI-0025 AuditorName / AuditorFirmId / AuditorLocation (10-K only, since 2022)
  (additional rules for specific forms)

cik.py:
  EFM-CIK-0001 Fact context entity scheme must be http://www.sec.gov/CIK
  EFM-CIK-0002 Fact context entity identifier must equal DEI CIK
  EFM-CIK-0003 CIK format (zero-padded 10 digits)
  EFM-CIK-0004 Multiple distinct CIKs across contexts (error)

negation.py (NEGVAL — EFM 6.11.x):
  SEC maintains a NEGVAL list of concepts where a negated label is required
  when the fact value is opposite the concept's semantic sign.

  EFM-NEG-0001 Concept in NEGVAL list but no negated-label arc present for the
               context of a negative-signed fact
  EFM-NEG-0002 Concept not in NEGVAL list but negated label used
  EFM-NEG-0003 Negated label but label value not actually inverted
  EFM-NEG-0004 Inconsistent negated-label use across facts of same concept

  The NEGVAL catalog itself is loaded from config/profiles/efm/negation_rules.yaml
  (derived from SEC's published list).

naming.py (extension naming — EFM 6.7.x):
  EFM-NAM-0001 Extension concept name matches a standard concept (case-insensitive)
  EFM-NAM-0002 Extension concept name contains lowercase letters followed by upper
  EFM-NAM-0003 Extension concept name too long (> 200 chars)
  EFM-NAM-0004 Extension concept name contains disallowed punctuation
  EFM-NAM-0005 Extension concept in wrong namespace for filer CIK
  EFM-NAM-0006 Extension namespace format: http://{entity-url}/{yyyymmdd}
  EFM-NAM-0007 Extension schema filename format (cik-yyyymmdd.xsd)
  EFM-NAM-0008 Extension schema version in name doesn't match fiscal period

period.py (EFM 6.6.x):
  EFM-PER-0001 Duration context end date mismatches DocumentPeriodEndDate
  EFM-PER-0002 Instant context date after DocumentPeriodEndDate
  EFM-PER-0003 Interim period duration > 365 days (10-Q limit)
  EFM-PER-0004 Annual period duration not ≈ 365 days
  EFM-PER-0005 Period contains >5 distinct years (ambiguous)
  EFM-PER-0006 Forever context used (not allowed in EFM)

share_class.py:
  EFM-SHR-0001 EntityCommonStockSharesOutstanding missing per class
  EFM-SHR-0002 Share class axis used but no values
  EFM-SHR-0003 Multiple share class values without us-gaap:ClassOfStockDomainAxis
  EFM-SHR-0004 Share count context date after DocumentPeriodEndDate + 90 days

role_hierarchy.py (EFM 6.7.x):
  EFM-ROL-0001 Custom role with invalid URI
  EFM-ROL-0002 Role used in presentation but not defined in schema
  EFM-ROL-0003 Presentation group ordering (roles must be in filer-specified order)
  EFM-ROL-0004 Role definition with improper prefix pattern
  EFM-ROL-0005 Presentation linkbase not ordered by role definition order

presentation.py:
  EFM-PRES-0001 Concept in instance not in any presentation tree
  EFM-PRES-0002 Presentation tree has orphan leaf concepts (warn)
  EFM-PRES-0003 Presentation root is not an abstract concept
  EFM-PRES-0004 Axis appears without corresponding LineItems

label.py:
  EFM-LBL-0001 Duplicate standard label across filer extension concepts
  EFM-LBL-0002 Label contains HTML tags (not permitted)
  EFM-LBL-0003 Label contains BOM or non-printable characters
  EFM-LBL-0004 Missing verbose label for extension concept > 100 chars

hidden_facts.py (EFM 6.12.x):
  EFM-HID-0001 Non-hidden fact appears also in hidden (duplicate)
  EFM-HID-0002 Hidden fact without a corresponding visible counterpart
                (where required by tagging rules)
  EFM-HID-0003 Hidden fact with continuation chain
  EFM-HID-0004 EFM permits hidden facts only for specific rationales (list)

structural.py:
  EFM-STR-0001 Multiple top-level <xbrl> elements
  EFM-STR-0002 Instance with external schema location
  EFM-STR-0003 Hyperlinked external resources in instance
  EFM-STR-0004 Disallowed namespace (e.g., XHTML) in instance

ixbrl.py (EFM 6.20.x — iXBRL specifics):
  EFM-IX-0001 Missing ix:header
  EFM-IX-0002 Multiple ix:header (allowed only one per target for EFM)
  EFM-IX-0003 ix:hidden used but no fact contained
  EFM-IX-0004 ix:exclude used outside a fact
  EFM-IX-0005 ix:references with foreign taxonomy URIs
  EFM-IX-0006 HTML document includes scripts (not permitted)
  EFM-IX-0007 HTML document includes forms/iframes
  EFM-IX-0008 Embedded image > size limit (EFM 6.5.28)
  EFM-IX-0009 Font-face declarations not allowed
  EFM-IX-0010 External stylesheets not permitted
  EFM-IX-0011 Javascript event handlers present
  EFM-IX-0012 Fact content in ix:hidden must not also appear in visible
  EFM-IX-0013 Continuation depth exceeds EFM limit (not identical to iXBRL spec)
  EFM-IX-0014 iXBRL format attribute references unknown transform version
  EFM-IX-0015 CSS property `position: fixed` disallowed

form_router.py:
  Inspects DocumentType fact value to route to form-specific validators.
  Falls back to filename pattern (form10k.xml → 10-K).

forms/form_10k.py, form_10q.py, form_8k.py, form_s1.py, form_20f.py:
  Form-specific mandatory elements, period constraints, cover page requirements.
  Form-specific rules are ~50 additional checks per form.

YAML/PYTHON RATIO:
  YAML: mandatory_elements, naming patterns, negation catalog (~30% of rules)
  Python: structural, cross-concept, NEGVAL logic, CIK semantics, role hierarchy,
          share class math, iXBRL-specific structure (~70% of rules)
  (v2 had this backwards.)

ERROR CODES: EFM-NNN-NNNN, ~150 codes.
```

### 12B — ESEF — `src/validator/regulator/esef/`

**v2's anchoring: a BFS. Real ESEF anchoring is 30+ specific rules.**

```text
esef_validator.py (orchestrator):
  ESEFValidator.validate() dispatches to sub-validators.
  Handles year-specific variations (ESEF 2020 vs 2022 vs 2024+).

package.py (ESEF 2.1.x — Report Package):
  ESEF-PKG-0001 Missing META-INF/taxonomyPackage.xml
  ESEF-PKG-0002 Missing META-INF/catalog.xml
  ESEF-PKG-0003 reports/ directory missing
  ESEF-PKG-0004 Multiple entry points where single required
  ESEF-PKG-0005 Entry point schema not in package
  ESEF-PKG-0006 Package contains disallowed files
  ESEF-PKG-0007 Package > 100 MB (ESMA soft limit)
  ESEF-PKG-0008 Package filename doesn't match LEI-dated pattern

signed_package.py (from ESEF 2024):
  Signed packages use XAdES detached signatures.
  ESEF-SIG-0001 Missing META-INF/signatures.xml
  ESEF-SIG-0002 Invalid XAdES signature structure
  ESEF-SIG-0003 Certificate chain not trusted
  ESEF-SIG-0004 Signature doesn't cover all package files
  ESEF-SIG-0005 Signing time outside report period

  Requires cryptography library (conditional import; documented in signed_package_rules.yaml).

anchoring.py (ESEF 3.4 — the BIG one):
  Anchoring = each extension concept must be anchored to at least one
  IFRS taxonomy concept via wider-narrower arc in a definition linkbase.

  ESEF-ANC-0001 Extension concept without ANY wider-narrower arc
  ESEF-ANC-0002 Extension concept's wider arc to another extension concept
                (must anchor to IFRS eventually)
  ESEF-ANC-0003 Circular wider-narrower relationship
  ESEF-ANC-0004 Extension wider arc points to deprecated IFRS concept
  ESEF-ANC-0005 Extension concept anchored to a concept of different data type
                (numeric concept anchored to non-numeric)
  ESEF-ANC-0006 Extension monetary concept anchored to non-monetary (warn)
  ESEF-ANC-0007 Extension period type differs from anchor period type
  ESEF-ANC-0008 Extension balance differs from anchor balance (warn)
  ESEF-ANC-0009 Anchor arc has wrong arcrole
  ESEF-ANC-0010 Anchor arc in wrong linkbase (must be definition)
  ESEF-ANC-0011 Extension abstract concept anchored (not required but not prohibited)
  ESEF-ANC-0012 Anchor chain exceeds recommended depth (warn)
  ESEF-ANC-0013 Extension dimension anchored (generally disallowed)
  ESEF-ANC-0014 Extension enumeration anchored to non-enum
  ESEF-ANC-0015 Multiple anchors to same concept (warn)
  ... (up to ~30 rules total)

  ALGORITHM:
    1. Load ESEF taxonomy + extension taxonomy.
    2. Build anchoring graph: nodes=all concepts, edges=wider-narrower arcs.
    3. For each extension concept C:
       a. BFS from C following wider arcs.
       b. Must reach at least one non-extension (IFRS) concept.
       c. Check data type / period type / balance compatibility at each step.

mandatory_tags.py (ESEF core tagging — IFRS-based):
  ESEF-MAN-0001 Missing mandatory LEI tag (entity identifier)
  ESEF-MAN-0002 Missing fiscal period tag
  ESEF-MAN-0003 Missing entity name / parent / address / country
  ESEF-MAN-0004 Missing auditor information
  ... (list driven by config/profiles/esef/mandatory_tags.yaml, ~40 tags)

block_tagging.py (ESEF 2022+):
  Financial statement notes must be block-tagged using IFRS text block concepts.

  ESEF-BLK-0001 Note without text block tag
  ESEF-BLK-0002 Overlapping text blocks (same content tagged twice)
  ESEF-BLK-0003 Text block with no narrower numeric tagging inside (warn)
  ESEF-BLK-0004 Text block shorter than minimum (< 50 chars likely mistagged)

lei.py:
  ESEF-LEI-0001 Entity identifier scheme not http://standards.iso.org/iso/17442
  ESEF-LEI-0002 LEI not 20-character ISO 17442 format
  ESEF-LEI-0003 LEI check digit invalid (ISO 7064 MOD 97-10)
  ESEF-LEI-0004 LEI not in GLEIF active list (requires --check-gleif)

language.py:
  ESEF-LNG-0001 Primary xml:lang not in ESMA languages list
  ESEF-LNG-0002 Mandatory facts missing in required languages
  ESEF-LNG-0003 Inconsistent language tags

html_profile.py (ESEF HTML 4.1 profile):
  ESEF-HTM-0001 <script> tag present
  ESEF-HTM-0002 <iframe> tag present
  ESEF-HTM-0003 <form> tag present
  ESEF-HTM-0004 external CSS link
  ESEF-HTM-0005 external JS link
  ESEF-HTM-0006 @import in inline CSS
  ESEF-HTM-0007 javascript: URL
  ESEF-HTM-0008 data: URI larger than 200 KB (image embedding limit)
  ESEF-HTM-0009 base64 image wrong MIME type

report_package.py (OIM report package format):
  ESEF-RPT-0001 rp.json missing
  ESEF-RPT-0002 rp.json schema invalid
  ESEF-RPT-0003 Referenced report file missing from package

YAML/PYTHON RATIO:
  YAML: mandatory tags list, LEI regex, permitted languages, HTML prohibitions
  Python: anchoring algorithm, block tagging overlap detection, signed package verification,
          multi-document merging

ERROR CODES: ESEF-PKG/SIG/ANC/MAN/BLK/LEI/LNG/HTM/RPT-NNNN, ~80 codes.
```

### 12C — FERC — `src/validator/regulator/ferc/`

**FERC is unusual: rules are authored in XULE, not hardcoded Python.**

```text
ferc_validator.py:
  Orchestrates by loading XULE rule sets for the detected form.
  Delegates to xule_runner.py.

xule_runner.py:
  Interface between FERC regulator and XULE engine (src/xule/).
  Loads compiled rule set for form type, runs via XULEEvaluator, converts outputs
  to ValidationMessage objects.

  RULE SETS (authored in config/profiles/ferc/xule_rules/):
    form1.xule     — Electric utility balance sheet/income statement
    form2.xule     — Natural gas
    form3.xule     — Oil pipeline
    form6.xule     — Oil pipeline (supplemental)
    form60.xule    — Service company annual
    form714.xule   — Electric quarterly
    common.xule    — Shared rule macros

  Each rule set has tens to hundreds of assertions.
  FERC publishes official .xule files; ours must be parity-compatible.

schedule_router.py:
  FERC forms contain many schedules. Routes facts to appropriate schedule validators.

  FERC-SCH-0001 Required schedule missing (per form)
  FERC-SCH-0002 Schedule structure violated (e.g., required axis missing)

XULE FEATURE REQUIREMENTS (for FERC parity):
  - Aspect-level queries with implicit filtering
  - Calendar arithmetic (period.end - period.start)
  - Namespace-prefix filters (${ferc:} prefix binding)
  - Custom functions for FERC-specific calculations
  - Output with severity, message template, table of facts
  - Rule groups (for bulk enable/disable via CLI)
  - Formula output to dynamically suggest fix values (SEC-style)

ERROR CODES: FERC-NNNN (mapped from XULE rule IDs).
```

### 12D — HMRC — `src/validator/regulator/hmrc/`

```text
hmrc_validator.py — orchestrator for UK CT600 / Companies House.

ct600.py (HMRC CT600 iXBRL):
  HMRC-CT-0001 Missing UTR (Unique Taxpayer Reference, 10 digits)
  HMRC-CT-0002 UTR check digit invalid
  HMRC-CT-0003 Accounts period start/end inconsistent with CT600 period
  HMRC-CT-0004 Required FRC taxonomy concepts missing
  HMRC-CT-0005 R&D claim section required but missing
  HMRC-CT-0006 Rate applied doesn't match rate for period (HMRC publishes yearly rates)
  HMRC-CT-0007 Losses carried forward inconsistent with prior returns (cross-doc if enabled)

companies_house.py:
  HMRC-CH-0001 Company Registration Number (CRN) format (8 digits, may start SC/NI/OC)
  HMRC-CH-0002 CRN not matching Companies House format for entity class
  HMRC-CH-0003 Accounts type (small/medium/micro/large) matching thresholds
  HMRC-CH-0004 Directors report required for non-micro

TAXONOMY:
  FRC IFRS taxonomy + DPL (Detailed Profit and Loss) taxonomy variants.

ERROR CODES: HMRC-CT/CH-NNNN, ~40 codes.
```

### 12E — CIPC — `src/validator/regulator/cipc/`

```text
cipc_validator.py — South Africa CIPC (Companies and Intellectual Property Commission).

entity_class.py:
  CIPC-CLS-0001 Entity classification (WCR/PI/CC) matches filing type
  CIPC-CLS-0002 Missing mandatory disclosure for classification
  CIPC-CLS-0003 Dormant company declaration inconsistent with activity facts

ifrs_sme.py:
  CIPC accepts IFRS-for-SMEs for small entities. Rules differ from full IFRS.
  CIPC-SME-0001 Full IFRS concept used but filer declared IFRS-for-SMEs
  CIPC-SME-0002 IFRS-for-SMEs mandatory tag missing

BEE (Broad-Based Black Economic Empowerment) reporting (optional extension).

ERROR CODES: CIPC-CLS/SME/BEE-NNNN, ~30 codes.
```

### 12F — MCA — `src/validator/regulator/mca/`

```text
mca_validator.py — India Ministry of Corporate Affairs (MCA21 filings).

cin.py (Corporate Identification Number, 21 chars):
  MCA-CIN-0001 CIN format invalid
  MCA-CIN-0002 CIN state code not ISO 3166-2:IN
  MCA-CIN-0003 CIN ROC code not on registered list
  MCA-CIN-0004 CIN check digits invalid

din.py (Director Identification Number, 8 digits):
  MCA-DIN-0001 DIN format
  MCA-DIN-0002 DIN check digit invalid
  MCA-DIN-0003 Director in filing but DIN not issued at filing date (requires MCA feed)

ind_as.py (Indian Accounting Standards = IFRS-adapted):
  MCA-IAS-0001 Ind-AS mandatory disclosure missing
  MCA-IAS-0002 Ind-AS concept used when Companies Act schedule III required
  MCA-IAS-0003 Schedule III taxonomy version mismatch with filing period

COST RECORDS AUDIT (CRA) specific filings handled by subset rules.

ERROR CODES: MCA-CIN/DIN/IAS-NNNN, ~40 codes.
```

---
## 13. XULE — `src/xule/`

**v2 reduced XULE to one-liners. Real XULE is a query language. FERC's rule sets
are full XULE programs. SEC DQC uses XULE too.**

```text
SPEC: XULE Specification (XBRL US DQC Committee), plus the reference implementation
      in the Arelle xulePackage. Our implementation targets FERC + DQC parity.

lexer.py:
  Tokenizer for XULE source. Handles:
    - Identifiers, numbers, strings
    - QNames (prefix:local)
    - Namespace declarations
    - Operators (= != < > >= <= + - * / . ;)
    - Keywords: rule, output, severity, message, from, where, if, then, else,
                for, in, none, true, false, taxonomy, function, assert, ...
    - Factset brackets: {...}
    - Navigation arrows: → (ASCII -> also accepted)
    - Comments: // line, /* block */
  LexerError on invalid tokens.

parser.py:
  Recursive-descent parser producing AST.
  Supports full XULE grammar: expressions, rules, factset queries, navigation,
  function definitions, macros, includes.
  ParseError with source_line/column.

ast_nodes.py:
  AST node dataclasses:
    Program, Namespace, Rule, Assertion, Output
    FactsetExpr, AspectBinding, Filter, Navigation
    BinaryOp, UnaryOp, FunctionCall, PropertyAccess
    ForComprehension, IfExpression, LetBinding
    Literal, QNameRef, Variable
    RuleSet (collection of rules with shared state)

compiler.py:
  AST → bytecode/IR.
  Performs:
    - Name resolution (rule names, variables, functions)
    - Type inference where possible
    - Dead code elimination
    - Constant folding
    - Filter pushdown hints to query planner

evaluator.py:
  Executes compiled rules.
  Input: XBRLInstance + compiled rule set.
  Output: List[XULEOutput]

  For each rule:
    1. Evaluate factset bindings (using query planner)
    2. Apply aspect filters
    3. For each binding tuple:
       - Evaluate where clause
       - If true, evaluate output/message
       - If assertion fails, emit ValidationMessage

  Timeout per rule: 300s. XULETimeoutError on exceed.

query_planner.py:
  Given a factset query, produces an execution plan.
  Similar to SQL query planner: push selective filters to fact_store index lookups
  before expensive computations.

  Example plan for `{@concept = us-gaap:Assets and @period = 2023-12-31}`:
    1. fact_store.get_by_concept("us-gaap:Assets")
    2. Filter by period
    3. Return

  Query tree rewriting:
    - Constant folding in filters
    - Filter commutation (most selective first)
    - Index use detection

factset.py:
  FactSet: a queryable set of fact bindings.
  Algebra: union, intersect, difference.
  Aspects: concept, entity, period, unit, dimension values.

aspect.py:
  Aspect binding model — how facts are matched across multiple factset variables.
  Implements XULE implicit filtering semantics (default: bind all aspects not
  explicitly varying).

navigation.py:
  Navigation over relationship networks: parent/child, ancestor/descendant, siblings.
  Syntax in XULE: `navigate parent-child relationships`, `navigate summation-item`.

calendar.py:
  Time-period arithmetic:
    - period.end - period.start → duration
    - period + "P1Y" → shifted period
    - Calendar math (year-end vs anniversary rules)

namespace_values.py:
  XULE can declare namespace prefixes:
    namespace us-gaap = http://fasb.org/us-gaap/2024

custom_functions.py:
  User-defined XULE functions.
  Registry: name → compiled function.

builtins.py:
  Built-in XULE functions:
    list(), set(), sum(), avg(), count(), min(), max()
    string-concat(), substring(), contains()
    abs(), round(), floor(), ceiling()
    taxonomy.concepts-where(), taxonomy.network()
    duration-days(), period-between()
    qname(), local-name(), namespace-uri()
    (50+ builtins)

output.py:
  XULEOutput structure:
    rule_id: str
    rule_focus: QName                  # reference concept
    severity: Severity
    message: str                        # after template substitution
    facts_involved: List[FactReference]
    metadata: Dict[str, Any]

rule_set_loader.py:
  Loads .xule files from filesystem or package.
  Handles includes/imports.
  Compiles and caches on disk (XULE compile is expensive for large rule sets).

xpath_interop.py:
  XULE can invoke XPath expressions (and vice versa in formula).
  Bridge via elementpath integration.

ERROR CODES:
  XULE-LEX-NNNN     lexer errors
  XULE-PRS-NNNN     parser errors
  XULE-CMP-NNNN     compile errors
  XULE-RUN-NNNN     runtime errors
  XULE-TIM-NNNN     timeouts
  Rule emissions use regulator-specific codes (FERC-* for FERC XULE rules).

PERFORMANCE:
  Target: FERC Form 1 (~5000 facts, ~300 XULE rules) validates in < 60s.
  Benchmark tracked in tests/benchmarks/bench_xule.py.
```

---

## 14. AI LAYER — `src/ai/`

**v1.0 ships a deterministic-suggestion tier only. LLM-backed suggestions ship in v1.2.**

```text
template_suggestions.py (DETERMINISTIC, always available):
  For every registered error code, a fix template:
    "XBRL21-0010 (missing decimals): Add decimals=\"{suggested}\" to element at line {line}"
    "DIM-0001 (member not in domain): Check that '{member}' is reachable via
     domain-member arcs from '{domain}' in role '{role}'"
    "CALC-0002 (summation inconsistency): parent {parent_value} ≠ sum of children
     {children_sum} by {diff}; expected tolerance {tol}"
  Templates live in config/error_codes.yaml under fix_suggestion field.

  Every ValidationMessage passes through template_suggestions before emission.

llm_suggestions.py (OPTIONAL, feature-flagged):
  Only activated with --enable-ai AND API key present.

  Providers:
    ANTHROPIC: anthropic.Client → claude-sonnet-4
    OPENAI:    openai.Client → gpt-4o (or newer)
  Fallback if provider unavailable → template_suggestions.

  Context sent to LLM:
    - Error code + template
    - Source snippet (10 lines around)
    - Concept name, context, unit
    - Related errors (deduplicated, sorted by severity)
  Cache by (error_code, concept, hash(context)) → suggestion.

  NEVER sent: full instance, PII, internal concept names beyond what's visible in error.

  Rate limiting: token bucket per API key, 20 req/min default.
  Deterministic flag --no-ai disables entirely.

cross_doc.py (v1.2 scope):
  Cross-document checks. E.g., Q1 + Q2 + Q3 + Q4 ≠ FY for revenue.
  Requires multiple instances passed together.

  Rules:
    CROSS-0001 Quarterly aggregate ≠ annual
    CROSS-0002 Share count jumps across consecutive periods
    CROSS-0003 Concept changes from numeric to non-numeric across periods (tagging error)
    CROSS-0004 Extension concept used period N but not N+1 (deprecated?)
    CROSS-0005 Significant fact absent in current period but present in prior

  (Cross-doc is AI-adjacent — heuristic rules, not true ML.)

business_rules.py (v1.2 scope):
  Heuristic business checks beyond XBRL spec:
    BIZ-0001 Liquidity ratio < 1 (warn, informational)
    BIZ-0002 Debt/equity > 10 (warn)
    BIZ-0003 Revenue decline > 50% YoY without disclosure
    BIZ-0004 Balance sheet doesn't balance (Assets ≠ Liabilities + Equity) beyond tolerance

  These are information-only (severity=INFO). They do NOT fail a filing.

tagging_analyzer.py (v1.2 scope):
  Uses ConceptVersionMap + LLM to suggest better tagging.
    TAG-0001 Extension concept could be replaced by standard concept X (score)
    TAG-0002 Deprecated concept used; recommend successor
    TAG-0003 Incorrectly tagged as block when numeric facts present inside
    TAG-0004 Tagged text block with >50% HTML markup (escape issue)

confidence.py:
  Every AI suggestion carries a confidence score 0.0–1.0:
    > 0.9: deterministic template match
    0.6–0.9: LLM response with high model confidence
    0.3–0.6: LLM response with cached-before distance
    < 0.3: suppressed unless --show-low-confidence

fix_suggester.py (orchestrator):
  For each ValidationMessage:
    1. Try template_suggestions (deterministic, instant).
    2. If enable_ai and template was generic, try llm_suggestions.
    3. Attach best suggestion to message.fix_suggestion, source tag, confidence.

RULE 11 COMPLIANCE:
  AI suggestions are the ONLY non-deterministic part of the pipeline.
  --no-ai disables entirely.
  AI suggestions are tagged so downstream consumers can distinguish.
```

---
## 15. REPORT GENERATORS — `src/report/`

```text
All generators accept PipelineResult, return string/bytes, and never block on I/O
for the primary serialization (writing to disk is a separate step).

json_report.py:
  Canonical JSON output. Stable schema versioned at v1.
  Top-level:
    {
      "schema": "xbrl-validator-result-v1",
      "summary": { counts by severity, elapsed_ms, files, strategy },
      "messages": [ ValidationMessage serialized ],
      "taxonomy_info": { versions, entry_points },
      "pipeline": { stages, timings, memory_peak }
    }
  Streaming mode: can write to file progressively as messages accumulate (large runs).

sarif_report.py:
  SARIF 2.1.0 format. Compatible with GitHub Code Scanning, Azure DevOps, etc.
  Each ValidationMessage → sarif "result":
    level: error/warning/note
    message.text: from template
    locations[0].physicalLocation.artifactLocation.uri = source_file
    locations[0].physicalLocation.region = { startLine, startColumn }
    ruleId: code
  sarif "rules": per distinct code, with full metadata.
  Fix suggestions → sarif "fixes".

html_report.py (jinja2 templates in report/templates/):
  Human-friendly HTML report:
    Summary card: counts, filename, taxonomy, duration
    Errors table: sortable, filterable by code/severity
    Error detail: source snippet, fix suggestion, spec reference
    Table rendering: if table linkbase was evaluated, embed rendered tables
    Charts: pie chart of severities, bar chart of codes (Chart.js, embedded)

csv_report.py:
  Flat CSV per message. Columns: code, severity, file, line, column, message,
  concept, context, unit, fix_suggestion, rule_source.
  Streaming output for very large error lists.

junit_report.py:
  JUnit XML format for CI systems.
  One test suite per spec category + one per regulator.
  Errors = failures; warnings = skipped (configurable).

arelle_compat_report.py:
  Arelle-compatible log format.
  Each message → Arelle-style line:
    [code] message - sourceFile line lineNumber, column columnNumber
  For customers migrating from Arelle tooling.
```

---

## 16. API — `src/api/`

```text
FastAPI application. Primarily async.

routes.py:
  POST /v1/validate
    body: multipart upload OR URL reference OR taxonomy package zip
    query: regulator, toggles
    returns: job_id (Celery task); 202 Accepted
    Sync mode: ?sync=true returns full PipelineResult (for small files only)

  GET  /v1/results/{job_id}
    returns: PipelineResult (latest, may be partial during streaming)
  GET  /v1/results/{job_id}/report?format=html|json|sarif|csv|junit|arelle
    returns: formatted report bytes

  WebSocket /v1/ws/{job_id}
    streams pipeline stage events + progress

  POST /v1/taxonomy/preload
    body: package zip or URL list
    preloads into cache for faster subsequent runs

  GET  /v1/health
  GET  /v1/metrics            (Prometheus)
  GET  /v1/conformance/status (pass rates per suite)
  GET  /v1/profiles           (available regulator profiles)
  GET  /v1/codes              (error code catalog)

middleware.py:
  Request ID injection.
  Structured logging middleware.
  CORS.
  Authentication (bearer token or API key).
  Rate limiting (per-API-key, Redis-backed).

auth.py:
  API key management. Rotation-friendly. Scopes: validate / admin / taxonomy.

rate_limit.py:
  Token bucket, Redis-backed.
  Default: 10 validations/min per key, 100/hr, 1000/day.
  Large-file validations (>100 MB) count as 10 units.

websocket.py:
  Event types: stage_started, stage_completed, progress, message_emitted, done, error.
  Backpressure: server buffers max 100 events, drops oldest on overflow.

worker.py (Celery):
  Task: validate_task(job_id, config, input_ref)
  Runs the full pipeline, stores result in Redis (TTL 24h) and optionally Postgres.
  Updates WebSocket channel with progress.

schemas.py:
  Pydantic models for request/response bodies.

health.py:
  /health: liveness (process alive)
  /health/ready: readiness (Redis + Postgres reachable, taxonomy cache intact)

metrics.py:
  Prometheus counters/histograms:
    xbrl_validations_total{regulator, result}
    xbrl_validation_duration_seconds{regulator}
    xbrl_facts_validated_total
    xbrl_memory_peak_bytes
    xbrl_spills_total
    xbrl_taxonomy_cache_hits / misses
```

---

## 17. CLI — `src/cli/`

```text
main.py — `xbrl-validate` entry point (typer):
  Commands:
    validate FILE [OPTIONS]
      --regulator [efm|esef|ferc|hmrc|cipc|mca|auto]
      --taxonomy-package PATH
      --taxonomy-cache-dir PATH
      --output FORMAT [json|sarif|html|csv|junit|arelle]
      --output-file PATH
      --memory-budget GIGABYTES
      --force-streaming
      --force-disk-spill
      --offline
      --no-ai
      --enable-xule / --no-xule
      --max-errors N
      --fail-fast               # stop on first error
      --diag                    # diagnostic mode (verbose logs)
      --parallel N              # worker count
    watch FILE                  # re-validate on change

  Progress bar (rich.progress): streaming mode shows bytes-read, facts-scanned,
  errors-so-far. Stage transitions update spinner.

taxonomy.py — `xbrl-taxonomy`:
  preload URL                   # fetch and cache
  preload-package FILE          # cache taxonomy package
  inspect FILE                  # dump taxonomy structure
  list-cache                    # show cached taxonomies
  clear-cache                   # clear cache
  verify-cache                  # check cache integrity

conform.py — `xbrl-conform`:
  run SUITE [--spec xbrl21|dimensions|formula|calc11|inline|table|enum|oim|pkg]
  report                        # show latest pass rates
  diff-arelle                   # compare results with Arelle (if arelle installed)
  history                       # historical pass rates

progress.py:
  rich.progress.Progress wrapper with XBRL-specific columns.

formatters.py:
  Terminal color output. Severity colors. Syntax highlighting for XML snippets.

diagnostics.py:
  --diag mode: emits debug JSON with:
    - Every taxonomy file fetched (size, time)
    - Every SQL query issued (for disk-spilled fact store)
    - Every memory checkpoint
    - XULE rule execution times
    - Formula variable set evaluation times
  Used for perf debugging on huge filings.
```

---

## 18. PLUGIN SYSTEM — `src/plugin/`

```text
base.py:
  Abstract base: Plugin, with lifecycle methods.

loader.py:
  Loads plugins from:
    - Entry points (pyproject.toml [project.entry-points."xbrl_validator.plugins"])
    - Explicit --plugin-path directories
    - Built-in regulator plugins (efm, esef, ferc, hmrc, cipc, mca)
  Enforces Rule 5 (import-linter) and plugin isolation.

profile_loader.py:
  Loads regulator profiles from config/profiles/{id}/profile.yaml + referenced YAMLs.
  Validates YAML structure against schema (jsonschema).
  Compiles YAML rules into Python rule objects via rule_compiler.

rule_compiler.py:
  Translates YAML rule declarations → Python callables:
    mandatory_element:
      concept: dei:DocumentType
      form_types: [10-K, 10-Q]
      severity: error
    → compiled into a function that checks presence and emits message.

  Handles all rule types declared in yaml_rules/.

yaml_rules/mandatory_element.py:
  Matches concept (or QName pattern) in facts, emits error if absent.

yaml_rules/value_constraint.py:
  Constrains fact values:
    - regex pattern
    - enumeration
    - numeric range (Decimal!)
    - date range

yaml_rules/cross_concept.py:
  Compare two facts: "concept A value × multiplier = concept B value (tolerance T)".

yaml_rules/naming_convention.py:
  Extension concept name patterns.

yaml_rules/structural.py:
  Presentation/definition tree structural rules.

yaml_rules/negation.py:
  NEGVAL-style negation catalog matching.

rule_types.py:
  YAML rule type registry. Plugins can add new rule types.
```

---

## 19. SECURITY — `src/security/`

```text
xxe_guard.py:
  Wraps lxml.etree.XMLParser with XXE-safe settings.
  Tests: XXE_INJECTION attacks from tests/fixtures/security/.

zip_guard.py:
  Zip bomb protection:
    - Track uncompressed bytes as they're read
    - Abort at max_zip_uncompressed_bytes
    - Check compression ratio per entry (> 100:1 = suspicious)
    - Max file count per zip
    - Reject absolute paths, ".." segments
    - Reject symlinks

url_allowlist.py:
  Check URL against allow-list before any outbound request.
  Support exact domain, subdomain wildcards (*.sec.gov), IP blocks.
  Reject private IPs by default (10/8, 172.16/12, 192.168/16, fc00::/7).

entity_limits.py:
  Entity expansion counter for lxml.
  Per-document counter reset on each parse call.
  Raises BillionLaughsError when limit hit.

SECURITY TEST SUITE (tests/security/):
  - XXE via external entity → XXEError
  - XXE via parameter entity → XXEError
  - Billion laughs nested entities → BillionLaughsError
  - Quadratic blowup → BillionLaughsError (same guard)
  - Zip bomb (4.5 GB uncompressed in 46 KB zip) → ZipBombError
  - Zip with absolute path → PathTraversalError
  - Zip with ".." entries → PathTraversalError
  - SSRF via taxonomy URL → SSRFError
  - SSRF via inline XBRL href → SSRFError
  - Taxonomy fetch to 127.0.0.1 → SSRFError (private IP block)
```

---
## 20. CONFORMANCE SUITE HARNESS — `conformance/`

**This is the primary quality gate per Rule 8. Much more prominent than in v2.**

```text
XBRL International publishes official conformance suites for each spec. Our validator
MUST pass these. Target pass rates at each release milestone are tracked in
conformance/reports/pass_rate.md.

SUITES TO DOWNLOAD (scripts/download_conformance.sh):
  suites/xbrl-2.1/             XBRL 2.1 conformance suite (~3000 test cases)
  suites/dimensions-1.0/       XDT 1.0 suite (~200 tests)
  suites/formula-1.0/          Formula 1.0 suite (~1000 tests)
  suites/calculation-1.1/      Calc 1.1 suite (~150 tests, 2024)
  suites/inline-1.1/           iXBRL 1.1 suite (~300 tests)
  suites/table-1.0/            Table Linkbase suite (~400 tests)
  suites/enumerations-2.0/     Extensible Enumerations 2.0 suite
  suites/taxonomy-packages-1.0/ Tax Package 1.0 suite
  suites/oim-1.0/              OIM suite (~200 tests)
  suites/generic-links-1.0/    Generic Links suite

runner.py:
  CLASS: ConformanceRunner
    run_suite(self, suite_name: str, subset: Optional[str] = None) -> SuiteResult
    run_all(self) -> Dict[str, SuiteResult]

  ALGORITHM per test case:
    1. Load suite index XML (testcases.xml)
    2. For each variation in test:
       a. Locate inputs (schemas, instances, linkbases)
       b. Locate expected result (valid / invalid with error codes)
       c. Run our pipeline on inputs
       d. Compare our errors to expected:
          - valid expected + no errors = PASS
          - invalid expected + our error (any code) = PASS (basic)
          - invalid expected + our error (matching code prefix) = STRICT PASS
          - other combinations = FAIL
       e. Record: pass/fail, our errors, expected, elapsed
    3. Aggregate: pass count, fail count, STRICT pass rate.

suite_config.yaml:
  Per-suite configuration:
    - URL for download
    - Version pinned (SHA256 of test case index)
    - Known-failing tests (with justification; reviewed quarterly)
    - Timeout per test

result_comparator.py:
  Error code matching logic.
  Our codes are XBRL21-NNNN; suite expects xbrl.core.NNNN or similar.
  Maintains a mapping: suite_expected_code → our_code.
  Mapping lives in config/error_codes.yaml `conformance_mapping` field.

expected_results.py:
  Parser for XBRL International testcase variation format.
  Handles: error-code specifications, valid/invalid verdicts, assertion expectations.

CI INTEGRATION:
  On every PR: run quick subset (known-pass tests) as smoke test.
  Nightly: run full suite. Fail CI if pass rate regresses by > 1%.
  Release gate: pass rate thresholds per milestone (see roadmap).

  Results reported to conformance/results.json, historical runs in history/.
  Reports rendered to conformance/reports/pass_rate.md (auto-updated).

ARELLE DIFF TRACKING (conformance/reports/diff_from_arelle.md):
  For each test our implementation handles differently from Arelle:
    - Test case ID
    - Our verdict vs Arelle verdict
    - Reason (our bug / Arelle bug / spec ambiguity)
    - Spec clause reference
    - Resolution target (next release / permanent difference / spec clarification request)
  This file is mandatory per Rule 14. Customer migrations depend on it.

TARGET PASS RATES by milestone (see roadmap §23):
  v1.0 (EFM focus):  XBRL 2.1 > 98%, Dimensions > 95%, Calc 1.0 > 99%,
                     Inline 1.1 > 95%, Enumerations > 95%, OIM > 90%
  v1.1 (ESEF added): all above + Calc 1.1 > 95%, Formula > 80%
  v1.2 (Formula full): Formula > 95%, Table > 85%
  v1.3 (full parity): all suites > 95%, most > 99%
```

---

## 21. TESTING

Test pyramid: unit → integration → large-file → security → conformance → e2e → property → benchmarks.

### 21A — Unit Tests (`tests/unit/`)

Mirror `src/` structure exactly. Every module has a test file with ≥ 3 tests per
public function (valid, invalid, edge case).

For validators: every error code must have at least one test that triggers it, and
one test that does NOT trigger it (false-positive guard).

CI: `pytest tests/unit --cov=src --cov-fail-under=85`
Target coverage: 85% statement, 75% branch. Security module ≥ 95%.

### 21B — Integration Tests (`tests/integration/`)

Full pipeline tests with moderate-size fixtures:
  - test_pipeline_efm: 10-K fixture, expect specific EFM errors
  - test_pipeline_esef: ESEF annual report fixture, expect anchoring check results
  - test_pipeline_ferc: Form 1 fixture, XULE rules run
  - test_pipeline_hmrc: CT600 fixture
  - test_pipeline_cipc, test_pipeline_mca
  - test_pipeline_inline: iXBRL fixture with transforms, continuations
  - test_pipeline_oim_json / oim_csv: OIM formats
  - test_pipeline_multidoc: ESEF multi-document filing, cross-doc continuation
  - test_round_trip_oim: XML → JSON → CSV → XML equivalence
  - test_api_endpoints: FastAPI test client
  - test_cli: typer CliRunner
  - test_taxonomy_preload: preload + offline validation

### 21C — Large-File Tests (`tests/large_file/`)

**This is where v2's strong parts really earn their place.**

```text
conftest.py:
  Fixtures for generated large files (cached between runs, regenerated on schema change).
  Slow test marker: only runs in CI nightly or with --run-slow.

test_streaming_xml_200mb.py:
  Generate 200MB XBRL with ~500K facts.
  Parse with streaming, check all facts indexed.
  Assert: memory peak < 1 GB, parse time < 120s.

test_streaming_xml_1gb.py:
  1 GB XBRL, ~2.5M facts.
  Assert: disk spill occurs, memory < 2 GB, parse time < 10 min.

test_streaming_xml_5gb.py:
  5 GB XBRL, ~12M facts.
  Assert: disk spill, memory < 4 GB, parse time < 60 min.

test_streaming_ixbrl_200mb.py:
  200MB iXBRL with ~200K facts + continuations.
  Assert: parse completes, continuations resolved.

test_streaming_json_500mb.py:
  500MB XBRL-JSON with ijson streaming.
  Rule 16 check: no float roundtrip loss on random sample of 1000 facts.

test_streaming_csv_1gb.py:
  1 GB XBRL-CSV with polars streaming.
  Rule 16 check: Decimal precision preserved.

test_memory_budget_enforcement.py:
  Set budget to 500 MB, feed generator that would exceed 1 GB.
  Assert: spill triggers at 80% threshold, no OOM.

test_disk_spill_correctness.py:
  Identical queries against InMemoryFactIndex and DiskSpilledFactIndex.
  Assert: results bit-identical for get_by_concept, get_by_context,
  get_duplicate_groups, iter_all, etc.

test_disk_spill_performance.py:
  Insert 10M synthetic facts; measure: insert rate, point query, range query.
  Assert: insert > 100K/sec, point query < 1ms, range scan > 50K/sec.

test_mmap_random_access.py:
  1 GB file, 10K random value reads.
  Assert: all values correctly extracted. (SSD-only; skipped on HDD.)

test_chunked_hdd_read.py:
  Simulate HDD (force ChunkedReader).
  10K random value reads from 1 GB file.
  Assert: completes in < 60s (vs. 30 min for naive seeking).

test_million_facts.py:
  1M-fact file. Full pipeline EFM validation.
  Assert: < 5 min, full memory budget compliance.

test_10m_facts.py:
  10M-fact file. Full pipeline (spec validators, no regulator).
  Assert: < 30 min, disk spill engaged.

test_50m_facts.py:
  50M-fact file (synthetic). Parse + index.
  Assert: disk spill, SQLite DB < 5 GB, completes.

test_threshold_boundaries.py:
  Test exactly at 99MB / 101MB / 999MB / 1001MB thresholds.
  Assert: strategy switches at threshold boundaries, both strategies produce
  equivalent validation results.

generators/:
  Synthetic XBRL/iXBRL/JSON/CSV generators.
  Parameterized by fact count, context count, unit count, dimensional depth.
  Deterministic (seeded) so tests are reproducible.
```

### 21D — Security Tests (`tests/security/`)

```text
test_xxe_attacks.py:
  - External entity injection (file:///)
  - External entity injection (http://)
  - Parameter entity injection
  - Nested entities
  Each must raise XXEError (subclass of SecurityError).

test_billion_laughs.py:
  Nested entity expansion ("ha" × 2^n pattern).
  Must raise BillionLaughsError before memory exhaustion.

test_quadratic_blowup.py:
  Same entity referenced many times.
  Must raise BillionLaughsError.

test_zip_bombs.py:
  4.5 GB → 46 KB classic zip bomb.
  Must raise ZipBombError before extracting to disk.

test_path_traversal.py:
  Zip with "../../etc/passwd" entries → PathTraversalError.
  Zip with absolute paths → PathTraversalError.

test_ssrf.py:
  - taxonomy URL to 127.0.0.1 → SSRFError
  - taxonomy URL to 169.254.169.254 (AWS metadata) → SSRFError
  - taxonomy URL to private IP ranges → SSRFError
  - taxonomy URL after 302 redirect to private IP → SSRFError

All security tests use fixtures in tests/fixtures/security/.
Attack payloads are sandbox-safe (no real exfiltration vectors).
```

### 21E — Conformance Tests (`tests/conformance/`)

Per §20 above. These are integration tests that run the official XII suites.

Marker: @pytest.mark.conformance (separate from regular test run; slower).

CI: nightly run, results updated in conformance/results.json.

### 21F — End-to-End Tests (`tests/e2e/`)

Real-world filings from each regulator:
  SEC 10-K / 10-Q / 8-K / S-1 / 20-F (sampled from SEC EDGAR)
  ESEF annual reports (sampled from ESMA)
  FERC Form 1 / Form 714 (sampled from FERC eLibrary)
  HMRC CT600 (synthetic, HMRC doesn't publish real ones)
  CIPC AFS sample
  MCA AOC-4 sample

Corpus downloaded via scripts/download_corpus.sh (gitignored).
Tests assert: completes without crash, no SecurityError, error count within
historical range (regression detection).

### 21G — Property Tests (`tests/property/`)

Hypothesis-based:
  test_decimal_arithmetic: xs:decimal round-trip, scale, round operations preserve invariants
  test_fact_equivalence: fact equivalence is reflexive, symmetric, transitive
  test_oim_round_trip: XML → OIM → XML preserves information (property-tested across
                       randomly generated small instances)
  test_context_equality: dimensional equality satisfies set semantics

### 21H — Benchmarks (`tests/benchmarks/`)

pytest-benchmark. Track regressions.

```text
bench_parsing.py:
  - parse 10 MB XBRL (DOM)
  - parse 100 MB XBRL (streaming)
  - parse 1 GB XBRL (streaming + spill)

bench_taxonomy_load.py:
  - cold us-gaap-2024 load
  - warm us-gaap-2024 load (L1 cache)
  - L2 (disk) cache load

bench_calculation.py:
  - small (1K facts), medium (10K), large (100K)

bench_formula.py:
  - small variable set
  - large variable set (1000+ filter combinations)

bench_xule.py:
  - FERC Form 1 full rule set

bench_pipeline.py:
  - full EFM 10-K pipeline
  - full ESEF pipeline
```

Baselines stored in benchmarks/baseline.json. CI fails if regression > 10%.

---
## 22. ERROR CODE REGISTRY — `config/error_codes.yaml`

**This is the system's ground truth. Every emitted message has an entry here.
Every entry has: template, severity, spec ref, fix, failing test fixture, Arelle
compat code (if applicable), and conformance mapping.**

Full registry is ~800 entries. Prefix index (count in parens):

```text
PARSE-NNNN    (20)  — Parser-level errors (XML, iXBRL, JSON, CSV, package)
DTS-NNNN      (15)  — DTS discovery/resolution
PKG-NNNN      (20)  — Taxonomy/report/filing package
TPE-NNNN      (15)  — Taxonomy Package Expectations (TPE) conformance
CAT-NNNN       (8)  — XML catalog
REF-NNNN      (10)  — SchemaRef/linkbaseRef/roleRef/arcroleRef XLink
DT-NNNN        (5)  — Date/time parsing
MODEL-NNNN    (15)  — Model building
MERGE-NNNN    (10)  — Multi-document merge
XBRL21-NNNN   (40)  — XBRL 2.1 spec
DIM-NNNN      (30)  — Dimensions XDT 1.0
CALC-NNNN     (10)  — Calculation 1.0 (classic)
CALC11-NNNN   (10)  — Calculation 1.1 (2023)
IXBRL-NNNN    (45)  — iXBRL 1.1
IXT-NNNN      (10)  — iXBRL transforms
FORMULA-NNNN  (20)  — Formula 1.0
TBL-NNNN      (15)  — Table Linkbase 1.0
LBL-NNNN      (10)  — Label linkbase
PRES-NNNN     (10)  — Presentation linkbase
DEF-NNNN      (10)  — Definition linkbase
ENUM-NNNN     (10)  — Extensible Enumerations 2.0
OIM-JSON-NNNN (15)  — XBRL-JSON
OIM-CSV-NNNN  (15)  — XBRL-CSV
OIM-INFO-NNNN (10)  — OIM report info
VER-NNNN      (10)  — Versioning report
GEN-NNNN      (10)  — Generic links
UTR-NNNN      (10)  — Units Registry
LRR-NNNN       (5)  — Link Role Registry
EFM-NNN-NNNN (150)  — SEC EFM rules (by category: DEI/CIK/NEG/NAM/PER/SHR/ROL/PRES/LBL/HID/STR/IX/FORM)
ESEF-NNN-NNNN (80)  — ESMA ESEF rules (PKG/SIG/ANC/MAN/BLK/LEI/LNG/HTM/RPT)
FERC-NNNN     (varies, mapped from XULE rule IDs)
HMRC-NNNN     (40)  — UK HMRC CT600 + Companies House
CIPC-NNNN     (30)  — South Africa CIPC
MCA-NNNN      (40)  — India MCA21
XULE-NNNN     (25)  — XULE engine errors (lexer/parser/compiler/runtime/timeout)
TAG-NNNN      (10)  — Tagging analysis (AI, v1.2)
BIZ-NNNN      (10)  — Business rules (AI, v1.2)
CROSS-NNNN    (10)  — Cross-document (v1.2)
SEC-NNNN      (5)   — System/security meta-codes (XXE, zip-bomb, SSRF surfaced as messages)
────────────
TOTAL         ~820
```

### 22A — Entry schema

```yaml
# Schema for each entry in config/error_codes.yaml
XBRL21-0010:
  severity: error                           # error | warning | inconsistency | info
  category: xbrl21.fact
  template: "Numeric fact '{concept}' in context '{context}' missing both @decimals and @precision."
  spec_reference: "XBRL 2.1 §4.6.3"
  arelle_equivalent: "xbrl.4.6.3"          # per Rule 14
  conformance_mapping:                      # per Rule 8, §20 result_comparator
    - "xbrl.core.4.6.3"
    - "xbrl:missingDecimalsAndPrecision"
  fix_suggestion: |
    Add either @decimals or @precision attribute to the fact element.
    @decimals='-3' indicates rounding to thousands.
    @decimals='0' indicates rounding to integer.
    Use @decimals='INF' for exact values.
  fix_template: 'Add decimals="{suggested}" to {concept} at line {line}'
  fields_required: [concept, context, line]
  test_fixture: "tests/fixtures/invalid/xbrl21/missing_decimals.xml"
  large_file_note: |
    Detected during streaming parse. Fact reference carries line/column.
    No value load needed to detect — attribute-presence check.
```

### 22B — Representative sample (10 entries across prefixes; full file in repo)

```yaml
PARSE-0001:
  severity: error
  category: parser.xml
  template: "XML parsing failed at line {line}, column {column}: {reason}"
  spec_reference: "XML 1.0 well-formedness"
  arelle_equivalent: "xmlSchema:parserError"
  fix_suggestion: "Open the file in an XML editor to fix the well-formedness error."
  fields_required: [line, column, reason]
  test_fixture: "tests/fixtures/invalid/parser/malformed.xml"

DIM-0001:
  severity: error
  category: dimensions.hypercube
  template: "Context '{context}' contains dimension '{dimension}' with member '{member}' which is not in the domain of that dimension (role: {role})."
  spec_reference: "XDT 1.0 §2.4.1"
  arelle_equivalent: "xbrldie:PrimaryItemDimensionallyInvalidError"
  conformance_mapping: [xbrldie:PrimaryItemDimensionallyInvalidError]
  fix_suggestion: |
    Verify that '{member}' is in the domain of '{dimension}':
      - Check dimension-domain arc from '{dimension}' to domain-member subtree
      - Check domain-member arcs from the domain to '{member}'
      - Check that any domain-member arc to '{member}' does NOT have usable=false
      - Check targetRole chains if the arcs cross roles
  fields_required: [context, dimension, member, role]
  test_fixture: "tests/fixtures/invalid/dimensions/member_not_in_domain.xml"
  large_file_note: "Dimension checks use pre-computed allowed-member sets per hypercube."

CALC-0002:
  severity: inconsistency
  category: calculation.summation
  template: "Summation inconsistency in role '{role}': parent {parent_concept}={parent_value} ≠ sum of children {children_sum} (diff={diff}, tolerance={tolerance})"
  spec_reference: "XBRL 2.1 §5.2.5.2"
  arelle_equivalent: "xbrl.5.2.5.2:calcInconsistency"
  fix_suggestion: |
    Verify child-concept values and weights. The inconsistency is {diff},
    exceeding tolerance {tolerance} (derived from @decimals of participants).
    Check:
      - All contributing children present in same context/unit
      - @decimals on each fact is appropriate
      - Weights in summation-item arcs are correct (+1 or -1 typically)
      - Rounding: review whether source system pre-rounded values
  fields_required: [role, parent_concept, parent_value, children_sum, diff, tolerance]
  test_fixture: "tests/fixtures/invalid/calculation/sum_mismatch.xml"
  large_file_note: |
    Requires fact value loading (not just metadata). Uses value_reader
    (MMapReader on SSD, ChunkedReader on HDD) with batched offset reads.

CALC11-0003:
  severity: inconsistency
  category: calculation.calc11.duplicate
  template: "Calc 1.1 duplicate facts for concept '{concept}' in context '{context}' have values '{v1}' and '{v2}' differing beyond rounded equivalence at decimals={decimals}."
  spec_reference: "Calculation 1.1 (2023) §4.2"
  arelle_equivalent: "xbrlcale:inconsistentDuplicateFactSetError"
  fix_suggestion: |
    Multiple facts with the same (concept, context, unit) must be consistent
    when rounded to their minimum @decimals. Check both fact values and
    their @decimals attributes.
  fields_required: [concept, context, v1, v2, decimals]
  test_fixture: "tests/fixtures/invalid/calc11/inconsistent_duplicates.xml"

IXBRL-0003:
  severity: error
  category: inline.continuation
  template: "Circular continuation chain starting at '{start_id}'. Continuation IDs visited: {chain}"
  spec_reference: "iXBRL 1.1 §4.1.7"
  arelle_equivalent: "ixbrl:continuationCycle"
  fix_suggestion: |
    Remove the cycle in ix:continuation chain. Each continuation can only
    be referenced once by @continuedAt.
  fields_required: [start_id, chain]
  test_fixture: "tests/fixtures/invalid/ixbrl/circular_continuation.xhtml"

ESEF-ANC-0001:
  severity: error
  category: regulator.esef.anchoring
  template: "Extension concept '{concept}' has no wider-narrower anchoring arc to the IFRS taxonomy."
  spec_reference: "ESEF Reporting Manual §3.4.3"
  arelle_equivalent: "ESEF.3.4.3.extensionConceptNotAnchored"
  fix_suggestion: |
    Every extension concept must be anchored (via the esef:wider-narrower arcrole
    in a definition linkbase) to one or more IFRS taxonomy concepts. Add a
    definition linkbase arc from your extension concept to its closest IFRS
    equivalent(s).
  fields_required: [concept]
  test_fixture: "tests/fixtures/invalid/esef/unanchored_extension.xml"
  large_file_note: |
    Checked on complete extension concept set after DTS resolution. No
    per-fact iteration. O(extension_concepts × anchor_arc_bfs_depth).

EFM-NEG-0001:
  severity: error
  category: regulator.efm.negation
  template: "Concept '{concept}' is in the SEC NEGVAL catalog with fact value {value}, but no negated-label arc applies for the context."
  spec_reference: "EFM §6.11.1"
  arelle_equivalent: "EFM.6.11.1.negatedLabel"
  fix_suggestion: |
    Either:
      (a) Verify the fact value sign is correct (maybe the sign should be inverted),
      (b) Add a negated-label arc for this concept for the filing's locale, OR
      (c) Confirm this concept should not actually be in NEGVAL — submit feedback to SEC.
  fields_required: [concept, value]
  test_fixture: "tests/fixtures/invalid/efm/negval_missing_label.xml"

FORMULA-0001:
  severity: error
  category: formula.assertion.value
  template: "Value assertion '{assertion_id}' failed: {test_expression} = false for binding {binding}"
  spec_reference: "Formula 1.0 §4.3"
  arelle_equivalent: "formula:assertionFailed"
  fix_suggestion: |
    Examine the test XPath expression and the fact binding. The assertion
    fired for this combination of variables; either the data is inconsistent
    or the assertion predicate needs adjustment.
  fields_required: [assertion_id, test_expression, binding]
  test_fixture: "tests/fixtures/invalid/formula/value_assertion_fails.xml"

XULE-RUN-0001:
  severity: error
  category: xule.runtime
  template: "XULE rule '{rule}' at {file}:{line} failed: {reason}"
  spec_reference: "XULE Specification"
  arelle_equivalent: null
  fix_suggestion: "Review the XULE rule. Runtime errors indicate the rule's assumptions didn't hold."
  fields_required: [rule, file, line, reason]
  test_fixture: "tests/fixtures/invalid/xule/runtime_error.xule"

SEC-0001:
  severity: error
  category: security.xxe
  template: "XML External Entity (XXE) attack detected while parsing '{file}': {detail}"
  spec_reference: "OWASP XXE"
  arelle_equivalent: null
  fix_suggestion: "The input document contains or references external entities, which are not permitted. Contact the document author."
  fields_required: [file, detail]
  test_fixture: "tests/fixtures/security/xxe_external.xml"
  security_note: |
    This error ABORTS the pipeline. Severity is always error. Cannot be downgraded
    via --treat-warnings-as-errors=false (this direction doesn't apply — security
    errors are non-negotiable). ErrorCode registry flag `security_abort: true`.
```

### 22C — CI cross-check scripts

```text
scripts/check_error_codes.py:
  Walks src/ for emitted codes: regex /[A-Z]+-[A-Z0-9\-]+-?\d{4}/.
  Ensures every emitted code exists in config/error_codes.yaml.
  Ensures every YAML entry has:
    severity, template, spec_reference, fix_suggestion,
    fields_required, test_fixture (or test_generator).
  Ensures every entry's test_fixture file exists and its test case references the code.
  Exit 1 on mismatch.

scripts/generate_rule_catalog.py:
  Generates docs/error_codes.md from the YAML registry.
  Includes cross-reference tables (code → spec clause, code → Arelle code, etc.).
  Run in CI, diff committed — if catalog changes without registry change, fails.
```

---
## 23. ROADMAP AND MILESTONES

**18-24 months, phased. Each milestone has acceptance criteria. Pass rates per §20.**

### 23A — Phase 0: Foundation (months 1-2)

Deliverable: Parse + model for XBRL 2.1 XML, taxonomy cache, security, CLI skeleton.
  - core/constants.py, types.py, exceptions.py
  - parser/xml_parser.py + security (xxe_guard, entity_limits)
  - parser/format_detector.py
  - parser/decimal_parser.py, datetime_parser.py
  - taxonomy/resolver.py + cache.py (L1/L2) + catalog.py
  - taxonomy/fetcher.py + url_allowlist
  - model/builder.py (DOM mode only, no streaming yet)
  - validator/pipeline.py skeleton
  - cli/main.py (validate subcommand)
  - Test: 40% of unit tests written

Acceptance:
  - `xbrl-validate small_10k.xml` runs end-to-end without errors for a hand-coded valid instance
  - Taxonomy cache caches us-gaap-2024 once, loads from L2 subsequently
  - XXE test suite passes 100%
  - Decimal-everywhere CI check in place

### 23B — Phase 1: XBRL 2.1 + conformance (months 2-4)

Deliverable: Full XBRL 2.1 validator, passing conformance suite.
  - validator/spec/xbrl21/ all files
  - model/merge.py, equivalence.py
  - validator/self_check.py
  - conformance/runner.py + XBRL 2.1 suite integrated
  - report/json_report.py, sarif_report.py
  - 80% unit test coverage for spec/xbrl21/

Acceptance:
  - XBRL 2.1 conformance suite: > 95% strict pass
  - 25+ error codes exercised by tests
  - JSON + SARIF output formats stable

### 23C — Phase 2: Streaming + large files (months 3-5, parallel with Phase 1)

Deliverable: Streaming infrastructure for large files.
  - streaming/sax_handler.py, fact_index.py, fact_store.py, disk_spill.py
  - streaming/mmap_reader.py, chunked_reader.py, storage_detector.py
  - streaming/memory_budget.py
  - model/builder_streaming.py
  - tests/large_file/ — 200 MB, 1 GB, 5 GB tests
  - tests/benchmarks/ initial baselines

Acceptance:
  - 1 GB instance parses in < 10 min, < 2 GB RAM
  - InMemory vs DiskSpilled indexes produce bit-identical query results
  - Memory budget enforcement test passes
  - Threshold-boundary tests pass

### 23D — Phase 3: Dimensions + Calc 1.0 (months 4-6)

Deliverable: XDT 1.0 full validator + classic Calc.
  - validator/spec/dimensions/ all files
  - validator/spec/calculation/ (classic.py, tolerance.py, rounding.py, network_walker.py)
  - networks/ full build (base_set, prohibition, definition_network, calculation_network)
  - Typed-dim schema validation
  - targetRole traversal

Acceptance:
  - XDT 1.0 conformance: > 95% strict pass
  - Calc classic checks pass tolerance tests
  - Hypercube inheritance and targetRole test cases pass

### 23E — Phase 4: iXBRL + transforms + package (months 5-7)

Deliverable: Full iXBRL 1.1 + taxonomy packages + OIM parsers.
  - parser/ixbrl_parser.py + ixbrl_transforms.py + ixbrl_continuation.py
  - validator/spec/inline/ all files
  - parser/package_parser.py + taxonomy/package.py + package_metadata.py + catalog (full OASIS)
  - parser/json_parser.py + csv_parser.py (OIM formats)
  - streaming/json_streamer.py, csv_streamer.py
  - model/builder_oim.py
  - validator/spec/oim/ (structural validation, round-trip)

Acceptance:
  - iXBRL 1.1 conformance: > 90%
  - Taxonomy Package 1.0 conformance: > 95%
  - OIM JSON/CSV round-trip: > 90% on conformance suite
  - Multi-target iXBRL supported

### 23F — Phase 5: EFM regulator (months 6-9)

Deliverable: SEC EFM v1.0.
  - validator/regulator/efm/ all files (dei, cik, negation, naming, period, share_class,
    role_hierarchy, presentation, label, hidden_facts, structural, ixbrl, forms/)
  - config/profiles/efm/ complete with version_map, form_specific YAMLs
  - plugin/profile_loader.py + yaml_rules/
  - NEGVAL catalog loaded
  - EFM 6.20.x iXBRL rules

Acceptance:
  - Validates real 10-K, 10-Q, 8-K, S-1, 20-F filings from SEC corpus without false-positives
  - EFM rule count > 140
  - Arelle-compat diff published; known differences documented

### 23G — Phase 6: Calc 1.1 + ESEF (months 8-11)

Deliverable: Calc 1.1 + full ESEF validator.
  - validator/spec/calculation/calc_1_1.py + duplicate_handler.py
  - validator/regulator/esef/ all files incl. signed_package.py, anchoring.py, block_tagging.py
  - config/profiles/esef/ complete
  - html_profile.py strict enforcement

Acceptance:
  - Calc 1.1 conformance: > 90%
  - ESEF: validates real ESEF annual reports without false-positives
  - Anchoring checks: > 30 rules implemented
  - Signed package (XAdES) verification working

### 23H — Phase 7: Formula 1.0 + Table (months 10-13)

Deliverable: Formula + Table linkbase.
  - validator/spec/formula/ all files, including all 11 filter types
  - xpath_bridge.py via elementpath
  - xpath_functions.py — XFI registry (50+ functions)
  - validator/spec/table/ all files including renderer
  - validator/spec/enumerations/
  - validator/spec/generic/
  - validator/spec/versioning/

Acceptance:
  - Formula 1.0 conformance: > 85%
  - Table 1.0 conformance: > 80%
  - Enumerations 2.0 conformance: > 90%
  - End-to-end: filing with both XDT and Formula evaluates in reasonable time

### 23I — Phase 8: XULE + FERC (months 12-15)

Deliverable: Full XULE engine + FERC regulator.
  - src/xule/ all files (lexer, parser, compiler, evaluator, query planner,
    factset, aspect, navigation, calendar, builtins, custom_functions)
  - validator/regulator/ferc/ + xule_runner + schedule_router
  - config/profiles/ferc/xule_rules/ full rule sets for Forms 1/2/3/6/60/714

Acceptance:
  - FERC Form 1 validates with full rule set in < 60s
  - XULE rule set loads from .xule source, compiles, caches
  - Parity with FERC's published rule results (> 95% of rules agree)

### 23J — Phase 9: HMRC + CIPC + MCA (months 14-17)

Deliverable: Remaining regulators.
  - validator/regulator/hmrc/ + ct600.py + companies_house.py
  - validator/regulator/cipc/ + entity_class.py + ifrs_sme.py
  - validator/regulator/mca/ + cin.py + din.py + ind_as.py
  - config/profiles/{hmrc,cipc,mca}/ complete

Acceptance:
  - Each regulator validates sample filings from e2e corpus
  - Cross-regulator CI (same test file run under different profiles doesn't leak state)

### 23K — Phase 10: API + Worker + Report formats (months 15-18)

Deliverable: Full service layer.
  - api/ full (FastAPI routes, WebSocket, auth, rate_limit, metrics)
  - worker.py (Celery)
  - report/ full (html, csv, junit, arelle_compat, jinja templates)
  - Docker / docker-compose deployable
  - Postgres schema + alembic migrations (for audit log, job history)
  - Observability (structured logs + Prometheus metrics)

Acceptance:
  - API handles 100 concurrent validations on 4-core box
  - WebSocket streams progress events
  - All 6 report formats render correctly

### 23L — Phase 11: AI layer + Cross-doc + Tagging (months 17-20)

Deliverable: v1.2 AI features.
  - ai/fix_suggester.py (deterministic templates — earlier phases contributed to this)
  - ai/llm_suggestions.py (Anthropic + OpenAI providers)
  - ai/cross_doc.py (quarterly aggregates, period-over-period)
  - ai/tagging_analyzer.py (version map, deprecated concept suggestions)
  - ai/business_rules.py (heuristic checks, informational)
  - taxonomy/version_map.py populated for us-gaap, IFRS, ESEF

Acceptance:
  - --enable-ai works for both providers
  - Fix suggestions visible in HTML report
  - Cross-doc Q1+Q2+Q3+Q4 test detects mismatches
  - Tagging analyzer suggests concept replacements

### 23M — Phase 12: Polish + docs + release (months 20-24)

Deliverable: v1.0 release.
  - docs/ all files complete (architecture, arelle_compat, conformance, error_codes,
    plugin_authoring, regulator_profiles, large_files, performance, security)
  - Full conformance report regenerated, pass rates hit targets per §23 intro
  - Customer migration guide (from Arelle)
  - Binary distributions (pypi, Docker image, CLI standalone)
  - Security audit (external, independent)
  - Performance benchmarks published

Acceptance:
  - All conformance target pass rates met or exceeded
  - Zero critical / high security audit findings
  - Documentation complete
  - 3+ beta customers have successfully migrated from Arelle

---

## 24. EXECUTION ORDER FOR AGENT

The agent should build in this strict order. Each step has tests and must pass
before the next begins.

```text
Step 01: Create project skeleton
  - pyproject.toml, Makefile, Dockerfile, .gitignore, .importlinter
  - Empty src/ tree (directories + __init__.py for all 90+ packages)
  - README stub, LICENSE
  - CI config: GitHub Actions with lint + mypy + pytest + importlinter stages
  - config/error_codes.yaml (empty registry with schema)
  - scripts/check_error_codes.py
  - scripts/check_imports.py
  VALIDATE: pytest runs (no tests yet, exit 0), mypy clean, importlinter clean

Step 02: Constants, types, exceptions
  Files: src/core/constants.py, types.py, exceptions.py, qname.py
  Tests: tests/unit/core/test_constants.py, test_types.py, test_qname.py
  VALIDATE: pytest tests/unit/core/ passes

Step 03: Security modules
  Files: src/security/xxe_guard.py, zip_guard.py, url_allowlist.py, entity_limits.py
  Tests: tests/security/test_xxe_attacks.py, test_billion_laughs.py, test_zip_bombs.py,
         test_path_traversal.py, test_ssrf.py
  VALIDATE: all security tests pass

Step 04: Format detector
  Files: src/core/parser/format_detector.py
  Tests: tests/unit/core/parser/test_format_detector.py (XML, iXBRL, JSON, CSV, package)
  VALIDATE: detects all formats correctly on fixture files

Step 05: Decimal parser, datetime parser
  Files: src/core/parser/decimal_parser.py, datetime_parser.py
  Tests: tests/unit/core/parser/test_decimal_parser.py, test_datetime_parser.py
  VALIDATE: Rule 16 compliance — no floats anywhere in numeric paths; ISO 8601 durations parse

Step 06: XML parser (DOM)
  Files: src/core/parser/xml_parser.py
  Tests: tests/unit/core/parser/test_xml_parser.py
  VALIDATE: parses well-formed XBRL, rejects XXE, records line/column

Step 07: Taxonomy cache + catalog + fetcher (offline-first)
  Files: src/core/taxonomy/cache.py, catalog.py, cache_keys.py, fetcher.py
  Tests: tests/unit/core/taxonomy/test_cache.py, test_catalog.py
  VALIDATE: L1→L2→L3 fallback works; catalog rewrites work; offline mode reject remote

Step 08: Package parser + taxonomy package metadata
  Files: src/core/parser/package_parser.py, src/core/taxonomy/package.py, package_metadata.py
  Tests: tests/unit/core/parser/test_package_parser.py, test_package_metadata.py
  VALIDATE: unzip with security, parse taxonomyPackage.xml, detect package types

Step 09: Taxonomy resolver (DTS discovery)
  Files: src/core/taxonomy/resolver.py, dts.py, lrr_registry.py, utr_registry.py
  Tests: tests/unit/core/taxonomy/test_resolver.py, test_dts.py
  VALIDATE: DTS closure computed; prohibition/override resolves; circular detection

Step 10: Model dataclasses + networks
  Files: src/core/model/*.py, src/core/networks/*.py
  Tests: tests/unit/core/model/, tests/unit/core/networks/
  VALIDATE: base_set computation passes conformance sub-case

Step 11: DOM model builder
  Files: src/core/model/builder.py
  Tests: tests/unit/core/model/test_builder.py
  VALIDATE: builds XBRLInstance from valid XBRL document

Step 12: Pipeline skeleton + first spec validator (XBRL 2.1 instance+context+unit+fact)
  Files: src/validator/pipeline.py, pipeline_config.py
         src/validator/spec/xbrl21/instance.py, context.py, unit.py, fact.py
  Tests: integration test against XBRL 2.1 conformance subset
  VALIDATE: > 80% strict pass on XBRL 2.1 conformance "basic" subset

Step 13: Remaining XBRL 2.1 validators (tuple, footnote, schema_ref)
  VALIDATE: > 95% strict pass on full XBRL 2.1 conformance suite

Step 14: CLI + first report format (JSON)
  Files: src/cli/main.py, src/report/generator.py, json_report.py
  Tests: tests/integration/test_cli.py
  VALIDATE: `xbrl-validate small_valid.xml --output json` produces valid JSON

Step 15: Streaming infrastructure (sax_handler, fact_index, fact_store, disk_spill,
         memory_budget, mmap_reader, chunked_reader, storage_detector, counting_wrapper)
  Tests: tests/large_file/ — 200 MB, 1 GB tests
  VALIDATE: 1 GB file parses within budget; InMemory vs DiskSpilled equivalent

Step 16: Streaming model builder + streaming XBRL 2.1 validation
  Files: src/core/model/builder_streaming.py
  Tests: tests/large_file/test_streaming_xml_1gb.py + reused spec validators
  VALIDATE: streaming path produces same validation results as DOM path on small files

Step 17: Dimensions XDT 1.0
  Files: src/validator/spec/dimensions/ all files
  Tests: tests/unit/validator/spec/test_dimensions_*.py + conformance subset
  VALIDATE: > 95% strict pass on XDT 1.0 conformance

Step 18: Calculation classic + networks.calculation_network
  Files: src/validator/spec/calculation/classic.py, tolerance.py, rounding.py, network_walker.py
  Tests: tests/unit/validator/spec/test_calculation_classic.py + XBRL 2.1 calc conformance subset
  VALIDATE: Calc tolerance math matches spec test cases

Step 19: iXBRL parser + transforms + continuation
  Files: src/core/parser/ixbrl_parser.py, ixbrl_transforms.py, ixbrl_continuation.py
         src/validator/spec/inline/ all files
  Tests: tests/unit/core/parser/test_ixbrl_*.py + iXBRL 1.1 conformance
  VALIDATE: > 90% strict pass on iXBRL 1.1 conformance

Step 20: OIM — JSON parser + CSV parser + builders + structural validators
  Files: src/core/parser/json_parser.py, csv_parser.py
         src/core/parser/streaming/json_streamer.py, csv_streamer.py
         src/core/model/builder_oim.py
         src/validator/spec/oim/ all files
  Tests: OIM 1.0 conformance, round-trip tests
  VALIDATE: Rule 16 compliance on numeric fact values; round-trip > 90%

Step 21: Label + Presentation + Definition + Reference + Generic + Enumerations + Versioning
  Files: src/validator/spec/label/, presentation/, definition/, reference/, generic/,
         enumerations/, versioning/
  Tests: unit + conformance subsets
  VALIDATE: relevant conformance suites > 90% strict pass

Step 22: Calc 1.1 — alongside classic
  Files: src/validator/spec/calculation/calc_1_1.py, duplicate_handler.py
  Tests: tests/unit/validator/spec/test_calculation_1_1.py + Calc 1.1 conformance
  VALIDATE: > 90% strict pass Calc 1.1 suite

Step 23: Formula 1.0 (this is the BIG step — ~1 month)
  Files: src/validator/spec/formula/ all files
  Tests: Formula 1.0 conformance
  VALIDATE: > 85% strict pass Formula suite

Step 24: Table linkbase
  Files: src/validator/spec/table/ all files
  Tests: Table 1.0 conformance
  VALIDATE: > 80% strict pass Table suite

Step 25: Plugin system + EFM regulator
  Files: src/plugin/ all files, src/validator/regulator/efm/ all files
  Tests: tests/unit/regulator/efm/, tests/e2e/test_real_sec_10k.py
  VALIDATE: validates 100+ real SEC filings without false-positive storm

Step 26: ESEF regulator
  Files: src/validator/regulator/esef/ all files
  Tests: tests/unit/regulator/esef/, tests/e2e/test_real_esef_annual.py
  VALIDATE: validates real ESEF filings; anchoring rules produce expected results

Step 27: XULE engine
  Files: src/xule/ all files
  Tests: tests/unit/xule/
  VALIDATE: XULE runs a reference rule set, benchmarked time

Step 28: FERC regulator (uses XULE)
  Files: src/validator/regulator/ferc/ all files, config/profiles/ferc/xule_rules/*.xule
  Tests: tests/e2e/test_real_ferc_form1.py, test_real_ferc_form714.py
  VALIDATE: validates real FERC Form 1 filings; matches FERC published rule results > 95%

Step 29: HMRC + CIPC + MCA regulators
  Files: src/validator/regulator/hmrc/, cipc/, mca/
  Tests: tests/unit/regulator/{hmrc,cipc,mca}/, tests/e2e/
  VALIDATE: each validates sample filings

Step 30: Report generators — all formats
  Files: src/report/ (html, csv, junit, arelle_compat, templates)
  Tests: tests/unit/report/
  VALIDATE: all formats render, HTML visually reviewed, SARIF schema-valid

Step 31: API + Worker
  Files: src/api/ all files
  Tests: tests/integration/test_api_endpoints.py
  VALIDATE: API handles upload, returns job_id, streams progress, returns result

Step 32: AI layer (deterministic templates; LLM suggestions as opt-in)
  Files: src/ai/ all files
  Tests: tests/unit/ai/
  VALIDATE: every error code has a template suggestion; LLM path mockable

Step 33: Cross-doc + Business rules + Tagging analyzer
  Files: src/ai/cross_doc.py, business_rules.py, tagging_analyzer.py
  Tests: tests/unit/ai/, tests/integration/test_cross_document.py
  VALIDATE: multi-doc input produces cross-doc findings

Step 34: Full conformance run + historical tracking
  Scripts: scripts/benchmark.py, scripts/arelle_compare.py
  VALIDATE: conformance/results.json updated, pass rates at targets
            conformance/reports/diff_from_arelle.md generated

Step 35: Documentation + release
  docs/: architecture, arelle_compat, conformance, error_codes, plugin_authoring,
         regulator_profiles, large_files, performance, security
  VALIDATE: docs build; examples run; API reference generated from code
```

---

## 25. ACCEPTANCE CRITERIA FOR v1.0 RELEASE

```text
CORRECTNESS:
  [ ] XBRL 2.1 conformance strict pass rate > 98%
  [ ] XDT 1.0 conformance strict pass rate > 95%
  [ ] Calc 1.0 & Calc 1.1 conformance strict pass rate > 95% each
  [ ] iXBRL 1.1 conformance strict pass rate > 95%
  [ ] Formula 1.0 conformance strict pass rate > 85%
  [ ] Table 1.0 conformance strict pass rate > 80%
  [ ] Enumerations 2.0 conformance strict pass rate > 95%
  [ ] OIM 1.0 conformance strict pass rate > 90%
  [ ] Taxonomy Packages 1.0 conformance strict pass rate > 95%
  [ ] Generic Links conformance strict pass rate > 90%
  [ ] Real-filing tests (SEC corpus 500+ filings, ESEF 100+, FERC 20+) pass

PERFORMANCE:
  [ ] 10 MB XBRL validated in < 5s (DOM mode)
  [ ] 100 MB XBRL validated in < 2 min (streaming)
  [ ] 1 GB XBRL validated in < 15 min (streaming + spill), < 2 GB RAM
  [ ] 5 GB XBRL parses (may not fully validate) in < 90 min, < 4 GB RAM
  [ ] Taxonomy warm-load us-gaap-2024 < 500 ms
  [ ] FERC Form 1 with XULE rule set < 60s
  [ ] API sustains 20 concurrent small-file validations on 4-core box

SECURITY:
  [ ] XXE attack vectors: 100% blocked
  [ ] Billion laughs / quadratic blowup: 100% blocked
  [ ] Zip bomb: 100% blocked
  [ ] Path traversal: 100% blocked
  [ ] SSRF (taxonomy fetch to private IPs): 100% blocked
  [ ] External security audit: zero critical or high findings

QUALITY:
  [ ] mypy strict passes with zero errors on src/
  [ ] Unit test coverage > 85% statement, > 75% branch
  [ ] Security module coverage > 95%
  [ ] No `float(` in value-path code (CI check)
  [ ] import-linter contracts pass (Rule 5)
  [ ] Every error code has a test fixture
  [ ] Every error code has a fix suggestion

COMPATIBILITY:
  [ ] Arelle compatibility matrix published (docs/arelle_compat.md)
  [ ] Known differences from Arelle documented with rationale
  [ ] Migration guide from Arelle published

OBSERVABILITY:
  [ ] Structured logs in JSON
  [ ] Prometheus metrics exposed
  [ ] WebSocket progress events documented
  [ ] OpenTelemetry tracing optional via env var

DOCUMENTATION:
  [ ] architecture.md, large_files.md, performance.md, security.md complete
  [ ] API reference (OpenAPI) published
  [ ] Plugin authoring guide with working example
  [ ] Regulator profile authoring guide
  [ ] 3+ end-to-end tutorials (EFM, ESEF, FERC)

DEPLOYMENT:
  [ ] pip install xbrl-validator works
  [ ] Docker image < 500 MB
  [ ] docker-compose up brings the API + worker + Redis + Postgres + Prometheus
  [ ] GitHub Actions CI green
```

---

## 26. DEPLOYMENT

```text
Dockerfile:
  FROM python:3.12-slim
  Multi-stage: builder installs deps, final image ships src/ + entrypoint
  Non-root user
  Health check: CMD curl -f http://localhost:8000/health || exit 1

Dockerfile.worker:
  Same base, command = celery -A src.api.worker worker

docker-compose.yml:
  services:
    api          → uvicorn src.api.app:app, port 8000
    worker       → celery worker (scalable replicas)
    redis        → for Celery + rate limit cache
    postgres     → job history + audit log
    prometheus   → scraping /v1/metrics
    grafana      → dashboards (optional)

VOLUMES:
  - taxonomy-cache (large, persistent)
  - postgres-data
  - input-files (temp, emptied after job TTL)

ENV:
  XBRL_MEMORY_BUDGET_GB            default 4
  XBRL_MAX_FILE_SIZE_GB            default 10
  XBRL_TAXONOMY_CACHE_DIR          default /var/cache/xbrl
  XBRL_TAXONOMY_FETCH_TIMEOUT_S    default 30
  XBRL_ALLOW_HTTP                  default false
  XBRL_OFFLINE                     default false
  XBRL_ENABLE_AI                   default false
  ANTHROPIC_API_KEY                optional
  OPENAI_API_KEY                   optional

SCALING:
  API: stateless, horizontal (behind load balancer)
  Worker: horizontal (scale based on Celery queue depth)
  Redis: single instance OK for <1000 rps; cluster for more
  Postgres: single instance + read replicas if needed
  Taxonomy cache: shared volume across workers (read-mostly)

OPERATIONS:
  /v1/health/ready checks: Redis + Postgres reachable, cache dir writable
  /v1/metrics for Prometheus
  Log format JSON → ingestible by Loki / Elasticsearch
  OpenTelemetry tracing optional (OTEL_EXPORTER_OTLP_ENDPOINT)
```

---

## 27. ARELLE COMPATIBILITY MATRIX (docs/arelle_compat.md skeleton)

```text
Per Rule 14, this file is MANDATORY for customer migration.

Sections:
  1. Error code mapping (our code → Arelle code)
     Table: ~800 rows, one per error code
     Columns: our_code, arelle_code, identical_semantics, notes
  2. Output format differences
     - Log message format: we structure fields; Arelle is free text
     - SARIF: we support; Arelle supports via plugin
     - Exit codes: we use 0=clean, 1=errors, 2=warnings, 3=abort;
                   Arelle uses 0=ok, any non-0 for any issue
  3. Behavior differences (per spec area)
     Table: spec_area, test_case, our_verdict, arelle_verdict, resolution
     - Dimensions: we enforce typed-dim schema STRICTLY; Arelle warns
     - Calc 1.1: we implement rounded-duplicate semantics per spec; Arelle's
                 implementation is optional in some releases
     - Formula: our XPath errors reference elementpath position; Arelle uses own
     - OIM round-trip: we emit per-fact diffs; Arelle emits document-level
  4. Performance differences
     - We are 2–5× faster on streaming large files (our design point)
     - Arelle is 1.2–2× faster on small files with warm JVM (their pypy path)
  5. Feature parity matrix
     Feature                     ours        arelle
     ----------------------------------------------------
     XBRL 2.1                    full        full
     Dimensions 1.0              full        full
     Formula 1.0                 full        full
     Calc 1.1                    full        partial
     iXBRL 1.1                   full        full
     Table 1.0                   full        full
     OIM JSON/CSV                full        full
     XULE                        full        via plugin
     FERC XULE rules             full        via plugin
     Signed ESEF packages        full        via plugin
     Streaming > 1 GB            yes         limited
     AI fix suggestions          yes         no
     ...
  6. Migration guide
     - Running our validator with --output arelle-compat produces logs
       that can be diffed against existing Arelle outputs
     - Config mapping: Arelle --plugins flag vs our --regulator flag
     - Taxonomy cache migration: use scripts/migrate_arelle_cache.py
```

---

## 28. RISK REGISTER AND OPEN QUESTIONS

```text
RISKS:

R1 — Formula 1.0 scope
  Formula is ~20% of total code effort. If elementpath falls short on XBRL
  Functions Registry edge cases, we'll need to extend it (contributes upstream)
  or fork. Budget: 3-month contingency in Phase 7 already.

R2 — Conformance suite availability
  XBRL International requires membership for full conformance suite access.
  If membership lapses, we can't run. Mitigation: commit to membership as line
  item; mirror suite internally.

R3 — FERC XULE rule drift
  FERC publishes new rule sets each year. Our config/profiles/ferc/xule_rules/
  must track. Mitigation: quarterly diff against published sources; automated
  test that fails when upstream changes.

R4 — ESEF signed packages (XAdES)
  XAdES is a complex spec. Implementation risk. Mitigation: use well-maintained
  library (signxml or similar) if available; otherwise reduced-scope verification
  (signature presence only, not full chain).

R5 — Large-file performance on cloud storage
  Cloud block storage (EBS, etc.) has different seek characteristics than
  local SSDs. Mitigation: test on typical cloud volumes; add profile flag
  to force ChunkedReader even on "SSD"-reported storage.

R6 — Decimal arithmetic precision
  Python Decimal default precision 28; some edge cases need higher. Mitigation:
  set getcontext().prec = 40 in validator contexts; measure impact.

R7 — Taxonomy evolution
  us-gaap ships yearly; our version_map must keep up. Mitigation: annual
  dedicated review cycle; CI test that version_map covers recent years.

OPEN QUESTIONS:

Q1 — Table linkbase rendering: produce HTML, JSON, or both for API output?
Q2 — AI layer: LLM fallback default on or off? (We default OFF; open to
     making ON default once cost/latency acceptable.)
Q3 — Plugin sandboxing: should custom Python plugins run in restricted env?
     (Decision: trusted-plugin model for v1.0; sandbox for v2.0.)
Q4 — XULE rule set signing: should FERC-published rule sets be verified
     cryptographically? (FERC doesn't sign today; track.)
Q5 — GPU acceleration for Formula XPath evaluation?
     (No for v1.0; revisit if benchmarks justify.)
```

---

## 29. SUMMARY

This plan replaces v2.0 to close the scope gap with Arelle and production regulator
needs. Key differentiators vs v2.0:

```text
1. Full XBRL specification coverage (XBRL 2.1, XDT 1.0, Calc 1.0 + 1.1, Formula 1.0,
   iXBRL 1.1, Table 1.0, Enumerations 2.0, OIM, Generic Links, Versioning).
2. Regulator modules sized for real EFM/ESEF/FERC/HMRC/CIPC/MCA depth (not demo).
3. Conformance suites as primary quality gate (not just unit tests).
4. Large-file handling deeply engineered (streaming, disk-spill, mmap + chunked,
   memory budget with voluntary/forced spill).
5. Arelle compatibility as a first-class concern (Rule 14).
6. XULE as a full query engine, not one-liners.
7. Error code registry with fix suggestions and Arelle mapping (Rule 4).
8. Security zero-trust (XXE/zip-bomb/SSRF tests).
9. Decimal-everywhere enforced (Rule 1 + Rule 16 + CI check).
10. Realistic 18–24 month timeline with phased milestones.
```

Expected outputs: ~585 files, ~180,000 LOC, 18–24 months with a 4–6 engineer team.

End of plan.
