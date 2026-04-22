"""FastAPI REST API for XBRL validation."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

app = FastAPI(
    title="XBRL Validator API",
    version="1.0.0",
    description="Production-grade XBRL/iXBRL validation engine",
)


class ValidationMessageResponse(BaseModel):
    """A single validation message in the API response."""

    code: str
    severity: str
    message: str
    spec_ref: str | None = None
    file_path: str | None = None
    line: int | None = None
    column: int | None = None
    fix_suggestion: str | None = None


class ValidationResult(BaseModel):
    """Top-level validation result returned by the API."""

    file_name: str
    input_format: str
    fact_count: int
    error_count: int
    warning_count: int
    messages: list[ValidationMessageResponse]
    valid: bool


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/v1/validate", response_model=ValidationResult)
async def validate_file(
    file: UploadFile = File(...),
    regulator: str = "",
    output_format: str = "json",
) -> ValidationResult:
    """Validate an uploaded XBRL or iXBRL document."""
    if file.filename is None:
        raise HTTPException(status_code=400, detail="No filename provided")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    # Write to a temporary location within the working directory for parsing
    work_dir = Path(".xbrl_api_work")
    work_dir.mkdir(exist_ok=True)
    temp_path = work_dir / file.filename
    try:
        temp_path.write_bytes(content)
        result = _validate_file(temp_path, file.filename, regulator)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return result


def _validate_file(
    file_path: Path,
    file_name: str,
    regulator: str,
) -> ValidationResult:
    """Internal validation logic."""
    from src.core.parser.format_detector import FormatDetector
    from src.core.types import InputFormat, Severity

    # 1. Detect format
    detector = FormatDetector()
    detection = detector.detect(str(file_path))

    # 2. Parse
    instance = _parse_document(file_path, detection.format)
    if instance is None:
        raise ValueError(f"Unsupported format: {detection.format.value}")

    # 3. Validate
    from src.validator import XBRLValidator

    validator = XBRLValidator()
    messages = validator.validate(instance)

    # 4. Build response
    error_count = sum(1 for m in messages if m.severity == Severity.ERROR)
    warning_count = sum(1 for m in messages if m.severity == Severity.WARNING)

    return ValidationResult(
        file_name=file_name,
        input_format=detection.format.value,
        fact_count=instance.fact_count(),
        error_count=error_count,
        warning_count=warning_count,
        messages=[
            ValidationMessageResponse(
                code=m.code,
                severity=m.severity.value,
                message=m.message,
                spec_ref=m.spec_ref or None,
                file_path=m.file_path or None,
                line=m.line,
                column=m.column,
                fix_suggestion=m.fix_suggestion or None,
            )
            for m in messages
        ],
        valid=error_count == 0,
    )


def _parse_document(
    path: Path,
    input_format: Any,
) -> Any:
    """Parse a document into an XBRLInstance based on detected format."""
    from src.core.types import InputFormat

    if input_format in (InputFormat.IXBRL_HTML, InputFormat.IXBRL_XHTML):
        return _parse_ixbrl(path, input_format)
    if input_format == InputFormat.XBRL_XML:
        return _parse_xbrl_xml(path)
    return None


def _parse_ixbrl(path: Path, input_format: Any) -> Any:
    """Parse an iXBRL document into an XBRLInstance."""
    from src.core.model.fact import Fact
    from src.core.model.instance import XBRLInstance
    from src.core.parser.ixbrl_parser import IXBRLParser
    from src.core.types import FactType

    parser = IXBRLParser()
    doc = parser.parse(str(path))

    facts: list[Fact] = []
    for inline_fact in doc.facts:
        fact_type = FactType.NON_NUMERIC
        if inline_fact.element_type in ("nonFraction", "fraction"):
            fact_type = FactType.NUMERIC
        if inline_fact.is_nil:
            fact_type = FactType.NIL

        value: str | None = inline_fact.value if not inline_fact.is_nil else None
        decimals_val: int | None = None
        if inline_fact.decimals is not None:
            try:
                decimals_val = int(inline_fact.decimals)
            except ValueError:
                decimals_val = None

        precision_val: int | None = None
        if inline_fact.precision is not None:
            try:
                precision_val = int(inline_fact.precision)
            except ValueError:
                precision_val = None

        facts.append(
            Fact(
                fact_id=inline_fact.fact_id,
                concept_qname=inline_fact.name,
                context_ref=inline_fact.context_ref,
                unit_ref=inline_fact.unit_ref,
                value=value,
                fact_type=fact_type,
                decimals=decimals_val,
                precision=precision_val,
                is_nil=inline_fact.is_nil,
                language=None,
                source_line=inline_fact.source_line,
                source_file=str(path),
                format_code=inline_fact.format_qname,
                scale=inline_fact.scale,
                sign=inline_fact.sign,
            )
        )

    footnotes: list[dict[str, str]] = [
        {"id": fn.footnote_id, "content": fn.content}
        for fn in doc.footnotes
    ]

    return XBRLInstance(
        file_path=str(path),
        input_format=input_format,
        schema_refs=doc.schema_refs,
        contexts={},
        units={},
        facts=facts,
        footnotes=footnotes,
        namespace_map={k: v for k, v in doc.namespaces.items()},
    )


def _parse_xbrl_xml(path: Path) -> Any:
    """Parse a traditional XBRL XML instance into an XBRLInstance."""
    from decimal import Decimal, InvalidOperation

    from src.core.model.context import Context, Entity, Period
    from src.core.model.fact import Fact
    from src.core.model.instance import XBRLInstance
    from src.core.model.unit import Unit
    from src.core.parser.xml_parser import XMLParser
    from src.core.types import FactType, InputFormat, PeriodType

    parser = XMLParser()
    raw_doc = parser.parse(str(path))
    root = raw_doc.root

    ns_xbrli = "http://www.xbrl.org/2003/instance"
    ns_xsi = "http://www.w3.org/2001/XMLSchema-instance"

    # Parse contexts
    contexts: dict[str, Context] = {}
    for ctx_elem in root.iter(f"{{{ns_xbrli}}}context"):
        ctx_id = ctx_elem.get("id", "")
        entity_elem = ctx_elem.find(f"{{{ns_xbrli}}}entity")

        entity = Entity(scheme="", identifier="")
        if entity_elem is not None:
            ident_elem = entity_elem.find(f"{{{ns_xbrli}}}identifier")
            if ident_elem is not None:
                entity = Entity(
                    identifier=ident_elem.text or "",
                    scheme=ident_elem.get("scheme", ""),
                )

        period_elem = ctx_elem.find(f"{{{ns_xbrli}}}period")
        period = Period(period_type=PeriodType.INSTANT)
        if period_elem is not None:
            instant_el = period_elem.find(f"{{{ns_xbrli}}}instant")
            start_el = period_elem.find(f"{{{ns_xbrli}}}startDate")
            end_el = period_elem.find(f"{{{ns_xbrli}}}endDate")
            forever_el = period_elem.find(f"{{{ns_xbrli}}}forever")
            if instant_el is not None:
                period = Period(period_type=PeriodType.INSTANT)
            elif start_el is not None and end_el is not None:
                period = Period(period_type=PeriodType.DURATION)
            elif forever_el is not None:
                period = Period(period_type=PeriodType.FOREVER)

        contexts[ctx_id] = Context(context_id=ctx_id, entity=entity, period=period)

    # Parse units
    units: dict[str, Unit] = {}
    for unit_elem in root.iter(f"{{{ns_xbrli}}}unit"):
        unit_id = unit_elem.get("id", "")
        measures: list[str] = []
        for measure in unit_elem.iter(f"{{{ns_xbrli}}}measure"):
            if measure.text:
                measures.append(measure.text)
        units[unit_id] = Unit(unit_id=unit_id, numerators=tuple(measures))

    # Parse facts
    facts: list[Fact] = []
    skip_tags = {f"{{{ns_xbrli}}}context", f"{{{ns_xbrli}}}unit", f"{{{ns_xbrli}}}xbrl"}
    fact_counter = 0
    for elem in root:
        tag = elem.tag if isinstance(elem.tag, str) else ""
        if not tag or tag in skip_tags or tag.startswith(f"{{{ns_xbrli}}}"):
            continue

        fact_id = elem.get("id", f"_fact_{fact_counter}")
        context_ref = elem.get("contextRef", "")
        unit_ref = elem.get("unitRef")
        is_nil = elem.get(f"{{{ns_xsi}}}nil", "").lower() == "true"
        decimals_str = elem.get("decimals")
        precision_str = elem.get("precision")

        raw_value = elem.text or ""
        is_numeric = unit_ref is not None
        fact_type = FactType.NIL if is_nil else (FactType.NUMERIC if is_numeric else FactType.NON_NUMERIC)

        value: Decimal | str | None = None
        if is_nil:
            value = None
        elif is_numeric:
            try:
                value = Decimal(raw_value.strip())
            except InvalidOperation:
                value = raw_value
                fact_type = FactType.NON_NUMERIC
        else:
            value = raw_value

        decimals_val: int | None = None
        if decimals_str is not None:
            try:
                decimals_val = int(decimals_str)
            except ValueError:
                pass

        precision_val: int | None = None
        if precision_str is not None:
            try:
                precision_val = int(precision_str)
            except ValueError:
                pass

        facts.append(
            Fact(
                fact_id=fact_id,
                concept_qname=tag,
                context_ref=context_ref,
                unit_ref=unit_ref,
                value=value,
                fact_type=fact_type,
                decimals=decimals_val,
                precision=precision_val,
                is_nil=is_nil,
                language=elem.get("{http://www.w3.org/XML/1998/namespace}lang"),
                source_line=elem.sourceline,
                source_file=str(path),
            )
        )
        fact_counter += 1

    namespace_map: dict[str | None, str] = {}
    for prefix, uri in raw_doc.namespaces.items():
        key: str | None = prefix if prefix != "" else None
        namespace_map[key] = uri

    return XBRLInstance(
        file_path=str(path),
        input_format=InputFormat.XBRL_XML,
        schema_refs=raw_doc.declared_schema_refs,
        contexts=contexts,
        units=units,
        facts=facts,
        footnotes=[],
        namespace_map=namespace_map,
    )
