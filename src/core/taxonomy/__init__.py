"""XBRL taxonomy resolution and caching.

Provides:
- :class:`XMLCatalog` – OASIS XML Catalog resolver
- :class:`TaxonomyCache` – multi-level taxonomy cache
- :class:`TaxonomyPackage` / :class:`PackageLoader` – taxonomy package handling
- :class:`TaxonomyResolver` – DTS discovery algorithm
- :class:`ConceptIndex` – fast concept lookup index
"""

from src.core.taxonomy.cache import TaxonomyCache
from src.core.taxonomy.catalog import XMLCatalog
from src.core.taxonomy.concept_index import ConceptIndex
from src.core.taxonomy.package import PackageLoader, TaxonomyPackage
from src.core.taxonomy.resolver import TaxonomyResolver

__all__ = [
    "ConceptIndex",
    "PackageLoader",
    "TaxonomyCache",
    "TaxonomyPackage",
    "TaxonomyResolver",
    "XMLCatalog",
]
