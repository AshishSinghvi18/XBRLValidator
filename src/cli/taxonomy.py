"""CLI for taxonomy management."""

from __future__ import annotations

import zipfile
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="xbrl-taxonomy", help="Taxonomy Package Management")
console = Console()


@app.command()
def preload_package(
    package_path: str = typer.Argument(..., help="Path to taxonomy package ZIP"),
) -> None:
    """Preload a taxonomy package into the cache."""
    path = Path(package_path)
    if not path.is_file():
        console.print(f"[red]Error:[/red] File not found: {package_path}")
        raise typer.Exit(code=1)

    if not zipfile.is_zipfile(path):
        console.print(f"[red]Error:[/red] Not a valid ZIP file: {package_path}")
        raise typer.Exit(code=1)

    try:
        from src.core.parser.package_parser import PackageParser

        parser = PackageParser()
        package = parser.parse(str(path))

        console.print(f"[green]✓[/green] Taxonomy package loaded: {path.name}")
        console.print(f"  Entry points: {len(package.entry_points)}")
    except Exception as exc:
        console.print(f"[red]Error loading package:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def clear_cache() -> None:
    """Clear the taxonomy cache."""
    cache_dir = Path.home() / ".xbrl-validator" / "cache"
    if cache_dir.exists():
        import shutil

        file_count = sum(1 for _ in cache_dir.rglob("*") if _.is_file())
        shutil.rmtree(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]✓[/green] Cache cleared ({file_count} files removed)")
    else:
        console.print("[yellow]Cache directory does not exist — nothing to clear[/yellow]")


@app.command()
def info(
    package_path: str = typer.Argument(..., help="Path to taxonomy package"),
) -> None:
    """Display information about a taxonomy package."""
    path = Path(package_path)
    if not path.is_file():
        console.print(f"[red]Error:[/red] File not found: {package_path}")
        raise typer.Exit(code=1)

    if not zipfile.is_zipfile(path):
        console.print(f"[red]Error:[/red] Not a valid ZIP file: {package_path}")
        raise typer.Exit(code=1)

    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        total_size = sum(info.file_size for info in zf.infolist())

        table = Table(title=f"Taxonomy Package: {path.name}")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("File", str(path))
        table.add_row("Compressed size", f"{path.stat().st_size:,} bytes")
        table.add_row("Uncompressed size", f"{total_size:,} bytes")
        table.add_row("File count", str(len(names)))

        has_meta = "META-INF/taxonomyPackage.xml" in names
        table.add_row("Has META-INF", "✓" if has_meta else "✗")

        has_catalog = "META-INF/catalog.xml" in names
        table.add_row("Has catalog", "✓" if has_catalog else "✗")

        schema_files = [n for n in names if n.endswith(".xsd")]
        table.add_row("Schema files", str(len(schema_files)))

        linkbase_files = [n for n in names if n.endswith(".xml") and "linkbase" in n.lower()]
        table.add_row("Linkbase files", str(len(linkbase_files)))

        console.print(table)


if __name__ == "__main__":
    app()
