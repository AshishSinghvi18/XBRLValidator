"""CLI for conformance suite testing."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

app = typer.Typer(name="xbrl-conform", help="Run XBRL Conformance Suite Tests")
console = Console()

_KNOWN_SPECS: dict[str, str] = {
    "xbrl21": "XBRL 2.1 Conformance Suite",
    "dimensions": "XBRL Dimensions 1.0 Conformance Suite",
    "calculation": "Calculation Linkbase Conformance Suite",
    "inline": "Inline XBRL 1.1 Conformance Suite",
}


@app.command()
def run(
    suite_dir: str = typer.Argument(..., help="Path to conformance suite directory"),
    spec: str = typer.Option("xbrl21", help="Spec to test: xbrl21, dimensions, calculation, inline"),
    pattern: str = typer.Option("", help="Filter test cases by ID pattern"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed results"),
    stop_on_fail: bool = typer.Option(False, help="Stop on first failure"),
) -> None:
    """Run a conformance test suite."""
    suite_path = Path(suite_dir)
    if not suite_path.is_dir():
        console.print(f"[red]Error:[/red] Directory not found: {suite_dir}")
        raise typer.Exit(code=1)

    if spec not in _KNOWN_SPECS:
        console.print(f"[red]Error:[/red] Unknown spec '{spec}'. Known: {', '.join(_KNOWN_SPECS)}")
        raise typer.Exit(code=1)

    console.print(f"[cyan]Running:[/cyan] {_KNOWN_SPECS[spec]}")
    console.print(f"[cyan]Suite directory:[/cyan] {suite_path}")

    # Discover test cases
    test_files = _discover_test_cases(suite_path, spec)
    if not test_files:
        console.print("[yellow]No test cases found in the specified directory[/yellow]")
        raise typer.Exit(code=0)

    if pattern:
        test_files = [f for f in test_files if pattern in f.stem]

    console.print(f"[cyan]Test cases found:[/cyan] {len(test_files)}")

    passed = 0
    failed = 0
    errors = 0
    failures: list[tuple[str, str]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Running tests...", total=len(test_files))

        for test_file in test_files:
            progress.update(task, description=f"Testing: {test_file.stem}")
            try:
                result = _run_single_test(test_file, spec)
                if result:
                    passed += 1
                else:
                    failed += 1
                    failures.append((test_file.stem, "Validation result mismatch"))
                    if stop_on_fail:
                        break
            except Exception as exc:
                errors += 1
                failures.append((test_file.stem, str(exc)))
                if stop_on_fail:
                    break
            progress.advance(task)

    # Summary
    console.print()
    table = Table(title="Conformance Suite Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="white", justify="right")

    table.add_row("Total", str(passed + failed + errors))
    table.add_row("Passed", f"[green]{passed}[/green]")
    table.add_row("Failed", f"[red]{failed}[/red]" if failed else "0")
    table.add_row("Errors", f"[red]{errors}[/red]" if errors else "0")
    console.print(table)

    if verbose and failures:
        console.print()
        fail_table = Table(title="Failures")
        fail_table.add_column("Test Case", style="cyan")
        fail_table.add_column("Reason", style="red")
        for test_id, reason in failures:
            fail_table.add_row(test_id, reason)
        console.print(fail_table)

    if failed > 0 or errors > 0:
        raise typer.Exit(code=1)


def _discover_test_cases(suite_path: Path, spec: str) -> list[Path]:
    """Find test case files in the conformance suite directory."""
    extensions = {".xbrl", ".xml", ".xhtml", ".htm", ".html"}
    test_files: list[Path] = []
    for ext in extensions:
        test_files.extend(suite_path.rglob(f"*{ext}"))
    test_files.sort(key=lambda p: p.name)
    return test_files


def _run_single_test(test_file: Path, spec: str) -> bool:
    """Run a single conformance test case.

    Returns True if the test passes, False otherwise.
    """
    from src.core.parser.format_detector import FormatDetector
    from src.core.types import InputFormat

    detector = FormatDetector()
    try:
        detection = detector.detect(str(test_file))
    except Exception:
        return False

    # For conformance testing, we just verify the file can be parsed
    # without raising unexpected exceptions
    if detection.format in (InputFormat.IXBRL_HTML, InputFormat.IXBRL_XHTML):
        from src.core.parser.ixbrl_parser import IXBRLParser

        parser = IXBRLParser()
        try:
            parser.parse(str(test_file))
            return True
        except Exception:
            return False
    elif detection.format == InputFormat.XBRL_XML:
        from src.core.parser.xml_parser import XMLParser

        parser = XMLParser()
        try:
            parser.parse(str(test_file))
            return True
        except Exception:
            return False

    return False


if __name__ == "__main__":
    app()
