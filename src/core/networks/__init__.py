"""XBRL relationship networks and linkbase parsing.

Re-exports:
    - :class:`Arc`                 — single linkbase arc.
    - :class:`RelationshipNetwork` — directed graph of relationships.
    - :class:`LinkbaseParser`      — linkbase XML parser.
"""

from src.core.networks.linkbase_parser import LinkbaseParser
from src.core.networks.relationship import Arc, RelationshipNetwork

__all__ = [
    "Arc",
    "LinkbaseParser",
    "RelationshipNetwork",
]