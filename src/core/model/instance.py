"""XBRL instance document — XBRL 2.1 §4.

An :class:`XBRLInstance` is the top-level container that aggregates every
parsed component of a single XBRL filing: contexts, units, facts, and
schema references.  :class:`ValidationMessage` carries structured
diagnostic output produced during validation passes.

References:
    - XBRL 2.1 §4   (instance document)
    - XBRL 2.1 §4.2 (schemaRef)
    - XBRL 2.1 §4.7 (contexts)
    - XBRL 2.1 §4.8 (units)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.model.context import Context
from src.core.model.fact import Fact
from src.core.model.unit import Unit
from src.core.types import InputFormat, Severity


@dataclass
class ValidationMessage:
    """Structured validation diagnostic message.

    Attributes:
        code: Machine-readable error/warning code (e.g.
            ``"xbrl.2.1:calcInconsistency"``).
        severity: Severity level of the message.
        message: Human-readable description.
        spec_ref: Specification section reference (e.g. ``"XBRL 2.1 §5.2.5.2"``).
        file_path: Path or URL of the source document.
        line: 1-based source line number, if available.
        column: 1-based source column number, if available.
        fix_suggestion: Optional suggestion for correcting the issue.

    References:
        - XBRL 2.1 Appendix B (error codes)
    """

    code: str
    severity: Severity
    message: str
    spec_ref: str = ""
    file_path: str = ""
    line: int | None = None
    column: int | None = None
    fix_suggestion: str = ""


@dataclass
class XBRLInstance:
    """Top-level XBRL instance document model — XBRL 2.1 §4.

    Attributes:
        file_path: Path or URL of the source document.
        input_format: Detected input format (XBRL XML, iXBRL, JSON, …).
        schema_refs: List of ``schemaRef`` href values — XBRL 2.1 §4.2.
        contexts: Mapping of context ID → :class:`Context`.
        units: Mapping of unit ID → :class:`Unit`.
        facts: Ordered list of parsed :class:`Fact` objects.
        footnotes: Simplified footnote storage (list of attribute dicts).
        namespace_map: Prefix → namespace-URI map populated during
            parsing.  A key of ``None`` represents the default namespace.

    References:
        - XBRL 2.1 §4
    """

    file_path: str
    input_format: InputFormat
    schema_refs: list[str]
    contexts: dict[str, Context]
    units: dict[str, Unit]
    facts: list[Fact]
    footnotes: list[dict[str, str]]
    namespace_map: dict[str | None, str] = field(default_factory=dict)

    def fact_count(self) -> int:
        """Return the total number of facts in this instance.

        Returns:
            Integer count of facts.

        References:
            - XBRL 2.1 §4.6
        """
        return len(self.facts)

    def iter_fact_ids(self) -> list[str]:
        """Return a list of all fact identifiers.

        Returns:
            Ordered list of :pydata:`src.core.types.FactID` strings.

        References:
            - XBRL 2.1 §4.6
        """
        return [f.fact_id for f in self.facts]

    def facts_by_concept(self, qname: str) -> list[Fact]:
        """Return all facts reporting a given concept.

        Args:
            qname: Clark-notation QName of the concept.

        Returns:
            List of matching :class:`Fact` objects (may be empty).

        References:
            - XBRL 2.1 §4.6
        """
        return [f for f in self.facts if f.concept_qname == qname]

    def facts_by_context(self, context_id: str) -> list[Fact]:
        """Return all facts referencing a given context.

        Args:
            context_id: The ``contextRef`` value to match.

        Returns:
            List of matching :class:`Fact` objects (may be empty).

        References:
            - XBRL 2.1 §4.7
        """
        return [f for f in self.facts if f.context_ref == context_id]

    def numeric_facts(self) -> list[Fact]:
        """Return all numeric facts (including fractions).

        Returns:
            List of :class:`Fact` objects where
            :attr:`Fact.is_numeric` is ``True``.

        References:
            - XBRL 2.1 §4.6.3
        """
        return [f for f in self.facts if f.is_numeric]

    def get_context(self, context_id: str) -> Context | None:
        """Look up a context by its ID.

        Args:
            context_id: The context ``id`` attribute value.

        Returns:
            The :class:`Context` if found, otherwise ``None``.

        References:
            - XBRL 2.1 §4.7
        """
        return self.contexts.get(context_id)

    def get_unit(self, unit_id: str) -> Unit | None:
        """Look up a unit by its ID.

        Args:
            unit_id: The unit ``id`` attribute value.

        Returns:
            The :class:`Unit` if found, otherwise ``None``.

        References:
            - XBRL 2.1 §4.8
        """
        return self.units.get(unit_id)
