"""Validation report formatter — outputs text, JSON, HTML, CSV formats."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from src.core.model.instance import ValidationMessage, XBRLInstance
from src.core.types import Severity

_TEMPLATES_DIR = Path(__file__).parent / "templates"


class ReportFormatter:
    """Formats validation results into various output formats.

    Supports text, JSON, HTML, and CSV output. The HTML format uses
    Jinja2 templates located in ``src/report/templates/``.
    """

    def __init__(self) -> None:
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=True,
        )

    def format_text(
        self,
        messages: list[ValidationMessage],
        instance: XBRLInstance,
    ) -> str:
        """Format validation results as human-readable text.

        Args:
            messages: Validation messages to format.
            instance: The validated XBRL instance.

        Returns:
            A formatted text report string.
        """
        error_count = sum(1 for m in messages if m.severity == Severity.ERROR)
        warning_count = sum(1 for m in messages if m.severity == Severity.WARNING)

        lines: list[str] = [
            "=" * 72,
            f"XBRL Validation Report — {instance.file_path}",
            "=" * 72,
            f"Format:    {instance.input_format.value}",
            f"Facts:     {instance.fact_count()}",
            f"Errors:    {error_count}",
            f"Warnings:  {warning_count}",
            f"Valid:     {'Yes' if error_count == 0 else 'No'}",
            "-" * 72,
        ]

        if not messages:
            lines.append("No validation issues found.")
        else:
            for msg in messages:
                severity_tag = msg.severity.value.upper()
                location = ""
                if msg.line is not None:
                    location = f" (line {msg.line}"
                    if msg.column is not None:
                        location += f", col {msg.column}"
                    location += ")"

                lines.append(f"[{severity_tag}] {msg.code}{location}")
                lines.append(f"  {msg.message}")
                if msg.spec_ref:
                    lines.append(f"  Ref: {msg.spec_ref}")
                if msg.fix_suggestion:
                    lines.append(f"  Fix: {msg.fix_suggestion}")
                lines.append("")

        lines.append("=" * 72)
        return "\n".join(lines)

    def format_json(
        self,
        messages: list[ValidationMessage],
        instance: XBRLInstance,
    ) -> str:
        """Format validation results as JSON.

        Args:
            messages: Validation messages to format.
            instance: The validated XBRL instance.

        Returns:
            A JSON string containing the validation report.
        """
        error_count = sum(1 for m in messages if m.severity == Severity.ERROR)
        warning_count = sum(1 for m in messages if m.severity == Severity.WARNING)

        report: dict[str, Any] = {
            "file_name": instance.file_path,
            "input_format": instance.input_format.value,
            "fact_count": instance.fact_count(),
            "error_count": error_count,
            "warning_count": warning_count,
            "valid": error_count == 0,
            "messages": [
                {
                    "code": m.code,
                    "severity": m.severity.value,
                    "message": m.message,
                    "spec_ref": m.spec_ref or None,
                    "file_path": m.file_path or None,
                    "line": m.line,
                    "column": m.column,
                    "fix_suggestion": m.fix_suggestion or None,
                }
                for m in messages
            ],
        }

        return json.dumps(report, indent=2, ensure_ascii=False)

    def format_html(
        self,
        messages: list[ValidationMessage],
        instance: XBRLInstance,
    ) -> str:
        """Format validation results as an HTML report.

        Uses the Jinja2 template at ``templates/report.html.j2``.

        Args:
            messages: Validation messages to format.
            instance: The validated XBRL instance.

        Returns:
            A rendered HTML string.
        """
        error_count = sum(1 for m in messages if m.severity == Severity.ERROR)
        warning_count = sum(1 for m in messages if m.severity == Severity.WARNING)

        template = self._jinja_env.get_template("report.html.j2")
        return template.render(
            file_name=instance.file_path,
            input_format=instance.input_format.value,
            fact_count=instance.fact_count(),
            error_count=error_count,
            warning_count=warning_count,
            valid=error_count == 0,
            messages=messages,
        )

    def format_csv(
        self,
        messages: list[ValidationMessage],
        instance: XBRLInstance,
    ) -> str:
        """Format validation messages as CSV.

        Args:
            messages: Validation messages to format.
            instance: The validated XBRL instance.

        Returns:
            A CSV string with header row and one row per message.
        """
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "code",
            "severity",
            "message",
            "spec_ref",
            "file_path",
            "line",
            "column",
            "fix_suggestion",
        ])
        for m in messages:
            writer.writerow([
                m.code,
                m.severity.value,
                m.message,
                m.spec_ref,
                m.file_path,
                m.line if m.line is not None else "",
                m.column if m.column is not None else "",
                m.fix_suggestion,
            ])
        return output.getvalue()

    def format(
        self,
        format_type: str,
        messages: list[ValidationMessage],
        instance: XBRLInstance,
    ) -> str:
        """Format validation results in the specified output format.

        Args:
            format_type: Output format (``"text"``, ``"json"``,
                ``"html"``, or ``"csv"``).
            messages: Validation messages to format.
            instance: The validated XBRL instance.

        Returns:
            The formatted report string.

        Raises:
            ValueError: If *format_type* is not recognised.
        """
        formatters: dict[str, Any] = {
            "text": self.format_text,
            "json": self.format_json,
            "html": self.format_html,
            "csv": self.format_csv,
        }
        formatter = formatters.get(format_type)
        if not formatter:
            raise ValueError(
                f"Unknown format: {format_type!r}. "
                f"Supported formats: {', '.join(formatters)}"
            )
        return formatter(messages, instance)
