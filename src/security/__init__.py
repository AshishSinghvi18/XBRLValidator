"""Security guards for the XBRL Validator Engine.

This package provides zero-trust security modules that protect against
common attack vectors when processing untrusted XBRL filings:

- **XXEGuard**: Prevents XML External Entity (XXE) attacks.
- **EntityLimitsGuard**: Blocks billion-laughs / quadratic blowup attacks.
- **ZipGuard**: Detects zip bombs and path-traversal in archives.
- **URLAllowList**: SSRF prevention via URL allow-listing.
- **SecurityGuard**: Unified façade combining all guards.

Spec references:
  - Rule 3 — Zero-Trust Parsing
"""

from __future__ import annotations

import structlog
from lxml import etree

from src.core.constants import (
    DEFAULT_MAX_ENTITY_EXPANSIONS,
    DEFAULT_MAX_ZIP_FILES,
    DEFAULT_MAX_ZIP_RATIO,
    DEFAULT_MAX_ZIP_UNCOMPRESSED_BYTES,
)
from src.security.entity_limits import EntityLimitsGuard
from src.security.url_allowlist import URLAllowList
from src.security.xxe_guard import XXEGuard
from src.security.zip_guard import ZipGuard, ZipValidationResult

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class SecurityGuard:
    """Unified security façade combining all security guards.

    Provides a single entry point for creating safe parsers, validating
    ZIP archives, and checking outbound URLs.

    Example::

        guard = SecurityGuard()
        parser = guard.create_safe_parser()
        tree = guard.safe_parse("filing.xbrl")
        guard.check_url("https://xbrl.fasb.org/us-gaap/2024/...")
    """

    def __init__(
        self,
        max_entity_expansions: int = DEFAULT_MAX_ENTITY_EXPANSIONS,
        max_zip_uncompressed: int = DEFAULT_MAX_ZIP_UNCOMPRESSED_BYTES,
        max_zip_ratio: int = DEFAULT_MAX_ZIP_RATIO,
        max_zip_files: int = DEFAULT_MAX_ZIP_FILES,
        allowed_domains: list[str] | None = None,
        allow_http: bool = False,
    ) -> None:
        """Initialize all security guards.

        Args:
            max_entity_expansions: Max entity expansions before abort.
            max_zip_uncompressed: Max total uncompressed ZIP size in bytes.
            max_zip_ratio: Max per-entry compression ratio.
            max_zip_files: Max files allowed in a ZIP archive.
            allowed_domains: Trusted domains for URL allow-list.
            allow_http: Whether to allow plain HTTP URLs.
        """
        self.xxe_guard = XXEGuard()
        self.entity_limits_guard = EntityLimitsGuard(
            max_expansions=max_entity_expansions,
        )
        self.zip_guard = ZipGuard(
            max_uncompressed=max_zip_uncompressed,
            max_ratio=max_zip_ratio,
            max_files=max_zip_files,
        )
        self.url_allowlist = URLAllowList(
            allowed_domains=allowed_domains,
            allow_http=allow_http,
        )
        self._log = logger.bind(component="security_guard")
        self._log.info("security_guard_initialized")

    # -- XXE delegation --

    def create_safe_parser(self) -> etree.XMLParser:
        """Create an XXE-safe XML parser."""
        return self.xxe_guard.create_safe_parser()

    def safe_parse(
        self,
        source: str | bytes,
        parser: etree.XMLParser | None = None,
    ) -> etree._ElementTree:
        """Parse XML with XXE protection."""
        return self.xxe_guard.safe_parse(source, parser=parser)

    def safe_fromstring(self, text: bytes) -> etree._Element:
        """Parse XML bytes with XXE protection."""
        return self.xxe_guard.safe_fromstring(text)

    def check_for_xxe(self, content: bytes) -> None:
        """Scan content for XXE indicators."""
        self.xxe_guard.check_for_xxe(content)

    # -- Entity limits delegation --

    def check_expansion(self, expansion_count: int) -> None:
        """Check entity expansion count against limits."""
        self.entity_limits_guard.check_expansion(expansion_count)

    # -- ZIP delegation --

    def validate_zip(self, zip_path: str) -> ZipValidationResult:
        """Validate a ZIP archive for safety."""
        return self.zip_guard.validate_zip(zip_path)

    def safe_extract(self, zip_path: str, dest: str) -> list[str]:
        """Safely extract a ZIP archive."""
        return self.zip_guard.safe_extract(zip_path, dest)

    # -- URL delegation --

    def check_url(self, url: str) -> None:
        """Check a URL against the allow-list."""
        self.url_allowlist.check_url(url)

    def is_url_allowed(self, url: str) -> bool:
        """Check if a URL is allowed without raising."""
        return self.url_allowlist.is_allowed(url)


__all__ = [
    "SecurityGuard",
    "XXEGuard",
    "EntityLimitsGuard",
    "ZipGuard",
    "ZipValidationResult",
    "URLAllowList",
]
