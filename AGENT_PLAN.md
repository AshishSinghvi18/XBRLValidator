# XBRL/iXBRL Validator Engine — Agent Execution Plan

> **Version:** 2.0.0 | **Date:** 2026-04-20
> **Type:** Deterministic build plan for AI coding agent
> **Estimated Output:** 145+ files, 35,000+ lines of code
> **Language:** Python 3.12+ (primary), TypeScript (API alternative)

---

## 0. AGENT OPERATING RULES (READ BEFORE ANY CODE GENERATION)

```text
RULE 1 — DECIMAL NEVER FLOAT
   ALL numeric XBRL values → Python `decimal.Decimal`.
   NEVER use `float` for fact values, tolerances, rounding, scale multiplication.
   Violation = critical defect.

RULE 2 — STREAMING FIRST
   Every file-reading function MUST check file size first.
   ≤ 100 MB → DOM parsing allowed.
   > 100 MB → MUST use streaming / SAX / iterparse.
   NEVER load an entire file > 100 MB into memory.

RULE 3 — ZERO-TRUST PARSING
   All XML parsing MUST disable: external entities, DTD, network resolution,
   entity expansion (cap at 100). Use defusedxml or hardened lxml XMLParser.

RULE 4 — REGISTERED ERROR CODES
   Every emitted message MUST have a code (PREFIX-NNNN), severity,
   spec reference, message template, and fix suggestion — all registered
   in config/error_codes.yaml.

RULE 5 — REGULATOR ISOLATION
   src/core/* and src/validator/spec/* must NEVER import from
   src/validator/regulator/*. Regulators are loaded dynamically via
   src/plugin/profile_loader.py.

RULE 6 — TYPE HINTS EVERYWHERE
   Every function: full parameter + return type hints.
   Every attribute: type annotation. Use dataclasses / Pydantic.

RULE 7 — DOCSTRINGS WITH SPEC REFERENCES
   Every validation function docstring MUST cite the spec clause,
   what it checks, what error codes it emits, and fix suggestion.

RULE 8 — TEST PER RULE
   Every validation rule needs ≥ 3 tests: valid-input, invalid-input, edge-case.
   Large-file code needs threshold-boundary tests (99 MB / 101 MB).

RULE 9 — FAIL-SAFE RECOVERY
   On malformed input: log error, skip section, continue parsing.
   Never crash. Never raise unhandled exception to caller.

RULE 10 — DETERMINISTIC
   Same input → same output. AI suggestions are the ONLY non-deterministic
   part and MUST be tagged source="AI".

RULE 11 — MEMORY BUDGET
   Default 4 GB. Every accumulating component tracks usage via MemoryBudget.
   Spill to disk (SQLite) when approaching limit.

RULE 12 — STRUCTURED LOGGING
   Python logging module. Every stage logs: name, start, end, items processed,
   errors found, memory used.
```

---

## 1. DEPENDENCIES

```toml
# pyproject.toml [project] section
[project]
name = "xbrl-validator"
version = "1.0.0"
requires-python = ">=3.12"
dependencies = [
  "lxml>=5.1.0",
  "defusedxml>=0.7.1",
  "jsonschema>=4.21.0",
  "orjson>=3.10.0",
  "ijson>=3.2.3",
  "polars>=0.20.0",
  "fastapi>=0.110.0",
  "uvicorn[standard]>=0.29.0",
  "python-multipart>=0.0.9",
  "celery[redis]>=5.3.6",
  "redis>=5.0.0",
  "sqlalchemy>=2.0.29",
  "asyncpg>=0.29.0",
  "alembic>=1.13.0",
  "typer[all]>=0.12.0",
  "rich>=13.7.0",
  "jinja2>=3.1.3",
  "httpx>=0.27.0",
  "pydantic>=2.6.0",
  "msgpack>=1.0.8",
  "psutil>=5.9.8",
]
[project.optional-dependencies]
ai  = ["openai>=1.14.0"]
dev = [
  "pytest>=8.1.0", "pytest-asyncio>=0.23.0", "pytest-cov>=5.0.0",
  "pytest-timeout>=2.3.1", "pytest-benchmark>=4.0.0",
  "mypy>=1.9.0", "ruff>=0.3.0", "hypothesis>=6.98.0",
]
[project.scripts]
xbrl-validate = "src.cli.main:app"
```

---

## 2. COMPLETE FILE TREE (agent MUST create every file)

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
├── README.md
├── LICENSE                              # MIT
│
├── config/
│   ├── default.yaml
│   ├── error_codes.yaml                 # FULL error registry
│   ├── profiles/
│   │   ├── index.yaml
│   │   ├── efm/
│   │   │   ├── profile.yaml
│   │   │   ├── mandatory_elements.yaml
│   │   │   ├── naming_rules.yaml
│   │   │   ├── negation_rules.yaml
│   │   │   ├── structural_rules.yaml
│   │   │   └── hidden_fact_rules.yaml
│   │   ├── esef/
│   │   │   ├── profile.yaml
│   │   │   ├── mandatory_tags.yaml
│   │   │   ├── anchoring_rules.yaml
│   │   │   ├── package_rules.yaml
│   │   │   └── block_tagging_rules.yaml
│   │   ├── ferc/
│   │   │   ├── profile.yaml
│   │   │   └── xule_rules/
│   │   │       ├── form1.xule
│   │   │       ├── form2.xule
│   │   │       └── common.xule
│   │   ├── hmrc/
│   │   │   ├── profile.yaml
│   │   │   └── mandatory_elements.yaml
│   │   ├── cipc/
│   │   │   ├── profile.yaml
│   │   │   └── mandatory_elements.yaml
│   │   └── mca/
│   │       ├── profile.yaml
│   │       └── mandatory_elements.yaml
│   └── transforms/
│       ├── ixt-4.json
│       ├── ixt-5.json
│       └── ixt-sec.json
│
├── src/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── constants.py
│   │   ├── exceptions.py
│   │   ├── types.py
│   │   ├── parser/
│   │   │   ├── __init__.py
│   │   │   ├── format_detector.py
│   │   │   ├── xml_parser.py
│   │   │   ├── ixbrl_parser.py
│   │   │   ├── json_parser.py
│   │   │   ├── csv_parser.py
│   │   │   ├── transform_registry.py
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
│   │   │       └── chunked_reader.py
│   │   ├── taxonomy/
│   │   │   ├── __init__.py
│   │   │   ├── resolver.py
│   │   │   ├── cache.py
│   │   │   ├── catalog.py
│   │   │   ├── package.py
│   │   │   └── concept_index.py
│   │   └── model/
│   │       ├── __init__.py
│   │       ├── xbrl_model.py
│   │       ├── builder.py
│   │       ├── builder_streaming.py
│   │       ├── indexes.py
│   │       └── merge.py
│   ├── validator/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── pipeline.py
│   │   ├── pipeline_config.py
│   │   ├── error_catalog.py
│   │   ├── message.py
│   │   ├── self_check.py
│   │   ├── spec/
│   │   │   ├── __init__.py
│   │   │   ├── xbrl21.py
│   │   │   ├── dimensions.py
│   │   │   ├── calculation.py
│   │   │   ├── formula.py
│   │   │   ├── table.py
│   │   │   ├── inline.py
│   │   │   ├── label.py
│   │   │   ├── presentation.py
│   │   │   └── definition.py
│   │   └── regulator/
│   │       ├── __init__.py
│   │       ├── efm.py
│   │       ├── esef.py
│   │       ├── esef_package.py
│   │       ├── esef_anchoring.py
│   │       ├── ferc_xule.py
│   │       ├── hmrc.py
│   │       ├── cipc.py
│   │       ├── mca.py
│   │       └── custom.py
│   ├── xule/
│   │   ├── __init__.py
│   │   ├── lexer.py
│   │   ├── parser.py
│   │   ├── compiler.py
│   │   ├── evaluator.py
│   │   ├── query_planner.py
│   │   ├── ast_nodes.py
│   │   └── builtins.py
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── fix_suggester.py
│   │   ├── cross_doc.py
│   │   ├── business_rules.py
│   │   └── tagging_analyzer.py
│   ├── report/
│   │   ├── __init__.py
│   │   ├── generator.py
│   │   ├── json_report.py
│   │   ├── sarif_report.py
│   │   ├── html_report.py
│   │   ├── csv_report.py
│   │   └── templates/
│   │       ├── report.html.j2
│   │       └── summary.html.j2
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── middleware.py
│   │   ├── websocket.py
│   │   ├── worker.py
│   │   ├── schemas.py
│   │   └── health.py
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── progress.py
│   │   └── formatters.py
│   ├── plugin/
│   │   ├── __init__.py
│   │   ├── loader.py
│   │   ├── profile_loader.py
│   │   ├── rule_compiler.py
│   │   └── base.py
│   └── utils/
│       ├── __init__.py
│       ├── qname.py
│       ├── datetime_utils.py
│       ├── xml_utils.py
│       ├── hash_utils.py
│       └── size_utils.py
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── factories.py
│   ├── unit/
│   │   ├── core/
│   │   │   ├── test_format_detector.py
│   │   │   ├── test_xml_parser.py
│   │   │   ├── test_xml_parser_streaming.py
│   │   │   ├── test_ixbrl_parser.py
│   │   │   ├── test_ixbrl_parser_streaming.py
│   │   │   ├── test_json_parser.py
│   │   │   ├── test_csv_parser.py
│   │   │   ├── test_transform_registry.py
│   │   │   ├── test_taxonomy_resolver.py
│   │   │   ├── test_taxonomy_cache.py
│   │   │   ├── test_catalog.py
│   │   │   ├── test_model_builder.py
│   │   │   ├── test_model_builder_streaming.py
│   │   │   ├── test_model_indexes.py
│   │   │   ├── test_model_merge.py
│   │   │   └── test_qname.py
│   │   ├── streaming/
│   │   │   ├── test_sax_handler.py
│   │   │   ├── test_memory_budget.py
│   │   │   ├── test_fact_index.py
│   │   │   ├── test_fact_store.py
│   │   │   ├── test_disk_spill.py
│   │   │   ├── test_mmap_reader.py
│   │   │   └── test_chunked_reader.py
│   │   ├── validator/
│   │   │   ├── test_xbrl21.py
│   │   │   ├── test_dimensions.py
│   │   │   ├── test_calculation.py
│   │   │   ├── test_formula.py
│   │   │   ├── test_inline.py
│   │   │   ├── test_table.py
│   │   │   ├── test_label.py
│   │   │   └── test_self_check.py
│   │   ├── regulator/
│   │   │   ├── test_efm.py
│   │   │   ├── test_esef.py
│   │   │   ├── test_esef_anchoring.py
│   │   │   ├── test_esef_package.py
│   │   │   ├── test_ferc_xule.py
│   │   │   ├── test_hmrc.py
│   │   │   ├── test_cipc.py
│   │   │   ├── test_mca.py
│   │   │   └── test_rule_compiler.py
│   │   ├── xule/
│   │   │   ├── test_lexer.py
│   │   │   ├── test_parser.py
│   │   │   ├── test_compiler.py
│   │   │   ├── test_evaluator.py
│   │   │   └── test_query_planner.py
│   │   ├── ai/
│   │   │   ├── test_fix_suggester.py
│   │   │   ├── test_business_rules.py
│   │   │   └── test_tagging_analyzer.py
│   │   └── report/
│   │       ├── test_json_report.py
│   │       ├── test_sarif_report.py
│   │       └── test_html_report.py
│   ├── integration/
│   │   ├── test_pipeline_efm.py
│   │   ├── test_pipeline_esef.py
│   │   ├── test_pipeline_ferc.py
│   │   ├── test_pipeline_hmrc.py
│   │   ├── test_pipeline_inline.py
│   │   ├── test_pipeline_multidoc.py
│   │   ├── test_api_endpoints.py
│   │   └── test_cli.py
│   ├── large_file/
│   │   ├── conftest.py
│   │   ├── test_streaming_xml.py
│   │   ├── test_streaming_ixbrl.py
│   │   ├── test_streaming_json.py
│   │   ├── test_streaming_csv.py
│   │   ├── test_memory_budget.py
│   │   ├── test_disk_spill.py
│   │   ├── test_mmap_random_access.py
│   │   ├── test_million_facts.py
│   │   ├── test_5gb_synthetic.py
│   │   └── generators/
│   │       ├── xbrl_generator.py
│   │       ├── ixbrl_generator.py
│   │       └── fact_generator.py
│   ├── conformance/
│   │   ├── test_xbrl21_conformance.py
│   │   ├── test_dimensions_conformance.py
│   │   ├── test_inline_conformance.py
│   │   └── test_formula_conformance.py
│   ├── e2e/
│   │   ├── test_real_sec_filing.py
│   │   ├── test_real_esef_filing.py
│   │   └── test_real_ferc_filing.py
│   └── fixtures/
│       ├── valid/
│       │   ├── simple_instance.xml
│       │   ├── simple_inline.html
│       │   ├── simple_json.json
│       │   ├── simple_csv/
│       │   │   ├── metadata.json
│       │   │   └── data.csv
│       │   └── taxonomy/
│       │       ├── schema.xsd
│       │       ├── cal.xml
│       │       ├── pre.xml
│       │       ├── def.xml
│       │       └── lab.xml
│       └── invalid/
│           ├── missing_context.xml
│           ├── period_mismatch.xml
│           ├── calc_inconsistency.xml
│           ├── dimension_error.xml
│           ├── duplicate_facts.xml
│           ├── broken_continuation.html
│           ├── missing_dei.xml
│           ├── bad_cik.xml
│           ├── unanchored_extension.xml
│           └── malformed_xml.xml
│
└── scripts/
    ├── download_conformance.sh
    ├── preload_taxonomies.py
    ├── generate_rule_catalog.py
    ├── generate_large_fixtures.py
    └── benchmark.py
```

---

## 3. CONSTANTS, TYPES, EXCEPTIONS

### 3A — `src/core/constants.py`

```text
IMPLEMENT these exact constants:

NAMESPACES:
  NS_XBRLI       = "http://www.xbrl.org/2003/instance"
  NS_LINK        = "http://www.xbrl.org/2003/linkbase"
  NS_XLINK       = "http://www.w3.org/1999/xlink"
  NS_XSD         = "http://www.w3.org/2001/XMLSchema"
  NS_XSI         = "http://www.w3.org/2001/XMLSchema-instance"
  NS_IX          = "http://www.xbrl.org/2013/inlineXBRL"
  NS_IXT_PREFIX  = "http://www.xbrl.org/inlineXBRL/transformation"
  NS_ISO4217     = "http://www.xbrl.org/2003/iso4217"
  NS_XBRLDI      = "http://xbrl.org/2006/xbrldi"
  NS_XBRLDT      = "http://xbrl.org/2005/xbrldt"

ARCROLES:
  ARCROLE_SUMMATION_ITEM    = "http://www.xbrl.org/2003/arcrole/summation-item"
  ARCROLE_PARENT_CHILD      = "http://www.xbrl.org/2003/arcrole/parent-child"
  ARCROLE_DOMAIN_MEMBER     = "http://xbrl.org/int/dim/arcrole/domain-member"
  ARCROLE_DIMENSION_DOMAIN  = "http://xbrl.org/int/dim/arcrole/dimension-domain"
  ARCROLE_DIMENSION_DEFAULT = "http://xbrl.org/int/dim/arcrole/dimension-default"
  ARCROLE_HYPERCUBE_DIM     = "http://xbrl.org/int/dim/arcrole/hypercube-dimension"
  ARCROLE_ALL               = "http://xbrl.org/int/dim/arcrole/all"
  ARCROLE_NOT_ALL           = "http://xbrl.org/int/dim/arcrole/notAll"
  ARCROLE_WIDER_NARROWER    = "http://www.esma.europa.eu/xbrl/esef/arcrole/wider-narrower"
  ARCROLE_CONCEPT_LABEL     = "http://www.xbrl.org/2003/arcrole/concept-label"
  ARCROLE_CONCEPT_REF       = "http://www.xbrl.org/2003/arcrole/concept-reference"
  ARCROLE_FOOTNOTE          = "http://www.xbrl.org/2003/arcrole/fact-footnote"

THRESHOLDS (all configurable via PipelineConfig):
  DEFAULT_LARGE_FILE_THRESHOLD_BYTES  = 100 * 1024 * 1024    # 100 MB
  DEFAULT_MEMORY_BUDGET_BYTES         = 4 * 1024 * 1024 * 1024 # 4 GB
  DEFAULT_FACT_INDEX_SPILL_THRESHOLD  = 10_000_000            # 10M facts
  DEFAULT_ERROR_BUFFER_LIMIT          = 10_000
  DEFAULT_MAX_FILE_SIZE_BYTES         = 10 * 1024 * 1024 * 1024 # 10 GB
  DEFAULT_IO_CHUNK_SIZE               = 64 * 1024 * 1024      # 64 MB
  DEFAULT_SAX_BUFFER_SIZE             = 8 * 1024 * 1024       # 8 MB
  DEFAULT_TAXONOMY_FETCH_TIMEOUT_S    = 30
  DEFAULT_MAX_ENTITY_EXPANSIONS       = 100
```

### 3B — `src/core/types.py`

```text
IMPLEMENT these enums and type aliases:

  PeriodType      → INSTANT, DURATION, FOREVER
  BalanceType     → DEBIT, CREDIT
  Severity        → ERROR, WARNING, INCONSISTENCY, INFO
  InputFormat     → XBRL_XML, IXBRL_HTML, XBRL_JSON, XBRL_CSV,
                    TAXONOMY_SCHEMA, LINKBASE, UNKNOWN
  ParserStrategy  → DOM, STREAMING
  LinkbaseType    → CALCULATION, PRESENTATION, DEFINITION, LABEL,
                    REFERENCE, FORMULA
  SpillState      → IN_MEMORY, SPILLING, ON_DISK

  Type aliases:
    QName        = str
    ContextID    = str
    UnitID       = str
    FactID       = str
    ByteOffset   = int
    DimensionKey = Tuple[Tuple[str, str], ...]
```

### 3C — `src/core/exceptions.py`

```text
Hierarchy (all inherit from XBRLValidatorError):
  XBRLValidatorError          — base
  ├── ParseError              — attrs: file_path, line, column
  ├── SecurityError           — XXE, DTD bomb
  ├── FileTooLargeError       — attrs: file_size, max_size
  ├── MemoryBudgetExceededError
  ├── TaxonomyResolutionError — attr: url
  ├── DiskSpillError
  ├── UnsupportedFormatError
  ├── ProfileNotFoundError    — attr: profile_id
  ├── XULESyntaxError         — attrs: file_path, line
  └── PipelineAbortError
```

---

## 4. FORMAT DETECTOR — `src/core/parser/format_detector.py`

```text
CLASS: FormatDetector
  __init__(self, config: PipelineConfig)
  detect(self, file_path: str) -> DetectionResult
  detect_batch(self, file_paths: List[str]) -> List[DetectionResult]

DATACLASS: DetectionResult
  format: InputFormat
  strategy: ParserStrategy    # DOM or STREAMING
  encoding: str
  file_path: str
  file_size_bytes: int
  is_compressed: bool
  mime_type: Optional[str]

DETECTION ALGORITHM (implement exactly):
  1. os.path.getsize → reject if > max_file_size_bytes
  2. Read first 4 bytes → if b"PK\x03\x04" → ZIP (taxonomy/filing package)
  3. Read first 8192 bytes → decode
  4. BOM detection: EF BB BF=UTF-8, FF FE=UTF-16LE, FE FF=UTF-16BE
  5. Content sniffing:
     "<?xml" or "<"     → XML sub-classify (step 6)
     "{"                → XBRL-JSON (threshold 50 MB for streaming)
     CSV header pattern → XBRL-CSV (threshold 200 MB for streaming)
     "<!DOCTYPE html"   → HTML sub-classify (step 7)
     else               → UNKNOWN → raise UnsupportedFormatError
  6. XML root tag:
     {NS_XBRLI}xbrl         → XBRL_XML
     {NS_XSD}schema          → TAXONOMY_SCHEMA
     {NS_LINK}linkbase       → LINKBASE
     html + ix: namespace    → IXBRL_HTML
  7. HTML body scan for ix:header/ix:nonFraction → IXBRL_HTML or UNKNOWN
  8. Set strategy = STREAMING if file_size > threshold else DOM
```

---

## 5. LARGE-FILE STREAMING INFRASTRUCTURE

### 5A — `src/core/parser/streaming/memory_budget.py`

```text
CLASS: MemoryBudget (singleton per pipeline run, thread-safe)

  __init__(self, total_bytes: int)

  register(component: str, max_bytes: int) -> MemoryAllocation
  can_allocate(component: str, additional_bytes: int) -> bool
  record_allocation(component: str, bytes_added: int) -> None
  record_deallocation(component: str, bytes_freed: int) -> None
  request_spill(component: str) -> None
  get_total_used() -> int
  get_system_rss() -> int          # psutil.Process().memory_info().rss

DATACLASS: MemoryAllocation
  component: str
  allocated_bytes: int
  used_bytes: int
  spill_state: SpillState

DEFAULT BUDGET SPLIT:
  Python runtime + libs    200 MB  (fixed)
  Taxonomy model           300 MB  (fixed after load)
  Context/Unit registries   50 MB  (fixed after parse)
  Fact index               500 MB  (spills at limit)
  Active fact values       500 MB  (LRU eviction)
  Validation state         200 MB  (spills error list at 10K)
  Error accumulator        100 MB  (spills to file)
  I/O buffers              150 MB  (fixed)
  Safety margin           2000 MB
```

### 5B — `src/core/parser/streaming/fact_index.py`

```text
DATACLASS: FactReference
  index: int                    # ordinal position
  concept: QName
  context_ref: ContextID
  unit_ref: Optional[UnitID]
  byte_offset: ByteOffset       # start byte in source file
  value_length: int             # byte length of value text
  is_numeric: bool
  is_nil: bool
  decimals: Optional[str]
  precision: Optional[str]
  id: Optional[FactID]
  source_line: int
  period_type: Optional[PeriodType] = None
  balance_type: Optional[BalanceType] = None

  property estimated_memory_bytes -> int:
      ~200 + len(strings)

CLASS: InMemoryFactIndex
  __init__(self, budget: MemoryBudget, spill_threshold: int)
  add(ref: FactReference) -> bool          # False if at capacity
  count -> int
  should_spill -> bool
  get_by_concept(concept) -> List[FactReference]
  get_by_context(ctx_id) -> List[FactReference]
  get_by_unit(unit_id) -> List[FactReference]
  get_by_concept_and_context(concept, ctx_id) -> List[FactReference]
  get_duplicate_groups() -> Dict[Tuple, List[FactReference]]
  iter_all() -> Iterator[FactReference]
  iter_batches(batch_size: int) -> Iterator[List[FactReference]]

INTERNAL INDEXES (store int indices, not copies):
  _facts: List[FactReference]
  _by_concept: Dict[QName, List[int]]
  _by_context: Dict[ContextID, List[int]]
  _by_unit:    Dict[UnitID, List[int]]
  _by_cc:      Dict[Tuple[QName,ContextID], List[int]]

MEMORY MATH:
  Per fact: ~264 bytes (200 obj + 64 index entries)
  500 MB budget → ~1.89M facts in memory
  Spill at 10M facts or 500 MB used, whichever comes first
```

### 5C — `src/core/parser/streaming/disk_spill.py`

```text
CLASS: DiskSpilledFactIndex
  Same interface as InMemoryFactIndex but backed by SQLite.

  __init__(self, db_path: Optional[str] = None)  # None → tempfile
  add(ref) -> bool
  add_batch(refs: List[FactReference]) -> None     # batch of 10K
  + all query methods from InMemoryFactIndex
  close() -> None
  __del__() → cleanup

SQLITE SCHEMA:
  CREATE TABLE facts (
    idx INTEGER PRIMARY KEY,
    concept TEXT NOT NULL,
    context_ref TEXT NOT NULL,
    unit_ref TEXT,
    byte_offset INTEGER NOT NULL,
    value_length INTEGER NOT NULL,
    is_numeric INTEGER NOT NULL,
    is_nil INTEGER NOT NULL,
    decimals TEXT,
    precision TEXT,
    fact_id TEXT,
    source_line INTEGER NOT NULL,
    period_type TEXT,
    balance_type TEXT
  );
  CREATE INDEX idx_concept ON facts(concept);
  CREATE INDEX idx_context ON facts(context_ref);
  CREATE INDEX idx_unit ON facts(unit_ref);
  CREATE INDEX idx_cc ON facts(concept, context_ref);
  CREATE INDEX idx_offset ON facts(byte_offset);

SETTINGS: WAL journal mode, batch insert 10K rows per transaction,
  parameterized queries only.

PERFORMANCE:
  Insert: ~500K facts/sec   Lookup: ~100K queries/sec
```

### 5D — `src/core/parser/streaming/fact_store.py`

```text
CLASS: FactStore
  Unified interface. Transparently switches InMemory → DiskSpilled.

  __init__(self, budget: MemoryBudget, config: PipelineConfig)
  storage_mode -> SpillState
  count -> int
  add(ref: FactReference) -> None
    # if in-memory and should_spill:
    #   create DiskSpilledFactIndex
    #   transfer all in-memory facts via add_batch
    #   free InMemoryFactIndex
    #   switch mode
  + all query methods (delegates to active backend)
  iter_batches(batch_size: int) -> Iterator[List[FactReference]]
  close() -> None
```

### 5E — `src/core/parser/streaming/mmap_reader.py`

```text
CLASS: MMapReader
  For SSD storage. Memory-mapped random access.

  __init__(self, file_path: str)
  read_value(byte_offset: int, value_length: int) -> bytes
  read_values_batch(locations: List[Tuple[int,int]]) -> List[bytes]
    # sorts by offset for page-cache friendliness
  close() -> None

  @staticmethod
  is_ssd(file_path: str) -> bool
    # Linux: /sys/block/{dev}/queue/rotational == 0
    # macOS: diskutil info
    # Windows: Win32_DiskDrive MediaType
    # Fallback: assume SSD

IMPLEMENTATION: Python mmap module, ACCESS_READ, 64-bit offsets.
```

### 5F — `src/core/parser/streaming/chunked_reader.py`

```text
CLASS: ChunkedReader
  For HDD / network storage. Sequential I/O.

  __init__(self, file_path: str, chunk_size: int = 64 MB)
  read_values(locations: List[Tuple[int,int]]) -> Dict[int, bytes]
    # 1. Sort locations by offset
    # 2. Read in chunk_size blocks sequentially
    # 3. Extract values as chunk passes over their offsets
    # 4. Handle values spanning chunk boundaries
  close() -> None

HDD BENEFIT: Converts random I/O (~5 MB/s) to sequential (~150 MB/s) = 30× faster.
```

### 5G — `src/core/parser/streaming/sax_handler.py`

```text
CLASS: XBRLSAXHandler
  SAX/iterparse handler for XBRL instance XML > 100 MB.

  __init__(self, file_path: str, fact_store: FactStore, budget: MemoryBudget)
  parse() -> StreamingParseResult

ALGORITHM (Pass 1 — structure scan):
  Use lxml.etree.iterparse(file, events=("start","end"), huge_tree=True)

  ON "end" EVENT for each element:
    if element is {NS_XBRLI}context  → _handle_context(elem) → store in dict
    if element is {NS_XBRLI}unit     → _handle_unit(elem) → store in dict
    if element is {NS_LINK}schemaRef → _handle_schema_ref(elem)
    if element is {NS_LINK}linkbaseRef → _handle_linkbase_ref(elem)
    if element is a FACT (not context/unit/link/*):
      → _handle_fact_start(elem, byte_offset)
      → Create FactReference (concept, contextRef, unitRef, decimals,
        byte_offset, value_length, is_nil, source_line)
      → fact_store.add(ref)
      → Do NOT store elem.text (the value)

  CRITICAL MEMORY CLEANUP after every element:
    elem.clear()
    while elem.getprevious() is not None:
        del elem.getparent()[0]

  Without this cleanup, lxml accumulates the full tree even with iterparse!

BYTE OFFSET TRACKING:
  Wrap the file object in a CountingFileWrapper that tracks read position.
  At each "start" event, record wrapper.position as approximate byte offset.

DATACLASS: StreamingParseResult
  namespaces: Dict[str, str]
  schema_refs: List[SchemaRef]
  linkbase_refs: List[LinkbaseRef]
  contexts: Dict[str, Context]
  units: Dict[str, Unit]
  fact_store: FactStore
  parse_errors: List[ValidationMessage]
  total_facts: int
  total_bytes_scanned: int
  elapsed_seconds: float
  spill_occurred: bool
```

### 5H — `src/core/parser/streaming/sax_ixbrl_handler.py`

```text
CLASS: IXBRLStreamingHandler
  For large iXBRL HTML > 100 MB (rare but possible).

  Strategy:
    If XHTML (well-formed XML) → use iterparse like sax_handler
    If HTML5 → use incremental lxml.html parser with target mode

  Must handle:
    ix:header extraction (contexts, units, schemaRefs)
    ix:nonFraction / ix:nonNumeric fact extraction
    Continuation chain ID tracking (not content — resolve later)
    Transform info capture (format attribute)
    Store short display values (< 100 chars) in FactReference
```

### 5I — `src/core/parser/streaming/json_streamer.py`

```text
CLASS: XBRLJSONStreamer
  Uses ijson for streaming XBRL-JSON.
  Threshold: 50 MB.

  parse() -> StreamingParseResult
    - ijson.parse(file) → event stream
    - "documentInfo" → parse fully (small)
    - "facts" → extract each fact incrementally → FactStore
```

### 5J — `src/core/parser/streaming/csv_streamer.py`

```text
CLASS: XBRLCSVStreamer
  Uses polars.scan_csv (lazy) for XBRL-CSV.
  Threshold: 200 MB.

  parse() -> StreamingParseResult
    - Parse metadata.json fully (always small)
    - polars.scan_csv → lazy frame
    - Process in 100K-row batches
    - Build FactReferences from each batch → FactStore
```

---

## 6. DOM PARSERS (small files)

### 6A — `src/core/parser/xml_parser.py`

```text
CLASS: XMLParser
  __init__(config: Optional[PipelineConfig])
  parse(file_path: str) -> RawXBRLDocument
  parse_bytes(data: bytes) -> RawXBRLDocument

SECURITY:
  parser = etree.XMLParser(
    resolve_entities=False, no_network=True,
    dtd_validation=False, load_dtd=False, huge_tree=False
  )

ERROR CODES: PARSE-0001..0007
```

### 6B — `src/core/parser/ixbrl_parser.py`

```text
CLASS: IXBRLParser
  parse(file_path: str) -> InlineXBRLDocument
  to_xbrl_instance(doc) -> RawXBRLDocument

PHASES:
  1. HTML parse (lxml.html)
  2. ix:header extraction (contexts, units, schemaRefs)
  3. Body walk for ix:nonFraction, ix:nonNumeric, ix:fraction, ix:tuple
  4. Transform application (format attr → TransformRegistry)
  5. Continuation chain resolution
  6. Hidden fact classification

TRANSFORMS:
  Final XBRL value = transform(displayValue) × 10^scale × (-1 if sign="-")

CONTINUATION ALGORITHM:
  Follow fact.continuedAt → next continuation → … → end
  Detect broken chains (IXBRL-0002) and circular chains.
  Concatenate content, removing ix:exclude regions.

ERROR CODES: IXBRL-0001..0020
```

### 6C — `src/core/parser/transform_registry.py`

```text
CLASS: TransformRegistry
  __init__(registry_paths: List[str])    # config/transforms/*.json
  get_transform(format_qname: str) -> Optional[Callable]
  apply_transform(format_qname, display_value) -> Tuple[str, Optional[str]]

MINIMUM TRANSFORMS TO IMPLEMENT:
  ixt:numdotdecimal, ixt:numcommadecimal, ixt:zerodash, ixt:nocontent,
  ixt:fixedzero, ixt:booleanfalse, ixt:booleantrue,
  ixt:dateslashus, ixt:dateslasheu, ixt:datedoteu,
  ixt:datelongus, ixt:datelonguk, ixt:durday, ixt:durmonth, ixt:duryear,
  ixt-sec:duryear, ixt-sec:durmonth, ixt-sec:numwordsen
```

---

## 7. TAXONOMY RESOLUTION — `src/core/taxonomy/resolver.py`

```text
CLASS: TaxonomyResolver
  __init__(cache_dir, remote_timeout, catalog_files)
  resolve(entry_points: List[str]) -> TaxonomyModel
  load_package(zip_path: str) -> TaxonomyPackage

DTS ALGORITHM:
  visited = set(); queue = deque(entry_points)
  while queue:
    url = queue.popleft()
    if url in visited: continue
    visited.add(url)
    resolved = catalog.resolve(url)
    content = cache.get_or_fetch(resolved)
    if .xsd: parse schema → extract concepts, role/arcrole types
             for each import/include/linkbaseRef → queue.append
    if .xml: parse linkbase → classify → store in TaxonomyModel

CONCEPT EXTRACTION:
  For each <element> with substitutionGroup deriving from xbrli:item/tuple:
    QName, type, period_type, balance_type, abstract, nillable,
    is_numeric, is_textblock, is_enum

LINKBASE PARSING:
  Extract arcs: from, to (via locator resolution), arcrole, order,
  weight (calc), priority, use, preferredLabel (pres).
  Apply prohibition/override (higher priority wins).

CACHE — 3 LEVELS:
  L1 HOT:  .tax_cache/_parsed/{hash}.msgpack  (~200ms load)
  L2 WARM: .tax_cache/{name}/{ver}/*.xsd,xml   (~15s parse)
  L3 COLD: HTTP fetch from CDN                  (~30-60s download)
  Key: SHA256 of taxonomy package content.

ERROR CODES: DTS-0001..0005
```

---

## 8. MODEL — `src/core/model/xbrl_model.py`

```text
DATACLASSES TO IMPLEMENT (all with full type hints):

  Period          — period_type, instant, start_date, end_date
  EntityIdentifier — scheme, identifier
  DimensionMember — dimension, member, is_typed, typed_value
  Context         — id, entity, period, segment_dims, scenario_dims
                    properties: dimension_key, all_dimensions
                    methods: is_dimensional_equivalent(other)
  UnitMeasure     — namespace, local_name
  Unit            — id, measures, divide_measures
                    properties: is_divide, is_monetary, is_pure
  Fact            — id, concept, context_ref, context, unit_ref, unit,
                    value, numeric_value (Decimal!), is_nil, is_numeric,
                    decimals, precision, language, source_line, source_file,
                    is_hidden, footnote_refs
                    properties: duplicate_key (Tuple), rounded_value (Decimal)
  Footnote        — id, role, language, content, fact_refs
  ValidationMessage — code, severity, message, concept, context_id,
                       fact_id, location, source_file, source_line,
                       details, fix_suggestion, rule_source
  ConceptDefinition — qname, namespace, local_name, data_type,
                       period_type, balance_type, abstract, nillable,
                       substitution_group, type_is_numeric,
                       type_is_textblock, type_is_enum, labels, references
  ArcModel        — arc_type, arcrole, from_concept, to_concept,
                     order, weight, priority, use, preferred_label
  LinkbaseModel   — linkbase_type, role_uri, arcs
  HypercubeModel  — qname, dimensions, is_closed, context_element,
                     domain_members
  TaxonomyModel   — concepts, role_types, arcrole_types,
                     calc/pres/def/label/ref linkbases,
                     namespaces, dimension_defaults, hypercubes

  XBRLInstance     — file_path, format_type, contexts, units, facts,
                     footnotes, taxonomy, schema_refs, namespaces,
                     facts_by_concept, facts_by_context, facts_by_unit,
                     dimensional_facts
                     + Optional[FactStore] for large-file mode
                     + Optional[MMapReader|ChunkedReader] for value access

CRITICAL — DUAL MODE:
  XBRLInstance MUST transparently support:
    Mode 1 (small): facts in List[Fact], indexes as Dict[str,List[Fact]]
    Mode 2 (large): facts in FactStore, values loaded on-demand

  get_facts_by_concept(concept) must work in BOTH modes:
    if _mode == "memory": return self._by_concept.get(concept, [])
    else: return self._hydrate_facts(self.fact_store.get_by_concept(concept))

  _hydrate_facts converts FactReferences → Fact objects by reading
  values from MMapReader/ChunkedReader. LRU cache (10K facts).
```

### Model Builders

```text
src/core/model/builder.py — DOM model builder
  ModelBuilder.build(raw_doc, taxonomy) -> XBRLInstance
  ModelBuilder.build_from_inline(inline_doc, taxonomy) -> XBRLInstance

src/core/model/builder_streaming.py — streaming model builder
  StreamingModelBuilder.build(parse_result, taxonomy, source_file) -> XBRLInstance
    Creates store-backed XBRLInstance.
    Classifies FactReferences using taxonomy (set period_type, balance_type).
    Sets up value reader (MMapReader if SSD, ChunkedReader if HDD).

src/core/model/merge.py — multi-document merger
  ModelMerger.merge(instances: List[XBRLInstance]) -> XBRLInstance
    Same entity required. Context/Unit ID collision checks.
    Fact ID uniqueness. Cross-doc continuation chains.
  ERROR CODES: MERGE-0001..0005
```

---

## 9. VALIDATION PIPELINE — `src/validator/pipeline.py`

```text
DATACLASS: PipelineConfig
  input_files, taxonomy_packages, catalog_files,
  regulator (Optional[str]),
  enable_calculation, enable_dimensions, enable_formula, enable_table,
  enable_ai, enable_cross_document,
  large_file_threshold_bytes, memory_budget_bytes,
  fact_index_spill_threshold, max_file_size_bytes, io_chunk_size,
  treat_warnings_as_errors, max_errors,
  parallel_workers, taxonomy_cache_dir, temp_dir,
  custom_rule_paths, xule_rule_sets,
  output_format, output_file

CLASS: ValidationPipeline
  STAGES (in order):
    1. parse           — detect format, parse (DOM or streaming)
    2. dts_resolve     — resolve taxonomy via TaxonomyResolver
    3. model_build     — build XBRLInstance (DOM or streaming builder)
    4. spec_validate   — XBRL 2.1, dims, calc, inline, table, label, pres
                         (run sub-validators IN PARALLEL via ProcessPoolExecutor)
    5. formula_eval    — formula linkbase assertions
    6. regulator_rules — load profile, run regulator validators
    7. ai_reasoning    — fix suggestions, business rules, tagging analysis
    8. self_check      — dedup, false positive removal, severity verify, sort
    9. report          — format output as JSON/SARIF/HTML/CSV

  run() -> PipelineResult
    Each stage catches exceptions internally.
    Continues to next stage unless critical (can't build model at all).
    Tracks memory via MemoryBudget. Logs stage timing.

DATACLASS: PipelineResult
  success, messages, error_count, warning_count, info_count,
  facts_validated, concepts_used, contexts_count, elapsed_seconds,
  stages_completed, memory_peak_bytes, spill_occurred,
  files_processed, parsing_strategy, instance (optional)
  to_json(), to_sarif(), to_html(), to_csv()
```

---

## 10. SPECIFICATION VALIDATORS

### Base — `src/validator/base.py`

```text
CLASS: BaseValidator (ABC)
  __init__(self, instance: XBRLInstance)
  validate() -> List[ValidationMessage]  # abstract
  error(code, message, **kwargs), warning(...), info(...), inconsistency(...)
```

### XBRL 2.1 — `src/validator/spec/xbrl21.py`

```text
25 checks. Error codes XBRL21-0001..0025.
Key checks:
  0001 Missing entity identifier        0002 Missing period
  0003 Invalid instant date             0004 startDate > endDate
  0005 Duplicate context ID             0006 Duplicate unit ID
  0007 Unit missing measure             0008 Fact → invalid context
  0009 Numeric fact missing unit        0010 Missing decimals/precision
  0011 Both decimals AND precision      0012 Nil fact has value
  0013 Concept not in taxonomy          0014 Type mismatch (numeric/unit)
  0015 Period type mismatch             0016 Monetary needs ISO 4217
  0017 Shares needs xbrli:shares        0018 Pure needs xbrli:pure
  0019 Invalid identifier scheme URI    0020 Conflicting duplicate facts
  0021 Tuple ordering violation         0022 Missing schemaRef
  0023 Missing xml:lang for string      0024 Invalid footnote role
  0025 Missing footnote language

LARGE-FILE: Use model query interface.
For duplicates: FactStore.get_duplicate_groups() (SQL GROUP BY in disk mode).
For iteration: iter_batches(10000) to avoid loading all facts.
```

### Calculation — `src/validator/spec/calculation.py`

```text
6 checks. Error codes CALC-0001..0006.
  0001 Zero weight           0002 Summation inconsistency
  0003 Rounding exceeded     0004 Missing contributing fact
  0005 Cross-unit calc       0006 Circular calc

TOLERANCE (per XBRL 2.1 §5.2.5.2):
  child_tol = 0.5 × 10^(-child_decimals) per child
  parent_tol = 0.5 × 10^(-parent_decimals)
  total_tol = parent_tol + sum(child_tolerances)
  ALL in Decimal arithmetic.

LARGE-FILE VALUE LOADING:
  1. Walk calc linkbase → identify parent/child concept sets
  2. For each parent fact ref → load value via reader
  3. Find child refs with same context+unit → load values
  4. Pre-sort all needed offsets for sequential I/O
  5. Release values from LRU cache when done
```

### Dimensions — `src/validator/spec/dimensions.py`

```text
10 checks. Error codes DIM-0001..0010.
  0001 Member not in domain        0002 Typed dim value invalid
  0003 Hypercube violated          0004 Undeclared dimension
  0005 Default member explicit     0006 Segment/scenario wrong
  0007 Multiple defaults           0008 has-hypercube violated
  0009 Concept not dim-valid       0010 all/notAll arc violation

OPTIMIZATION: Pre-compute concept → applicable hypercubes mapping.
Context data always in memory.
```

### Other spec validators

```text
src/validator/spec/formula.py    — FORMULA-0001..0006 (XPath subset)
src/validator/spec/inline.py     — IXBRL-0001..0020
src/validator/spec/table.py      — TBL-0001..0005
src/validator/spec/label.py      — LBL-0001..0005
src/validator/spec/presentation.py — PRES-0001..0005
src/validator/spec/definition.py — DEF-0001..0005
```

---

## 11. REGULATOR RULE INJECTION

### Profile Loader — `src/plugin/profile_loader.py`

```text
CLASS: ProfileLoader
  load(profile_id: str) -> RegulatorProfile
    1. Read config/profiles/index.yaml → find profile dir
    2. Load profile.yaml → metadata, rule_source list
    3. For each source:
       .yaml → RuleCompiler.compile_file()
       .py   → importlib dynamic import
       .xule → XULE engine parse
    4. Return RegulatorProfile(validators=[...])

  auto_detect(instance: XBRLInstance) -> Optional[str]
    Check taxonomy namespace:
      fasb.org/us-gaap → "efm"
      esma.europa.eu   → "esef"
      ferc.gov         → "ferc"
      xbrl.frc.org.uk  → "hmrc"
      cipc.co.za       → "cipc"
      mca.gov.in       → "mca"
    Check entity scheme:
      sec.gov/CIK → "efm"
      iso/17442 (LEI) → "esef"
```

### Rule Compiler — `src/plugin/rule_compiler.py`

```text
CLASS: RuleCompiler
  compile_file(yaml_path: str) -> List[BaseValidator]

YAML RULE TYPES:
  mandatory_element  → concept must exist with value
  value_constraint   → value matches pattern/range/enum
  cross_concept      → if X exists then Y must exist/equal
  naming_convention  → extension names match regex
  structural         → schema_ref count, file naming
  negation           → expected sign for balance type
```

### Regulator Modules

```text
src/validator/regulator/efm.py
  Rules: EFM-6.5.3 (CIK scheme), EFM-6.5.4 (CIK format 10-digit),
         EFM-6.5.20 (mandatory DEI), EFM-6.5.27 (period end date ±30 days),
         EFM-6.5.40 (CamelCase naming), EFM-6.5.42 (extension usage),
         EFM-6.6.1 (one schemaRef), EFM-6.12.x (inline rules),
         EFM-NEGVAL (negation detection)
  Mix: 70% YAML + 30% Python

src/validator/regulator/esef.py + esef_anchoring.py + esef_package.py
  Rules: ESEF-2.x (ZIP package), ESEF-3.x (anchoring wider-narrower),
         ESEF-4.x (mandatory IFRS tags, block tagging)
  Anchoring: graph BFS from extension concept to base concept

src/validator/regulator/ferc_xule.py
  Loads .xule files → XULE engine. 100% XULE-driven.

src/validator/regulator/hmrc.py
  Mandatory CT600 elements, GBP currency, Companies House number format.

src/validator/regulator/cipc.py
  ZAR currency, CIPC registration number, mandatory line items.

src/validator/regulator/mca.py
  CIN format (21-char), INR currency, DIN for directors.
```

---

## 12. XULE ENGINE — `src/xule/`

```text
FILES: lexer.py, parser.py, compiler.py, evaluator.py,
       query_planner.py, ast_nodes.py, builtins.py

LANGUAGE FEATURES TO SUPPORT:
  Variable binding:     $var = {@concept = QName @period = ... @dim:D = M}
  Expressions:          +, -, *, /, ==, !=, <, >, <=, >=, and, or, not
  Aggregation:          sum(), count(), min(), max(), avg()
  Existence:            exists(), not_exists()
  Tolerance:            tolerance_for_decimals($a, $b, n)
  Properties:           $fact.concept, .value, .period, .unit, .decimals
  Navigation:           $fact.dimension(DimQName)
  Output:               output rule-name / severity / message

QUERY PLANNER:
  @concept filter → facts_by_concept index (O(1))
  @concept + @context → compound index (O(1))
  No @concept → full scan (warn: expensive)
  For disk-spilled: push filters into SQL WHERE clause.

PERFORMANCE TARGET:
  500 rules × 5M facts → < 60 seconds (with query planning)
  Without planning → hours (unacceptable)
```

---

## 13. AI LAYER — `src/ai/`

```text
ALL AI outputs tagged source="AI". Disabled with --no-ai.

fix_suggester.py
  Template-based for common errors (fast, deterministic).
  LLM fallback for rare errors (optional, non-deterministic).

business_rules.py
  Assets = Liabilities + Equity
  Net Income = Revenue - Expenses
  Cash flow identity checks
  Tagged as WARNING, never ERROR.

cross_doc.py
  Compare same concepts across multi-doc filings.
  Prior period consistency.
  Quarterly → annual summation.

tagging_analyzer.py
  Over-tagging: duplicate semantic tagging.
  Under-tagging: untagged financial content near existing tags.
  Wrong concept: broader concept when narrower exists.
```

---

## 14. API — `src/api/`

```text
routes.py (FastAPI):
  POST /api/v1/validate          — async, returns job_id
  GET  /api/v1/validate/{job_id} — poll for results
  POST /api/v1/validate/sync     — sync for small files (<5MB)
  GET  /api/v1/profiles          — list regulator profiles
  GET  /api/v1/taxonomies        — list cached taxonomies
  POST /api/v1/taxonomies/load   — pre-load taxonomy package
  GET  /health                   — health check
  WS   /api/v1/validate/{job_id}/stream — progress websocket

worker.py (Celery):
  validate_filing task — runs ValidationPipeline in worker process

schemas.py (Pydantic):
  ValidationRequest, ValidationResponse, ErrorDetail
```

---

## 15. CLI — `src/cli/main.py`

```text
Typer application. Entry point: xbrl-validate

OPTIONS:
  files...                    Positional: files to validate
  --profile, -p               Regulator profile
  --output, -o                Output file path
  --format, -f                json|sarif|html|csv (default: json)
  --taxonomy, -t              Taxonomy package path(s)
  --catalog, -c               XML catalog file(s)
  --no-ai                     Disable AI reasoning
  --no-formula                Disable formula validation
  --rules                     Custom YAML rule file(s)
  --xule                      XULE rule set path(s)
  --strict                    Warnings → errors
  --max-errors                Stop after N errors
  --memory-budget             Memory budget in MB (default: 4096)
  --large-file-threshold      Streaming threshold in MB (default: 100)
  --verbose, -v               Verbose logging
  --cache-dir                 Taxonomy cache directory
  --workers                   Parallel worker count

EXIT CODES: 0 = success, 1 = validation errors found, 2 = system error
```

---

## 16. REPORT — `src/report/`

```text
generator.py — orchestrator, delegates to format-specific reporters

json_report.py:
  {
    "summary": "...",
    "errors": [{ "code", "severity", "message", "concept",
                 "location", "details", "fix_suggestion" }],
    "warnings": [...],
    "fix_suggestions": ["..."],
    "metadata": { "files", "facts_validated", "elapsed_seconds",
                  "memory_peak_mb", "spill_occurred", "strategy" }
  }

sarif_report.py — SARIF 2.1.0 format

html_report.py — Jinja2 template rendering (report.html.j2)
  Sections: summary, error table (sortable), fix suggestions,
            filing metadata, performance stats

csv_report.py — flat CSV: code, severity, message, concept, location, fix
```

---

## 17. DOCKER & DEPLOYMENT

```text
Dockerfile:
  FROM python:3.12-slim
  System deps: libxml2-dev libxslt1-dev gcc
  pip install requirements.txt
  COPY src/ config/ plugins/
  EXPOSE 8080
  HEALTHCHECK curl -f http://localhost:8080/health
  CMD uvicorn src.api.routes:app --host 0.0.0.0 --port 8080 --workers 4

Dockerfile.worker:
  Same base.
  CMD celery -A src.api.worker worker --loglevel=info --concurrency=4

docker-compose.yml:
  api (port 8080) + worker (4 replicas) + redis + postgres
  Shared volume: taxonomy_cache
```

---

## 18. TEST REQUIREMENTS

```text
CATEGORIES:

unit/         — every module has matching test file
                every validation rule has ≥3 tests (valid, invalid, edge)
streaming/    — memory_budget enforcement, fact_index operations,
                disk_spill transitions, mmap/chunked readers
large_file/   — 200MB+ XML, 200MB+ iXBRL, 100MB+ JSON, 500MB+ CSV
                memory budget enforcement under load
                disk spill round-trip (write+query correctness)
                mmap random access correctness
                1M+ fact validation timing (<60s target)
                synthetic 5GB file end-to-end
integration/  — full pipeline per regulator profile
                multi-document merging
                API endpoint round-trips
                CLI invocation + exit codes
conformance/  — XBRL Int'l official conformance suites (downloaded)
e2e/          — real SEC/ESEF/FERC filings (downloaded)

LARGE FILE TEST GENERATORS (tests/large_file/generators/):
  xbrl_generator.py  — Generate valid XBRL with N facts, M contexts
  ixbrl_generator.py — Generate valid iXBRL with N facts
  fact_generator.py  — Generate N FactReferences with random data

  Generator params:
    num_facts: int        — 1K to 50M
    num_contexts: int     — 1 to 10K
    num_units: int        — 1 to 100
    num_dimensions: int   — 0 to 20
    target_file_size_mb: int — generate until file reaches target size
    include_calc_tree: bool  — embed calculation relationships
    include_inline: bool     — wrap in iXBRL HTML

PERFORMANCE TARGETS (measured in tests):
  Small SEC 10-Q (5 MB)        < 10s
  Large SEC 10-K (50 MB)       < 30s
  ESEF annual (100 MB)         < 2min
  FERC Form 1 (500 MB)         < 10min
  FERC Form 1 (2 GB)           < 30min
  Extreme (5 GB)               < 90min
  Taxonomy cold load           < 20s
  Taxonomy warm load           < 1s
```

---

## 19. ERROR CODE REGISTRY — `config/error_codes.yaml`

```yaml
# Agent MUST generate the FULL registry. Partial listing for structure:

PARSE-0001: { severity: error, source: parser, spec: "XML 1.0", desc: "Malformed XML" }
PARSE-0002: { severity: error, source: parser, spec: "XML 1.0", desc: "Missing root element" }
PARSE-0003: { severity: error, source: parser, spec: "XML NS 1.0", desc: "Namespace conflict" }
PARSE-0004: { severity: error, source: parser, spec: "XML 1.0", desc: "Encoding error" }
PARSE-0005: { severity: error, source: parser, spec: "Security", desc: "XXE attack detected" }
PARSE-0006: { severity: error, source: parser, spec: "Internal", desc: "File too large for DOM" }
PARSE-0007: { severity: error, source: parser, spec: "XBRL 2.1 §4.2", desc: "Missing schemaRef" }

DTS-0001: { severity: error, source: taxonomy, spec: "XBRL 2.1 §3", desc: "Unresolvable schema" }
DTS-0002: { severity: error, source: taxonomy, spec: "XBRL 2.1 §3", desc: "Circular import" }
DTS-0003: { severity: error, source: taxonomy, spec: "Tax Pkg 1.0", desc: "Invalid package" }
DTS-0004: { severity: warning, source: taxonomy, spec: "XML Catalog", desc: "Catalog mapping failure" }
DTS-0005: { severity: error, source: taxonomy, spec: "Network", desc: "Fetch timeout" }

MODEL-0001: { severity: error, source: model, spec: "XBRL 2.1 §4.7", desc: "Invalid context ref" }
MODEL-0002: { severity: error, source: model, spec: "XBRL 2.1 §4.8", desc: "Invalid unit ref" }
MODEL-0003: { severity: error, source: model, spec: "XBRL 2.1 §4.6", desc: "Unknown concept" }
MODEL-0004: { severity: warning, source: model, spec: "XBRL 2.1", desc: "Orphaned context" }
MODEL-0005: { severity: warning, source: model, spec: "XBRL 2.1", desc: "Orphaned unit" }

XBRL21-0001: { severity: error, source: spec, spec: "XBRL 2.1 §4.7.1", desc: "Missing entity ID" }
# ... through XBRL21-0025 (agent must generate all 25)

CALC-0001: { severity: error, source: spec, spec: "XBRL 2.1 §5.2.5", desc: "Zero weight" }
# ... through CALC-0006

DIM-0001: { severity: error, source: spec, spec: "Dims 1.0 §2", desc: "Member not in domain" }
# ... through DIM-0010

IXBRL-0001: { severity: error, source: spec, spec: "iXBRL 1.1 §4", desc: "Missing ix:header" }
# ... through IXBRL-0020

FORMULA-0001: { severity: error, source: spec, spec: "Formula 1.0", desc: "Assertion unsatisfied" }
# ... through FORMULA-0006

MERGE-0001: { severity: error, source: model, spec: "Internal", desc: "Entity ID mismatch" }
# ... through MERGE-0005

# Regulator codes: EFM-*, ESEF-*, XULE-*, HMRC-*, CIPC-*, MCA-*
# AI codes: AI-0001..0010
```

---

## 20. EXECUTION ORDER FOR AGENT

```text
The agent SHOULD build modules in this order to satisfy dependencies:

PHASE 1 — Foundation (no deps on other project modules)
  1. src/core/constants.py
  2. src/core/types.py
  3. src/core/exceptions.py
  4. src/utils/*.py
  5. config/error_codes.yaml
  6. config/default.yaml

PHASE 2 — Streaming infrastructure
  7. src/core/parser/streaming/memory_budget.py
  8. src/core/parser/streaming/fact_index.py
  9. src/core/parser/streaming/disk_spill.py
  10. src/core/parser/streaming/fact_store.py
  11. src/core/parser/streaming/mmap_reader.py
  12. src/core/parser/streaming/chunked_reader.py

PHASE 3 — Parsers
  13. src/core/parser/format_detector.py
  14. src/core/parser/transform_registry.py
  15. src/core/parser/xml_parser.py
  16. src/core/parser/ixbrl_parser.py
  17. src/core/parser/json_parser.py
  18. src/core/parser/csv_parser.py
  19. src/core/parser/streaming/sax_handler.py
  20. src/core/parser/streaming/sax_ixbrl_handler.py
  21. src/core/parser/streaming/json_streamer.py
  22. src/core/parser/streaming/csv_streamer.py

PHASE 4 — Taxonomy
  23. src/core/taxonomy/catalog.py
  24. src/core/taxonomy/cache.py
  25. src/core/taxonomy/package.py
  26. src/core/taxonomy/resolver.py
  27. src/core/taxonomy/concept_index.py

PHASE 5 — Model
  28. src/core/model/xbrl_model.py
  29. src/core/model/indexes.py
  30. src/core/model/builder.py
  31. src/core/model/builder_streaming.py
  32. src/core/model/merge.py

PHASE 6 — Validators
  33. src/validator/message.py
  34. src/validator/error_catalog.py
  35. src/validator/base.py
  36. src/validator/spec/xbrl21.py
  37. src/validator/spec/dimensions.py
  38. src/validator/spec/calculation.py
  39. src/validator/spec/inline.py
  40. src/validator/spec/formula.py
  41. src/validator/spec/table.py
  42. src/validator/spec/label.py
  43. src/validator/spec/presentation.py
  44. src/validator/spec/definition.py
  45. src/validator/self_check.py

PHASE 7 — XULE engine
  46. src/xule/ast_nodes.py
  47. src/xule/builtins.py
  48. src/xule/lexer.py
  49. src/xule/parser.py
  50. src/xule/compiler.py
  51. src/xule/query_planner.py
  52. src/xule/evaluator.py

PHASE 8 — Plugin system + regulators
  53. src/plugin/base.py
  54. src/plugin/rule_compiler.py
  55. src/plugin/profile_loader.py
  56. src/plugin/loader.py
  57. config/profiles/**/*.yaml
  58. src/validator/regulator/efm.py
  59. src/validator/regulator/esef.py
  60. src/validator/regulator/esef_anchoring.py
  61. src/validator/regulator/esef_package.py
  62. src/validator/regulator/ferc_xule.py
  63. src/validator/regulator/hmrc.py
  64. src/validator/regulator/cipc.py
  65. src/validator/regulator/mca.py
  66. src/validator/regulator/custom.py

PHASE 9 — AI layer
  67. src/ai/fix_suggester.py
  68. src/ai/business_rules.py
  69. src/ai/cross_doc.py
  70. src/ai/tagging_analyzer.py

PHASE 10 — Pipeline + API + CLI + Reports
  71. src/validator/pipeline_config.py
  72. src/validator/pipeline.py
  73. src/report/*.py + templates
  74. src/api/*.py
  75. src/cli/*.py

PHASE 11 — Tests (parallel with phases above)
  76-145. All test files

PHASE 12 — Infrastructure
  146. pyproject.toml, Makefile, Dockerfiles, docker-compose.yml,
       README.md, LICENSE, .gitignore, .env.example, scripts/*
```

---

## 21. ACCEPTANCE CRITERIA

```text
The agent's output is ACCEPTED when ALL of these pass:

□ Every file in Section 2 tree exists and is non-empty
□ `pip install -e ".[dev]"` succeeds
□ `mypy src/` passes with zero errors
□ `ruff check src/` passes with zero errors
□ `pytest tests/unit/ -v` — all pass
□ `pytest tests/streaming/ -v` — all pass
□ `xbrl-validate --help` prints usage
□ `xbrl-validate tests/fixtures/valid/simple_instance.xml` → exit 0, zero errors
□ `xbrl-validate tests/fixtures/invalid/period_mismatch.xml` → exit 1, XBRL21-0015
□ `xbrl-validate tests/fixtures/invalid/calc_inconsistency.xml` → exit 1, CALC-0002
□ `xbrl-validate tests/fixtures/valid/simple_inline.html` → exit 0
□ POST /api/v1/validate with simple_instance.xml → 200 + job_id
□ Docker build succeeds
□ Memory budget test: synthetic 150 MB file validates in < 2 min, peak RSS < 2 GB
□ Disk spill test: synthetic 15M-fact file validates without OOM
□ All error codes in output match entries in config/error_codes.yaml
□ No float usage for XBRL numeric values (grep -r "float(" src/ returns 0 hits
  in fact/value/calculation code paths)
□ No regulator imports in src/core/ or src/validator/spec/
```