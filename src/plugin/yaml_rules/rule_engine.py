"""YAML-based validation rule engine.

Loads validation rules defined in YAML files and evaluates them against
XBRL instances to produce validation messages.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.core.exceptions import RuleCompileError
from src.core.model.instance import ValidationMessage, XBRLInstance
from src.core.types import Severity

logger = logging.getLogger(__name__)

# Mapping from YAML severity strings to Severity enum values
_SEVERITY_MAP: dict[str, Severity] = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "inconsistency": Severity.INCONSISTENCY,
    "info": Severity.INFO,
}


@dataclass
class YAMLRule:
    """A validation rule defined in YAML.

    Attributes:
        rule_id: Unique identifier for the rule.
        description: Human-readable description of what the rule checks.
        severity: Severity level (error, warning, info, inconsistency).
        condition: A simple check expression evaluated against facts.
        message_template: Template string for the validation message,
            may contain ``{placeholders}`` for fact attributes.
        spec_ref: Reference to the relevant specification section.
        enabled: Whether the rule is active.
        tags: Optional categorisation tags.
    """

    rule_id: str
    description: str
    severity: str
    condition: str
    message_template: str
    spec_ref: str = ""
    enabled: bool = True
    tags: list[str] = field(default_factory=list)


class YAMLRuleEngine:
    """Loads and evaluates YAML-defined validation rules.

    Rules are expressed as declarative checks in YAML and evaluated
    against the facts and metadata of an XBRL instance.
    """

    def load_rules(self, yaml_path: str) -> list[YAMLRule]:
        """Load validation rules from a YAML file.

        Args:
            yaml_path: Path to the YAML rules file.

        Returns:
            A list of parsed :class:`YAMLRule` objects.

        Raises:
            FileNotFoundError: If the YAML file does not exist.
            RuleCompileError: If a rule definition is malformed.
        """
        path = Path(yaml_path)
        if not path.is_file():
            raise FileNotFoundError(f"YAML rules file not found: {yaml_path}")

        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        if not isinstance(data, dict):
            raise RuleCompileError(
                rule_id="<file>",
                reason=f"Expected a mapping at top level in {yaml_path}",
            )

        raw_rules = data.get("rules", [])
        if not isinstance(raw_rules, list):
            raise RuleCompileError(
                rule_id="<file>",
                reason=f"'rules' key must be a list in {yaml_path}",
            )

        rules: list[YAMLRule] = []
        for idx, raw in enumerate(raw_rules):
            if not isinstance(raw, dict):
                raise RuleCompileError(
                    rule_id=f"<rule-{idx}>",
                    reason=f"Rule at index {idx} must be a mapping",
                )
            try:
                rule = YAMLRule(
                    rule_id=raw["id"],
                    description=raw.get("description", ""),
                    severity=raw.get("severity", "error"),
                    condition=raw["condition"],
                    message_template=raw.get("message", "Rule {rule_id} violated"),
                    spec_ref=raw.get("spec_ref", ""),
                    enabled=raw.get("enabled", True),
                    tags=raw.get("tags", []),
                )
                rules.append(rule)
            except KeyError as exc:
                raise RuleCompileError(
                    rule_id=raw.get("id", f"<rule-{idx}>"),
                    reason=f"Missing required field: {exc}",
                ) from exc

        return rules

    def evaluate(
        self,
        rules: list[YAMLRule],
        instance: XBRLInstance,
    ) -> list[ValidationMessage]:
        """Evaluate a list of rules against an XBRL instance.

        Each rule's ``condition`` is evaluated as a simple expression
        against instance-level properties and facts. Supported condition
        types:

        - ``fact_count == 0``: Check fact count.
        - ``no_contexts``: Check that contexts exist.
        - ``missing_schema_ref``: Verify schema references are present.
        - ``concept_required:<qname>``: Require a specific concept.
        - ``max_facts:<n>``: Warn if fact count exceeds a threshold.

        Args:
            rules: Rules to evaluate.
            instance: The XBRL instance to validate.

        Returns:
            A list of :class:`ValidationMessage` for each rule violation.
        """
        messages: list[ValidationMessage] = []

        for rule in rules:
            if not rule.enabled:
                continue

            severity = _SEVERITY_MAP.get(rule.severity, Severity.ERROR)

            violations = self._evaluate_condition(rule, instance)
            for violation_msg in violations:
                messages.append(
                    ValidationMessage(
                        code=rule.rule_id,
                        severity=severity,
                        message=violation_msg,
                        spec_ref=rule.spec_ref,
                        file_path=instance.file_path,
                    )
                )

        return messages

    def _evaluate_condition(
        self,
        rule: YAMLRule,
        instance: XBRLInstance,
    ) -> list[str]:
        """Evaluate a single rule condition against an instance.

        Returns a list of violation messages (empty if rule passes).
        """
        condition = rule.condition.strip()

        # fact_count comparisons
        if condition.startswith("fact_count"):
            return self._eval_fact_count(rule, instance, condition)

        # no_contexts: verify contexts exist
        if condition == "no_contexts":
            if not instance.contexts:
                return [rule.message_template.format(rule_id=rule.rule_id)]
            return []

        # missing_schema_ref: verify at least one schema ref
        if condition == "missing_schema_ref":
            if not instance.schema_refs:
                return [rule.message_template.format(rule_id=rule.rule_id)]
            return []

        # concept_required:<qname>
        if condition.startswith("concept_required:"):
            qname = condition.split(":", 1)[1].strip()
            matching = instance.facts_by_concept(qname)
            if not matching:
                msg = rule.message_template.format(
                    rule_id=rule.rule_id, concept=qname
                )
                return [msg]
            return []

        # max_facts:<n>
        if condition.startswith("max_facts:"):
            try:
                limit = int(condition.split(":", 1)[1].strip())
            except ValueError:
                logger.warning("Invalid max_facts limit in rule %s", rule.rule_id)
                return []
            if instance.fact_count() > limit:
                msg = rule.message_template.format(
                    rule_id=rule.rule_id,
                    fact_count=instance.fact_count(),
                    limit=limit,
                )
                return [msg]
            return []

        logger.warning("Unknown condition type in rule %s: %s", rule.rule_id, condition)
        return []

    def _eval_fact_count(
        self,
        rule: YAMLRule,
        instance: XBRLInstance,
        condition: str,
    ) -> list[str]:
        """Evaluate fact_count comparison conditions."""
        import operator
        import re

        ops: dict[str, Any] = {
            "==": operator.eq,
            "!=": operator.ne,
            ">=": operator.ge,
            "<=": operator.le,
            ">": operator.gt,
            "<": operator.lt,
        }

        match = re.match(r"fact_count\s*(==|!=|>=|<=|>|<)\s*(\d+)", condition)
        if not match:
            logger.warning("Cannot parse fact_count condition: %s", condition)
            return []

        op_str, val_str = match.group(1), match.group(2)
        op_func = ops[op_str]
        threshold = int(val_str)

        if op_func(instance.fact_count(), threshold):
            msg = rule.message_template.format(
                rule_id=rule.rule_id,
                fact_count=instance.fact_count(),
            )
            return [msg]
        return []
