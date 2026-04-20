"""Exception hierarchy for the XBRL Validator Engine.

Most validation findings are accumulated as ``ValidationMessage`` objects;
exceptions are reserved for *unrecoverable* conditions or security
violations that must abort processing.

Spec references: Rule 3 (zero-trust), Rule 10 (fail-safe recovery),
Rule 12 (memory budget).
"""

from __future__ import annotations

from typing import Any

# ── Base ────────────────────────────────────────────────────────────────────


class XBRLValidatorError(Exception):
    """Root of the XBRL-Validator exception hierarchy.

    Every subclass carries a machine-readable ``code`` (e.g. ``SEC-0001``),
    a human-readable ``message``, and an arbitrary ``context`` dict for
    structured logging.
    """

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "XBRL-0000",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code: str = code
        self.message: str = message
        self.context: dict[str, Any] = context or {}


# ── Parse errors ────────────────────────────────────────────────────────────


class ParseError(XBRLValidatorError):
    """Base for all document parsing failures."""

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "PARSE-0000",
        context: dict[str, Any] | None = None,
        file_path: str = "",
        line: int | None = None,
        column: int | None = None,
        snippet: str = "",
    ) -> None:
        super().__init__(message, code=code, context=context)
        self.file_path: str = file_path
        self.line: int | None = line
        self.column: int | None = column
        self.snippet: str = snippet


class XMLParseError(ParseError):
    """Malformed XML detected during parsing."""


class IXBRLParseError(ParseError):
    """Inline XBRL markup error (invalid nesting, missing continuation, etc.)."""


class JSONParseError(ParseError):
    """Malformed XBRL-JSON document."""


class CSVParseError(ParseError):
    """Malformed XBRL-CSV document."""


class PackageParseError(ParseError):
    """Invalid taxonomy or report package structure."""


# ── Security errors ─────────────────────────────────────────────────────────


class SecurityError(XBRLValidatorError):
    """Base for security-related abort conditions.

    Spec: Rule 3 — Zero-Trust Parsing.
    """

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "SEC-0000",
        context: dict[str, Any] | None = None,
        attack_type: str = "",
    ) -> None:
        super().__init__(message, code=code, context=context)
        self.attack_type: str = attack_type


class XXEError(SecurityError):
    """XML External Entity expansion detected."""

    def __init__(self, message: str = "XXE attack detected", **kwargs: Any) -> None:
        super().__init__(message, attack_type="xxe", **kwargs)


class BillionLaughsError(SecurityError):
    """Excessive entity expansion (billion-laughs / quadratic blowup)."""

    def __init__(
        self, message: str = "Billion-laughs attack detected", **kwargs: Any
    ) -> None:
        super().__init__(message, attack_type="billion-laughs", **kwargs)


class ZipBombError(SecurityError):
    """ZIP decompression bomb detected."""

    def __init__(self, message: str = "Zip bomb detected", **kwargs: Any) -> None:
        super().__init__(message, attack_type="zip-bomb", **kwargs)


class PathTraversalError(SecurityError):
    """Path traversal attempt (``../`` escape) detected."""

    def __init__(
        self, message: str = "Path traversal detected", **kwargs: Any
    ) -> None:
        super().__init__(message, attack_type="path-traversal", **kwargs)


class SSRFError(SecurityError):
    """Server-Side Request Forgery — blocked outbound URL."""

    def __init__(
        self, message: str = "SSRF: blocked outbound URL", **kwargs: Any
    ) -> None:
        super().__init__(message, attack_type="ssrf", **kwargs)


# ── Resource-limit errors ──────────────────────────────────────────────────


class FileTooLargeError(XBRLValidatorError):
    """Input file exceeds the configured maximum size."""

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "LIMIT-0001",
        context: dict[str, Any] | None = None,
        file_size: int = 0,
        max_size: int = 0,
    ) -> None:
        if not message:
            message = (
                f"File size {file_size} bytes exceeds maximum {max_size} bytes"
            )
        super().__init__(message, code=code, context=context)
        self.file_size: int = file_size
        self.max_size: int = max_size


class MemoryBudgetExceededError(XBRLValidatorError):
    """A component tried to allocate more than the memory budget allows.

    Spec: Rule 12 — Memory Budget.
    """

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "LIMIT-0002",
        context: dict[str, Any] | None = None,
        component: str = "",
        requested: int = 0,
        available: int = 0,
    ) -> None:
        if not message:
            message = (
                f"Memory budget exceeded by '{component}': "
                f"requested={requested}, available={available}"
            )
        super().__init__(message, code=code, context=context)
        self.component: str = component
        self.requested: int = requested
        self.available: int = available


# ── Taxonomy errors ─────────────────────────────────────────────────────────


class TaxonomyResolutionError(XBRLValidatorError):
    """Base for taxonomy loading / resolution failures."""

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "TAX-0000",
        context: dict[str, Any] | None = None,
        url: str = "",
        reason: str = "",
    ) -> None:
        if not message:
            message = f"Taxonomy resolution failed for '{url}': {reason}"
        super().__init__(message, code=code, context=context)
        self.url: str = url
        self.reason: str = reason


class TaxonomyNotFoundError(TaxonomyResolutionError):
    """Taxonomy entry point could not be located (local or remote)."""


class TaxonomyFetchError(TaxonomyResolutionError):
    """Network fetch of a taxonomy resource failed."""


class TaxonomyVersionMismatchError(TaxonomyResolutionError):
    """Filing references a taxonomy version that doesn't match the cache.

    Spec: Rule 15 — Version-Aware Taxonomies.
    """


class CircularImportError(TaxonomyResolutionError):
    """Circular ``xs:import`` / ``xs:include`` detected in a taxonomy DTS."""


# ── Disk / spill errors ────────────────────────────────────────────────────


class DiskSpillError(XBRLValidatorError):
    """Failure during disk-spill I/O (SQLite write, mmap, etc.)."""

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "SPILL-0001",
        context: dict[str, Any] | None = None,
        path: str = "",
        operation: str = "",
    ) -> None:
        if not message:
            message = f"Disk spill error at '{path}' during {operation}"
        super().__init__(message, code=code, context=context)
        self.path: str = path
        self.operation: str = operation


# ── Format / profile errors ────────────────────────────────────────────────


class UnsupportedFormatError(XBRLValidatorError):
    """Input format could not be identified or is not supported."""

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "FMT-0001",
        context: dict[str, Any] | None = None,
        detected_content: str = "",
    ) -> None:
        if not message:
            message = f"Unsupported format: {detected_content}"
        super().__init__(message, code=code, context=context)
        self.detected_content: str = detected_content


class ProfileNotFoundError(XBRLValidatorError):
    """A regulator profile referenced in the config was not found."""

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "PROF-0001",
        context: dict[str, Any] | None = None,
        profile_id: str = "",
    ) -> None:
        if not message:
            message = f"Profile not found: {profile_id}"
        super().__init__(message, code=code, context=context)
        self.profile_id: str = profile_id


# ── Rule / XULE errors ─────────────────────────────────────────────────────


class RuleCompileError(XBRLValidatorError):
    """A validation rule file failed to compile."""

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "RULE-0001",
        context: dict[str, Any] | None = None,
        rule_file: str = "",
        line: int | None = None,
    ) -> None:
        if not message:
            message = f"Rule compile error in '{rule_file}' at line {line}"
        super().__init__(message, code=code, context=context)
        self.rule_file: str = rule_file
        self.line: int | None = line


class XULEError(XBRLValidatorError):
    """Base for XULE engine errors."""


class XULESyntaxError(XULEError):
    """XULE rule source has a syntax error."""

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "XULE-0001",
        context: dict[str, Any] | None = None,
        file_path: str = "",
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        super().__init__(message, code=code, context=context)
        self.file_path: str = file_path
        self.line: int | None = line
        self.column: int | None = column


class XULECompileError(XULEError):
    """XULE rule compilation failed (semantic analysis)."""


class XULERuntimeError(XULEError):
    """XULE rule raised an unrecoverable error at runtime."""


class XULETimeoutError(XULEError):
    """XULE rule execution exceeded the configured timeout.

    Spec: ``DEFAULT_XULE_TIMEOUT_S`` in constants.
    """


# ── Formula errors ──────────────────────────────────────────────────────────


class FormulaError(XBRLValidatorError):
    """Base for XBRL Formula 1.0 engine errors."""


class FormulaCompileError(FormulaError):
    """Formula linkbase could not be compiled into an executable plan."""


class FormulaRuntimeError(FormulaError):
    """An assertion or formula raised an unrecoverable error at runtime."""


class FormulaTimeoutError(FormulaError):
    """Formula variable-set evaluation exceeded the configured timeout.

    Spec: ``DEFAULT_FORMULA_TIMEOUT_S`` in constants.
    """


class XPathError(FormulaError):
    """Wraps errors from the underlying XPath evaluator (elementpath)."""


# ── Conformance / pipeline errors ───────────────────────────────────────────


class ConformanceError(XBRLValidatorError):
    """A conformance-suite test produced unexpected results."""

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "CONF-0001",
        context: dict[str, Any] | None = None,
        suite: str = "",
        test_case: str = "",
        expected: str = "",
        got: str = "",
    ) -> None:
        if not message:
            message = (
                f"Conformance failure [{suite}/{test_case}]: "
                f"expected={expected}, got={got}"
            )
        super().__init__(message, code=code, context=context)
        self.suite: str = suite
        self.test_case: str = test_case
        self.expected: str = expected
        self.got: str = got


class PipelineAbortError(XBRLValidatorError):
    """Critical condition that requires the entire pipeline to stop."""
