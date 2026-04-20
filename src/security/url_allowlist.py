"""URL allow-list for SSRF prevention.

Restricts outbound requests (e.g. taxonomy fetches) to a set of known-good
XBRL-related domains and blocks connections to private/internal IP ranges.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import FrozenSet, Iterable, Optional, Set
from urllib.parse import urlparse

from src.core.exceptions import SSRFError

# Canonical XBRL taxonomy hosts recognised by major filing programmes.
_DEFAULT_ALLOWED_DOMAINS: FrozenSet[str] = frozenset(
    {
        "xbrl.fasb.org",
        "xbrl.ifrs.org",
        "xbrl.sec.gov",
        "www.xbrl.org",
        "ferc.gov",
        "www.esma.europa.eu",
        "xbrl.frc.org.uk",
        "cipc.co.za",
        "mca.gov.in",
    }
)


class URLAllowList:
    """Domain-based URL allow-list with private-IP blocking.

    Args:
        allowed_domains:  Iterable of domain strings.  Defaults to the
            canonical XBRL taxonomy hosts.
        allow_subdomains: When ``True`` (default), ``sub.example.org`` is
            accepted when ``example.org`` is in the list.
        block_private_ips: When ``True`` (default), resolved IP addresses
            are checked against RFC 1918 / RFC 4193 private ranges.
    """

    def __init__(
        self,
        allowed_domains: Optional[Iterable[str]] = None,
        *,
        allow_subdomains: bool = True,
        block_private_ips: bool = True,
    ) -> None:
        self._domains: Set[str] = set(
            d.lower().strip()
            for d in (allowed_domains if allowed_domains is not None else _DEFAULT_ALLOWED_DOMAINS)
        )
        self.allow_subdomains = allow_subdomains
        self.block_private_ips = block_private_ips

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_allowed(self, url: str) -> bool:
        """Return ``True`` if *url* passes domain and IP checks."""
        try:
            self.check_url(url)
        except SSRFError:
            return False
        return True

    def check_url(self, url: str) -> None:
        """Validate *url* against the allow-list.

        Args:
            url: The URL to validate.

        Raises:
            SSRFError: If the URL's host is not allowed or resolves to a
                private IP address.
        """
        parsed = urlparse(url)
        scheme = (parsed.scheme or "").lower()

        if scheme not in ("http", "https"):
            raise SSRFError(
                message=f"URL scheme {scheme!r} is not allowed (must be http or https)",
                context={"url": url, "scheme": scheme},
            )

        host = (parsed.hostname or "").lower().strip(".")
        if not host:
            raise SSRFError(
                message="URL has no hostname",
                context={"url": url},
            )

        # Block private IPs when enabled.
        if self.block_private_ips and self._host_is_private(host):
            raise SSRFError(
                message=f"URL host {host!r} resolves to a private/internal address",
                context={"url": url, "host": host},
            )

        # Domain allow-list check.
        if not self._domain_matches(host):
            raise SSRFError(
                message=f"Domain {host!r} is not in the URL allow-list",
                context={"url": url, "host": host},
            )

    def add_domain(self, domain: str) -> None:
        """Add a domain to the allow-list at runtime.

        Args:
            domain: Domain name to allow (e.g. ``"example.org"``).
        """
        self._domains.add(domain.lower().strip())

    def is_private_ip(self, host: str) -> bool:
        """Return ``True`` if *host* is or resolves to a private IP.

        Args:
            host: A hostname or IP address string.
        """
        return self._host_is_private(host)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _domain_matches(self, host: str) -> bool:
        """Check whether *host* matches an allowed domain."""
        if host in self._domains:
            return True

        if self.allow_subdomains:
            for domain in self._domains:
                if host.endswith("." + domain):
                    return True

        return False

    @staticmethod
    def _host_is_private(host: str) -> bool:
        """Determine if *host* is a private/reserved IP address.

        If *host* is a hostname (not an IP literal), DNS resolution is
        attempted.  Resolution failure is treated as private (fail-closed).
        """
        addrs: list[str] = []

        # Try treating it as an IP literal first.
        try:
            ipaddress.ip_address(host)
            addrs.append(host)
        except ValueError:
            # It's a hostname – resolve it.
            try:
                infos = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
                addrs.extend(info[4][0] for info in infos)
            except (socket.gaierror, OSError):
                # Cannot resolve – fail closed.
                return True

        for addr_str in addrs:
            try:
                addr = ipaddress.ip_address(addr_str)
            except ValueError:
                continue

            if (
                addr.is_private
                or addr.is_loopback
                or addr.is_reserved
                or addr.is_link_local
                or addr.is_multicast
                or addr.is_unspecified
            ):
                return True

        return False
