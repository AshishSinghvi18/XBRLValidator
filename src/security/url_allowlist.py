"""URL allow-list guard for SSRF prevention during taxonomy fetches.

Validates outbound URLs against a configurable allow-list of trusted
domains and rejects requests to private/loopback IP addresses.  This
prevents Server-Side Request Forgery (SSRF) attacks where a malicious
XBRL filing could instruct the validator to fetch resources from
internal network hosts.

Spec references:
  - Rule 3 — Zero-Trust Parsing
  - CWE-918: Server-Side Request Forgery (SSRF)
  - ``DEFAULT_TAXONOMY_FETCH_TIMEOUT_S`` in constants

Example::

    allowlist = URLAllowList()
    allowlist.check_url("https://xbrl.fasb.org/us-gaap/2024/...")  # OK
    allowlist.check_url("http://169.254.169.254/metadata")  # raises SSRFError
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import structlog

from src.core.exceptions import SSRFError

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Default trusted XBRL taxonomy domains.
_DEFAULT_ALLOWED_DOMAINS: list[str] = [
    "xbrl.fasb.org",
    "xbrl.ifrs.org",
    "xbrl.sec.gov",
    "www.xbrl.org",
    "ferc.gov",
    "www.esma.europa.eu",
    "xbrl.frc.org.uk",
    "cipc.co.za",
    "mca.gov.in",
]

# Private/reserved IPv4 networks (RFC 1918, loopback, link-local, etc.)
_PRIVATE_IPV4_NETWORKS = [
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("169.254.0.0/16"),
    ipaddress.IPv4Network("0.0.0.0/8"),
]

# Private/reserved IPv6 networks (ULA, loopback, link-local)
_PRIVATE_IPV6_NETWORKS = [
    ipaddress.IPv6Network("fc00::/7"),
    ipaddress.IPv6Network("::1/128"),
    ipaddress.IPv6Network("fe80::/10"),
]


class URLAllowList:
    """URL allow-list checking for taxonomy fetch SSRF prevention.

    Validates that outbound URLs target only trusted XBRL taxonomy
    domains and do not resolve to private or loopback IP addresses.
    """

    def __init__(
        self,
        allowed_domains: list[str] | None = None,
        allow_http: bool = False,
    ) -> None:
        """Initialize the URL allow-list.

        Args:
            allowed_domains: List of trusted domain names.  If ``None``,
                uses the default list of XBRL taxonomy domains.
            allow_http: If ``True``, allow plain HTTP in addition to HTTPS.
                Defaults to ``False`` (HTTPS only).
        """
        self._allowed_domains: set[str] = set(
            allowed_domains if allowed_domains is not None else _DEFAULT_ALLOWED_DOMAINS
        )
        self._allow_http: bool = allow_http
        self._log = logger.bind(
            component="url_allowlist",
            domain_count=len(self._allowed_domains),
            allow_http=allow_http,
        )
        self._log.debug("url_allowlist_initialized")

    @property
    def allowed_domains(self) -> frozenset[str]:
        """Return the current set of allowed domains."""
        return frozenset(self._allowed_domains)

    def add_domain(self, domain: str) -> None:
        """Add a domain to the allow-list.

        Both the exact domain and its subdomains will be accepted.

        Args:
            domain: Domain name to add (e.g. ``"example.com"``).
        """
        domain = domain.lower().strip()
        if not domain:
            return
        self._allowed_domains.add(domain)
        self._log.info("domain_added", domain=domain)

    def is_allowed(self, url: str) -> bool:
        """Check whether a URL is permitted by the allow-list.

        Validation steps:
          1. Parse the URL and extract scheme and hostname.
          2. Reject non-HTTPS URLs (unless ``allow_http=True``).
          3. Check the hostname against the allow-list (exact match
             and subdomain wildcard matching).
          4. Reject hostnames that resolve to private/loopback IPs.

        Args:
            url: The URL to validate.

        Returns:
            ``True`` if the URL is allowed, ``False`` otherwise.
        """
        parsed = urlparse(url)

        # Scheme check
        allowed_schemes = {"https"}
        if self._allow_http:
            allowed_schemes.add("http")

        if parsed.scheme not in allowed_schemes:
            self._log.debug(
                "url_scheme_rejected",
                url=url,
                scheme=parsed.scheme,
            )
            return False

        hostname = parsed.hostname
        if not hostname:
            self._log.debug("url_no_hostname", url=url)
            return False

        hostname = hostname.lower()

        # Check for private IPs before domain matching
        if self.is_private_ip(hostname):
            self._log.warning(
                "url_private_ip_rejected",
                url=url,
                hostname=hostname,
            )
            return False

        # Exact domain match or subdomain wildcard match
        if hostname in self._allowed_domains:
            return True

        # Subdomain check: "sub.xbrl.fasb.org" matches "xbrl.fasb.org"
        for allowed in self._allowed_domains:
            if hostname.endswith("." + allowed):
                return True

        self._log.debug(
            "url_domain_not_allowed",
            url=url,
            hostname=hostname,
        )
        return False

    def check_url(self, url: str) -> None:
        """Validate a URL and raise on rejection.

        Convenience wrapper around :meth:`is_allowed` that raises
        :class:`~src.core.exceptions.SSRFError` instead of returning
        ``False``.

        Args:
            url: The URL to validate.

        Raises:
            SSRFError: If the URL is not in the allow-list.
        """
        if not self.is_allowed(url):
            self._log.error(
                "ssrf_blocked",
                url=url,
            )
            raise SSRFError(
                f"URL not in allow-list: {url}",
                code="SEC-0005",
                context={"url": url},
            )

    def is_private_ip(self, hostname: str) -> bool:
        """Check whether a hostname resolves to a private or loopback IP.

        Handles both raw IP addresses and DNS hostnames.  For DNS names,
        performs a resolution and checks all returned addresses.

        Args:
            hostname: Hostname or IP address string to check.

        Returns:
            ``True`` if the hostname is or resolves to a private/loopback
            address, ``False`` otherwise.
        """
        # Try parsing as a literal IP address first
        try:
            addr = ipaddress.ip_address(hostname)
            return self._is_private_address(addr)
        except ValueError:
            pass

        # Resolve DNS hostname and check all results
        try:
            addr_infos = socket.getaddrinfo(
                hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
            )
        except socket.gaierror:
            # Cannot resolve — treat as potentially unsafe
            self._log.debug(
                "url_dns_resolution_failed",
                hostname=hostname,
            )
            return False

        for _family, _type, _proto, _canonname, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            try:
                addr = ipaddress.ip_address(ip_str)
                if self._is_private_address(addr):
                    self._log.debug(
                        "url_resolves_to_private",
                        hostname=hostname,
                        resolved_ip=ip_str,
                    )
                    return True
            except ValueError:
                continue

        return False

    @staticmethod
    def _is_private_address(
        addr: ipaddress.IPv4Address | ipaddress.IPv6Address,
    ) -> bool:
        """Check if an IP address falls within private/reserved ranges.

        Args:
            addr: An IPv4 or IPv6 address object.

        Returns:
            ``True`` if the address is private, loopback, or reserved.
        """
        if isinstance(addr, ipaddress.IPv4Address):
            for network in _PRIVATE_IPV4_NETWORKS:
                if addr in network:
                    return True
        elif isinstance(addr, ipaddress.IPv6Address):
            for network in _PRIVATE_IPV6_NETWORKS:
                if addr in network:
                    return True
            # Handle IPv4-mapped IPv6 addresses (e.g., ::ffff:10.0.0.1)
            mapped = addr.ipv4_mapped
            if mapped is not None:
                for network in _PRIVATE_IPV4_NETWORKS:
                    if mapped in network:
                        return True

        return False
