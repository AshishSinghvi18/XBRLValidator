"""XBRL Validator exception hierarchy.

Every exception carries structured metadata so that callers can produce
machine-readable validation reports without parsing error messages.

Hierarchy
---------
::

    XBRLValidatorError
    ├── ParseError
    │   ├── XMLParseError
    │   ├── IXBRLParseError
    │   ├── JSONParseError
    │   ├── CSVParseError
    │   └── PackageParseError
    ├── SecurityError
    │   ├── XXEError
    │   ├── BillionLaughsError
    │   ├── ZipBombError
    │   ├── PathTraversalError
    │   └── SSRFError
    ├── FileTooLargeError
    ├── MemoryBudgetExceededError
    ├── TaxonomyResolutionError
    │   ├── TaxonomyNotFoundError
    │   ├── TaxonomyTimeoutError
    │   └── TaxonomyCacheError
    ├── DiskSpillError
    ├── UnsupportedFormatError
    ├── ProfileNotFoundError
    ├── RuleCompileError
    ├── XULEError
    │   ├── XULEParseError
    │   ├── XULERuntimeError
    │   └── XULETimeoutError
    ├── FormulaError
    │   ├── FormulaParseError
    │   ├── FormulaEvaluationError
    │   └── FormulaTimeoutError
    ├── ConformanceError
    └── PipelineAbortError

References:
    - XBRL 2.1 §Appendix B (error codes)
    - Inline XBRL 1.1 §6 (error handling)
"""

from __future__ import annotations

from typing import Any


# ===========================================================================
# Base
# ===========================================================================


class XBRLValidatorError(Exception):
    """Base exception for all XBRL Validator errors.

    Args:
        code:    Machine-readable error code (e.g. ``"xbrl.2.1:calcInconsistency"``).
        message: Human-readable description.
        context: Arbitrary key/value metadata for structured logging.
    """

    def __init__(
        self,
        code: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.context: dict[str, Any] = context or {}
        super().__init__(f"[{code}] {message}")

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


# ===========================================================================
# Parse Errors
# ===========================================================================


class ParseError(XBRLValidatorError):
    """Error during document parsing.

    Args:
        code:      Machine-readable error code.
        message:   Human-readable description.
        file_path: Path or URL of the file that failed to parse.
        line:      1-based line number where the error occurred (if known).
        column:    1-based column number (if known).
        snippet:   A short extract of the problematic source text.
        context:   Extra metadata.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        file_path: str = "",
        line: int | None = None,
        column: int | None = None,
        snippet: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        self.file_path = file_path
        self.line = line
        self.column = column
        self.snippet = snippet
        ctx = dict(context or {})
        if file_path:
            ctx["file_path"] = file_path
        if line is not None:
            ctx["line"] = line
        if column is not None:
            ctx["column"] = column
        if snippet:
            ctx["snippet"] = snippet
        super().__init__(code=code, message=message, context=ctx)


class XMLParseError(ParseError):
    """Malformed or invalid XML in an XBRL 2.1 instance or taxonomy schema."""


class IXBRLParseError(ParseError):
    """Error parsing an Inline XBRL (HTML/XHTML) document."""


class JSONParseError(ParseError):
    """Error parsing an xBRL-JSON document."""


class CSVParseError(ParseError):
    """Error parsing an xBRL-CSV document."""


class PackageParseError(ParseError):
    """Error parsing a taxonomy or report package (ZIP structure)."""


# ===========================================================================
# Security Errors
# ===========================================================================


class SecurityError(XBRLValidatorError):
    """Security violation detected during processing.

    Args:
        code:        Machine-readable error code.
        message:     Human-readable description.
        attack_type: Short identifier for the class of attack.
        context:     Extra metadata.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        attack_type: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        self.attack_type = attack_type
        ctx = dict(context or {})
        if attack_type:
            ctx["attack_type"] = attack_type
        super().__init__(code=code, message=message, context=ctx)


class XXEError(SecurityError):
    """XML External Entity (XXE) injection detected.

    Reference: OWASP – XML External Entity Prevention.
    """

    def __init__(
        self,
        message: str = "XML External Entity expansion blocked",
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="security:xxe",
            message=message,
            attack_type="xxe",
            context=context,
        )


class BillionLaughsError(SecurityError):
    """Billion-laughs (entity-expansion bomb) attack detected.

    Reference: OWASP – XML Entity Expansion.
    """

    def __init__(
        self,
        message: str = "Excessive XML entity expansion detected (billion-laughs)",
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="security:billionLaughs",
            message=message,
            attack_type="billion_laughs",
            context=context,
        )


class ZipBombError(SecurityError):
    """ZIP-bomb (decompression bomb) detected.

    Reference: ZIP specification §4.3.7.
    """

    def __init__(
        self,
        message: str = "Potential ZIP bomb detected – compression ratio exceeded limit",
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="security:zipBomb",
            message=message,
            attack_type="zip_bomb",
            context=context,
        )


class PathTraversalError(SecurityError):
    """Path traversal attack detected in ZIP entry or file reference.

    Reference: CWE-22 Path Traversal.
    """

    def __init__(
        self,
        message: str = "Path traversal detected in archive entry",
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="security:pathTraversal",
            message=message,
            attack_type="path_traversal",
            context=context,
        )


class SSRFError(SecurityError):
    """Server-Side Request Forgery (SSRF) attempt detected.

    Reference: OWASP – SSRF Prevention.
    """

    def __init__(
        self,
        message: str = "Taxonomy URL targets a private/internal network address",
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="security:ssrf",
            message=message,
            attack_type="ssrf",
            context=context,
        )


# ===========================================================================
# Resource-Limit Errors
# ===========================================================================


class FileTooLargeError(XBRLValidatorError):
    """Input file exceeds the configured size limit.

    Args:
        file_path:  Path of the oversized file.
        size_bytes: Actual size in bytes.
        limit_bytes: Configured limit in bytes.
    """

    def __init__(
        self,
        file_path: str,
        size_bytes: int,
        limit_bytes: int,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.file_path = file_path
        self.size_bytes = size_bytes
        self.limit_bytes = limit_bytes
        ctx = dict(context or {})
        ctx.update(
            file_path=file_path,
            size_bytes=size_bytes,
            limit_bytes=limit_bytes,
        )
        super().__init__(
            code="resource:fileTooLarge",
            message=(
                f"File {file_path!r} is {size_bytes:,} bytes, "
                f"exceeding the {limit_bytes:,}-byte limit"
            ),
            context=ctx,
        )


class MemoryBudgetExceededError(XBRLValidatorError):
    """Process memory usage exceeded the configured budget.

    Args:
        used_bytes:   Current memory usage.
        budget_bytes: Configured budget.
    """

    def __init__(
        self,
        used_bytes: int,
        budget_bytes: int,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.used_bytes = used_bytes
        self.budget_bytes = budget_bytes
        ctx = dict(context or {})
        ctx.update(used_bytes=used_bytes, budget_bytes=budget_bytes)
        super().__init__(
            code="resource:memoryBudgetExceeded",
            message=(
                f"Memory usage {used_bytes:,} bytes exceeds "
                f"budget of {budget_bytes:,} bytes"
            ),
            context=ctx,
        )


# ===========================================================================
# Taxonomy Resolution Errors
# ===========================================================================


class TaxonomyResolutionError(XBRLValidatorError):
    """Failed to resolve or load a taxonomy component.

    Args:
        url: URL or path that could not be resolved.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        url: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        self.url = url
        ctx = dict(context or {})
        if url:
            ctx["url"] = url
        super().__init__(code=code, message=message, context=ctx)


class TaxonomyNotFoundError(TaxonomyResolutionError):
    """Taxonomy schema or linkbase could not be found at the given URL."""

    def __init__(
        self,
        url: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="taxonomy:notFound",
            message=f"Taxonomy document not found: {url!r}",
            url=url,
            context=context,
        )


class TaxonomyTimeoutError(TaxonomyResolutionError):
    """Taxonomy fetch timed out."""

    def __init__(
        self,
        url: str,
        timeout_seconds: int,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        ctx = dict(context or {})
        ctx["timeout_seconds"] = timeout_seconds
        super().__init__(
            code="taxonomy:timeout",
            message=f"Taxonomy fetch timed out after {timeout_seconds}s: {url!r}",
            url=url,
            context=ctx,
        )


class TaxonomyCacheError(TaxonomyResolutionError):
    """Taxonomy cache read/write failure."""

    def __init__(
        self,
        message: str,
        *,
        url: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="taxonomy:cacheError",
            message=message,
            url=url,
            context=context,
        )


# ===========================================================================
# Disk / Format / Profile Errors
# ===========================================================================


class DiskSpillError(XBRLValidatorError):
    """Failure during spill-to-disk operations."""

    def __init__(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="resource:diskSpillError",
            message=message,
            context=context,
        )


class UnsupportedFormatError(XBRLValidatorError):
    """Input file format is not supported by this validator."""

    def __init__(
        self,
        format_name: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.format_name = format_name
        ctx = dict(context or {})
        ctx["format_name"] = format_name
        super().__init__(
            code="input:unsupportedFormat",
            message=f"Unsupported input format: {format_name!r}",
            context=ctx,
        )


class ProfileNotFoundError(XBRLValidatorError):
    """Requested regulatory profile does not exist."""

    def __init__(
        self,
        profile_id: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.profile_id = profile_id
        ctx = dict(context or {})
        ctx["profile_id"] = profile_id
        super().__init__(
            code="config:profileNotFound",
            message=f"Regulatory profile not found: {profile_id!r}",
            context=ctx,
        )


class RuleCompileError(XBRLValidatorError):
    """A validation rule failed to compile."""

    def __init__(
        self,
        rule_id: str,
        reason: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.rule_id = rule_id
        self.reason = reason
        ctx = dict(context or {})
        ctx.update(rule_id=rule_id, reason=reason)
        super().__init__(
            code="rule:compileError",
            message=f"Rule {rule_id!r} failed to compile: {reason}",
            context=ctx,
        )


# ===========================================================================
# XULE Errors
# ===========================================================================


class XULEError(XBRLValidatorError):
    """Base error for the embedded XULE rule engine."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        rule_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        self.rule_id = rule_id
        ctx = dict(context or {})
        if rule_id:
            ctx["rule_id"] = rule_id
        super().__init__(code=code, message=message, context=ctx)


class XULEParseError(XULEError):
    """XULE rule source could not be parsed."""

    def __init__(
        self,
        message: str,
        *,
        rule_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="xule:parseError",
            message=message,
            rule_id=rule_id,
            context=context,
        )


class XULERuntimeError(XULEError):
    """Runtime error during XULE rule evaluation."""

    def __init__(
        self,
        message: str,
        *,
        rule_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="xule:runtimeError",
            message=message,
            rule_id=rule_id,
            context=context,
        )


class XULETimeoutError(XULEError):
    """XULE rule evaluation timed out."""

    def __init__(
        self,
        rule_id: str,
        timeout_seconds: float,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        ctx = dict(context or {})
        ctx["timeout_seconds"] = timeout_seconds
        super().__init__(
            code="xule:timeout",
            message=f"XULE rule {rule_id!r} timed out after {timeout_seconds}s",
            rule_id=rule_id,
            context=ctx,
        )


# ===========================================================================
# Formula Errors
# ===========================================================================


class FormulaError(XBRLValidatorError):
    """Base error for the XBRL Formula processor.

    Reference: XBRL Formula 1.0 §5.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        formula_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        self.formula_id = formula_id
        ctx = dict(context or {})
        if formula_id:
            ctx["formula_id"] = formula_id
        super().__init__(code=code, message=message, context=ctx)


class FormulaParseError(FormulaError):
    """Formula linkbase could not be parsed."""

    def __init__(
        self,
        message: str,
        *,
        formula_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="formula:parseError",
            message=message,
            formula_id=formula_id,
            context=context,
        )


class FormulaEvaluationError(FormulaError):
    """Runtime error during formula evaluation."""

    def __init__(
        self,
        message: str,
        *,
        formula_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="formula:evaluationError",
            message=message,
            formula_id=formula_id,
            context=context,
        )


class FormulaTimeoutError(FormulaError):
    """Formula evaluation exceeded the time limit."""

    def __init__(
        self,
        formula_id: str,
        timeout_seconds: float,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        ctx = dict(context or {})
        ctx["timeout_seconds"] = timeout_seconds
        super().__init__(
            code="formula:timeout",
            message=f"Formula {formula_id!r} timed out after {timeout_seconds}s",
            formula_id=formula_id,
            context=ctx,
        )


# ===========================================================================
# Pipeline / Conformance Errors
# ===========================================================================


class ConformanceError(XBRLValidatorError):
    """Conformance-suite test failure."""

    def __init__(
        self,
        test_id: str,
        expected: str,
        actual: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.test_id = test_id
        self.expected = expected
        self.actual = actual
        ctx = dict(context or {})
        ctx.update(test_id=test_id, expected=expected, actual=actual)
        super().__init__(
            code="conformance:testFailure",
            message=(
                f"Conformance test {test_id!r}: expected {expected!r}, "
                f"got {actual!r}"
            ),
            context=ctx,
        )


class PipelineAbortError(XBRLValidatorError):
    """Validation pipeline was aborted (e.g. by a fatal upstream error)."""

    def __init__(
        self,
        reason: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.reason = reason
        ctx = dict(context or {})
        ctx["reason"] = reason
        super().__init__(
            code="pipeline:abort",
            message=f"Pipeline aborted: {reason}",
            context=ctx,
        )
