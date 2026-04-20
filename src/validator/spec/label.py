"""Label linkbase validator.

Implements 5 checks (LBL-0001 through LBL-0005) covering the
XBRL 2.1 label linkbase specification requirements.

Spec references:
- XBRL 2.1 §5.2.2.1 (label relationships)
- XBRL 2.1 §5.2.2.2 (label roles)
- XBRL 2.1 §5.2.2.3 (label language)
"""

from __future__ import annotations

import logging
from collections import defaultdict

from src.core.model.xbrl_model import (
    ArcModel,
    ConceptDefinition,
    ValidationMessage,
    XBRLInstance,
)
from src.core.types import Severity
from src.validator.base import BaseValidator

logger = logging.getLogger(__name__)

# Standard label roles
_STANDARD_LABEL = "http://www.xbrl.org/2003/role/label"
_TERSE_LABEL = "http://www.xbrl.org/2003/role/terseLabel"
_VERBOSE_LABEL = "http://www.xbrl.org/2003/role/verboseLabel"
_DOCUMENTATION = "http://www.xbrl.org/2003/role/documentation"

_STANDARD_ROLES: set[str] = {
    _STANDARD_LABEL, _TERSE_LABEL, _VERBOSE_LABEL, _DOCUMENTATION,
    "http://www.xbrl.org/2003/role/positiveLabel",
    "http://www.xbrl.org/2003/role/positiveTerseLabel",
    "http://www.xbrl.org/2003/role/positiveVerboseLabel",
    "http://www.xbrl.org/2003/role/negativeLabel",
    "http://www.xbrl.org/2003/role/negativeTerseLabel",
    "http://www.xbrl.org/2003/role/negativeVerboseLabel",
    "http://www.xbrl.org/2003/role/zeroLabel",
    "http://www.xbrl.org/2003/role/zeroTerseLabel",
    "http://www.xbrl.org/2003/role/zeroVerboseLabel",
    "http://www.xbrl.org/2003/role/totalLabel",
    "http://www.xbrl.org/2003/role/periodStartLabel",
    "http://www.xbrl.org/2003/role/periodEndLabel",
}


class LabelValidator(BaseValidator):
    """Validator for XBRL 2.1 label linkbase rules.

    Implements 5 checks covering label completeness, role validity,
    duplicate detection, and language requirements.
    """

    def __init__(self, instance: XBRLInstance) -> None:
        super().__init__(instance)

    def validate(self) -> list[ValidationMessage]:
        """Run all 5 label linkbase checks and return messages."""
        self._messages.clear()

        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return []

        checks = [
            self._check_0001_missing_standard_label,
            self._check_0002_invalid_label_role,
            self._check_0003_duplicate_label,
            self._check_0004_empty_label,
            self._check_0005_missing_label_language,
        ]
        for check in checks:
            try:
                check()
            except Exception:
                self._logger.exception("Check %s failed unexpectedly", check.__name__)
        return list(self._messages)

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_0001_missing_standard_label(self) -> None:
        """LBL-0001: Concept has no standard (default) label.

        Spec: XBRL 2.1 §5.2.2.1 – every non-abstract concept SHOULD
        have at least a standard label in the primary language.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for qname, cdef in taxonomy.concepts.items():
            if cdef.abstract:
                continue
            labels = cdef.labels
            if not labels or _STANDARD_LABEL not in labels:
                self.warning(
                    "LBL-0001",
                    f"Concept '{qname}' has no standard label",
                    concept=qname,
                )

    def _check_0002_invalid_label_role(self) -> None:
        """LBL-0002: Label uses an undeclared or invalid role.

        Spec: XBRL 2.1 §5.2.2.2 – label roles MUST be declared in
        the DTS or be one of the standard XBRL roles.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for qname, cdef in taxonomy.concepts.items():
            for role in cdef.labels:
                if role not in _STANDARD_ROLES and role not in taxonomy.role_types:
                    self.warning(
                        "LBL-0002",
                        f"Concept '{qname}' uses undeclared label role "
                        f"'{role}'",
                        concept=qname,
                    )

    def _check_0003_duplicate_label(self) -> None:
        """LBL-0003: Duplicate label for same concept, role, and language.

        Spec: XBRL 2.1 §5.2.2.1 – a concept SHOULD NOT have more
        than one label for the same role and language combination.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        # Label linkbase arcs
        for lb in taxonomy.label_linkbases:
            seen: set[tuple[str, str, str]] = set()
            for arc in lb.arcs:
                # Approximate: arc.to_concept could encode role+lang
                key = (arc.from_concept, arc.arcrole, arc.to_concept)
                if key in seen:
                    self.warning(
                        "LBL-0003",
                        f"Duplicate label arc from '{arc.from_concept}' "
                        f"to '{arc.to_concept}'",
                        concept=arc.from_concept,
                    )
                seen.add(key)

    def _check_0004_empty_label(self) -> None:
        """LBL-0004: Label text is empty or whitespace-only.

        Spec: XBRL 2.1 §5.2.2.1 – label content SHOULD be
        non-empty and meaningful.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for qname, cdef in taxonomy.concepts.items():
            for role, lang_map in cdef.labels.items():
                for lang, text in lang_map.items():
                    if not text or not text.strip():
                        self.warning(
                            "LBL-0004",
                            f"Concept '{qname}' has empty label for role "
                            f"'{role}', language '{lang}'",
                            concept=qname,
                        )

    def _check_0005_missing_label_language(self) -> None:
        """LBL-0005: Label is missing xml:lang attribute.

        Spec: XBRL 2.1 §5.2.2.3 – every label MUST have an
        ``xml:lang`` attribute.
        """
        taxonomy = self._instance.taxonomy
        if taxonomy is None:
            return
        for qname, cdef in taxonomy.concepts.items():
            for role, lang_map in cdef.labels.items():
                for lang in lang_map:
                    if not lang or not lang.strip():
                        self.error(
                            "LBL-0005",
                            f"Concept '{qname}' has a label with missing "
                            f"language for role '{role}'",
                            concept=qname,
                        )
