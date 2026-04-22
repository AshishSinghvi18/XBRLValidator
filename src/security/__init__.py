"""Security guards for the XBRL Validator.

Re-exports the primary guard classes so consumers can write::

    from src.security import XXEGuard, ZipGuard, URLAllowList, EntityExpansionGuard
"""

from src.security.entity_limits import EntityExpansionGuard
from src.security.url_allowlist import URLAllowList
from src.security.xxe_guard import XXEGuard
from src.security.zip_guard import ZipCheckResult, ZipGuard

__all__ = [
    "EntityExpansionGuard",
    "URLAllowList",
    "XXEGuard",
    "ZipCheckResult",
    "ZipGuard",
]
