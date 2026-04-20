"""XBRL Validator exception hierarchy.

All custom exceptions derive from :class:`XBRLValidatorError` so callers
can catch a single base class when appropriate.
"""


class XBRLValidatorError(Exception):
    """Base exception for the XBRL Validator engine.

    Attributes:
        message: Human-readable description of the error.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ParseError(XBRLValidatorError):
    """Raised when XML/XBRL parsing fails.

    Attributes:
        file_path: Path to the file that failed to parse.
        line: Line number where the error was detected (1-based).
        column: Column number where the error was detected (1-based).
    """

    def __init__(self, message: str, *, file_path: str, line: int, column: int) -> None:
        self.file_path = file_path
        self.line = line
        self.column = column
        super().__init__(f"{message} ({file_path}:{line}:{column})")


class SecurityError(XBRLValidatorError):
    """Raised when a security-sensitive construct is detected.

    Covers XXE (XML External Entity) attacks, DTD bombs (billion-laughs),
    and other potentially dangerous XML constructs.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


class FileTooLargeError(XBRLValidatorError):
    """Raised when a file exceeds the configured maximum size.

    Attributes:
        file_size: Actual size of the file in bytes.
        max_size: Maximum allowed size in bytes.
    """

    def __init__(self, message: str, *, file_size: int, max_size: int) -> None:
        self.file_size = file_size
        self.max_size = max_size
        super().__init__(f"{message} (file_size={file_size}, max_size={max_size})")


class MemoryBudgetExceededError(XBRLValidatorError):
    """Raised when the validation pipeline exceeds its memory budget."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class TaxonomyResolutionError(XBRLValidatorError):
    """Raised when a taxonomy schema or linkbase cannot be resolved.

    Attributes:
        url: The URL or path that could not be resolved.
    """

    def __init__(self, message: str, *, url: str) -> None:
        self.url = url
        super().__init__(f"{message} (url={url})")


class DiskSpillError(XBRLValidatorError):
    """Raised when writing to or reading from disk-spilled data fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class UnsupportedFormatError(XBRLValidatorError):
    """Raised when the input format is not supported by the validator."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ProfileNotFoundError(XBRLValidatorError):
    """Raised when a requested validation profile cannot be found.

    Attributes:
        profile_id: The identifier of the missing profile.
    """

    def __init__(self, message: str, *, profile_id: str) -> None:
        self.profile_id = profile_id
        super().__init__(f"{message} (profile_id={profile_id})")


class XULESyntaxError(XBRLValidatorError):
    """Raised when a XULE rule file contains a syntax error.

    Attributes:
        file_path: Path to the XULE rule file.
        line: Line number where the syntax error was detected.
    """

    def __init__(self, message: str, *, file_path: str, line: int) -> None:
        self.file_path = file_path
        self.line = line
        super().__init__(f"{message} ({file_path}:{line})")


class PipelineAbortError(XBRLValidatorError):
    """Raised to abort the entire validation pipeline immediately."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
