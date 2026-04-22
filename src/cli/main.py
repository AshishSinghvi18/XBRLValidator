"""CLI entry point for XBRL validation — uses Typer."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="xbrl-validate", help="XBRL/iXBRL Validation Engine")
console = Console()


@app.command()
def validate(
    file_path: str = typer.Argument(..., help="Path to XBRL/iXBRL file"),
    regulator: str = typer.Option("", help="Regulator profile (efm, esef, etc.)"),
    output: str = typer.Option("text", help="Output format: text, json, html, csv"),
    strict: bool = typer.Option(False, help="Treat warnings as errors"),
    max_errors: int = typer.Option(0, help="Stop after N errors (0=unlimited)"),
) -> None:
    """Validate an XBRL or iXBRL document."""
    from src.core.parser.format_detector import FormatDetector
    from src.core.types import InputFormat, Severity
    from src.report.formatter import ReportFormatter

    path = Path(file_path)
    if not path.is_file():
        console.print(f"[red]Error:[/red] File not found: {file_path}")
        raise typer.Exit(code=1)

    # 1. Detect format
    detector = FormatDetector()
    try:
        detection = detector.detect(str(path))
    except Exception as exc:
        console.print(f"[red]Error detecting format:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        f"[cyan]Detected format:[/cyan] {detection.format.value} "
        f"(confidence: {detection.detection_confidence:.0%})"
    )

    # 2. Parse the document
    instance = _parse_document(path, detection.format)
    if instance is None:
        console.print("[red]Error:[/red] Could not parse document")
        raise typer.Exit(code=1)

    # 3. Run validation
    from src.validator import XBRLValidator

    validator = XBRLValidator()
    messages = validator.validate(instance)

    # 4. Load regulator profile rules if specified
    if regulator:
        try:
            from src.plugin.profile_loader import ProfileLoader

            profile = ProfileLoader.load(regulator)
            console.print(f"[cyan]Loaded profile:[/cyan] {profile.display_name}")
        except Exception as exc:
            console.print(f"[yellow]Warning:[/yellow] Could not load profile '{regulator}': {exc}")

    # 5. Apply strict mode — promote warnings to errors
    if strict:
        from src.core.model.instance import ValidationMessage as VM

        promoted: list[VM] = []
        for msg in messages:
            if msg.severity == Severity.WARNING:
                promoted.append(VM(
                    code=msg.code,
                    severity=Severity.ERROR,
                    message=msg.message,
                    spec_ref=msg.spec_ref,
                    file_path=msg.file_path,
                    line=msg.line,
                    column=msg.column,
                    fix_suggestion=msg.fix_suggestion,
                ))
            else:
                promoted.append(msg)
        messages = promoted

    # 6. Apply max_errors limit
    if max_errors > 0:
        error_count = 0
        limited: list[object] = []
        for msg in messages:
            limited.append(msg)
            if msg.severity == Severity.ERROR:
                error_count += 1
                if error_count >= max_errors:
                    break
        messages = limited  # type: ignore[assignment]

    # 7. Format and output results
    formatter = ReportFormatter()
    try:
        report = formatter.format(output, messages, instance)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if output == "text":
        console.print(report)
    else:
        typer.echo(report)

    # 8. Exit code: non-zero if errors found
    error_count = sum(1 for m in messages if m.severity == Severity.ERROR)
    if error_count > 0:
        raise typer.Exit(code=1)


def _parse_document(
    path: Path,
    input_format: "InputFormat",
) -> "XBRLInstance | None":
    """Parse a document into an XBRLInstance based on detected format."""
    from src.core.model.instance import XBRLInstance
    from src.core.types import InputFormat

    if input_format in (InputFormat.IXBRL_HTML, InputFormat.IXBRL_XHTML):
        return _parse_ixbrl(path, input_format)
    if input_format == InputFormat.XBRL_XML:
        return _parse_xbrl_xml(path)
    console.print(f"[yellow]Warning:[/yellow] Format '{input_format.value}' parsing not yet implemented")
    return None


def _parse_ixbrl(path: Path, input_format: "InputFormat") -> "XBRLInstance":
    """Parse an iXBRL document into an XBRLInstance."""
    from src.core.model.context import Context
    from src.core.model.fact import Fact
    from src.core.model.instance import XBRLInstance
    from src.core.model.unit import Unit
    from src.core.parser.ixbrl_parser import IXBRLParser
    from src.core.types import FactType, InputFormat

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


def _parse_xbrl_xml(path: Path) -> "XBRLInstance":
    """Parse a traditional XBRL XML instance into an XBRLInstance."""
    from decimal import Decimal, InvalidOperation

    from lxml import etree

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
        period_elem = ctx_elem.find(f"{{{ns_xbrli}}}period")

        entity = Entity(
            identifier="",
            scheme="",
        )
        if entity_elem is not None:
            ident_elem = entity_elem.find(f"{{{ns_xbrli}}}identifier")
            if ident_elem is not None:
                entity = Entity(
                    identifier=ident_elem.text or "",
                    scheme=ident_elem.get("scheme", ""),
                )

        period = Period(period_type=PeriodType.INSTANT, instant=None, start_date=None, end_date=None)
        if period_elem is not None:
            instant = period_elem.find(f"{{{ns_xbrli}}}instant")
            start = period_elem.find(f"{{{ns_xbrli}}}startDate")
            end = period_elem.find(f"{{{ns_xbrli}}}endDate")
            forever = period_elem.find(f"{{{ns_xbrli}}}forever")
            if instant is not None:
                period = Period(period_type=PeriodType.INSTANT, instant=None, start_date=None, end_date=None)
            elif start is not None and end is not None:
                period = Period(period_type=PeriodType.DURATION, instant=None, start_date=None, end_date=None)
            elif forever is not None:
                period = Period(period_type=PeriodType.FOREVER, instant=None, start_date=None, end_date=None)

        contexts[ctx_id] = Context(
            context_id=ctx_id,
            entity=entity,
            period=period,
        )

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
    skip_tags = {
        f"{{{ns_xbrli}}}context",
        f"{{{ns_xbrli}}}unit",
        f"{{{ns_xbrli}}}schemaRef",
        f"{{{ns_xbrli}}}xbrl",
    }
    fact_counter = 0
    for elem in root:
        tag = elem.tag if isinstance(elem.tag, str) else ""
        if not tag or tag in skip_tags:
            continue
        if tag.startswith(f"{{{ns_xbrli}}}"):
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


@app.command()
def version() -> None:
    """Show version information."""
    console.print("[bold]XBRL Validator[/bold] v1.0.0")
    console.print("Production-grade XBRL/iXBRL validation engine")


if __name__ == "__main__":
    app()
