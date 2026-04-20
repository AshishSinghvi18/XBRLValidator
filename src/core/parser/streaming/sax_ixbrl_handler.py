"""Streaming handler for large iXBRL HTML documents.

Parses iXBRL HTML documents larger than the DOM threshold using
``lxml.etree.iterparse`` with memory cleanup, extracting inline
XBRL facts, contexts, and units while maintaining O(1) memory
usage.

Spec references:
- Inline XBRL 1.1 §4–8
- lxml iterparse documentation
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from lxml import etree

from src.core.constants import NS_IX, NS_LINK, NS_XBRLI, NS_XLINK, NS_XSI
from src.core.parser.streaming.fact_index import FactReference
from src.core.parser.streaming.fact_store import FactStore
from src.core.parser.streaming.memory_budget import MemoryBudget
from src.core.parser.streaming.sax_handler import (
    CountingFileWrapper,
    StreamingParseResult,
)
from src.core.parser.transform_registry import TransformRegistry
from src.core.parser.xml_parser import (
    LinkbaseRef,
    RawContext,
    RawUnit,
    SchemaRef,
)
from src.utils.xml_utils import get_namespace, strip_namespace

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Clark-notation constants
# ---------------------------------------------------------------------------

_IX_HEADER = f"{{{NS_IX}}}header"
_IX_REFERENCES = f"{{{NS_IX}}}references"
_IX_RESOURCES = f"{{{NS_IX}}}resources"
_IX_HIDDEN = f"{{{NS_IX}}}hidden"
_IX_NON_FRACTION = f"{{{NS_IX}}}nonFraction"
_IX_NON_NUMERIC = f"{{{NS_IX}}}nonNumeric"
_IX_FRACTION = f"{{{NS_IX}}}fraction"
_IX_TUPLE = f"{{{NS_IX}}}tuple"
_IX_CONTINUATION = f"{{{NS_IX}}}continuation"
_IX_EXCLUDE = f"{{{NS_IX}}}exclude"

_XBRLI_CONTEXT = f"{{{NS_XBRLI}}}context"
_XBRLI_UNIT = f"{{{NS_XBRLI}}}unit"
_LINK_SCHEMA_REF = f"{{{NS_LINK}}}schemaRef"
_LINK_LINKBASE_REF = f"{{{NS_LINK}}}linkbaseRef"

_IX_FACT_TAGS = frozenset({
    _IX_NON_FRACTION,
    _IX_NON_NUMERIC,
    _IX_FRACTION,
    _IX_TUPLE,
})


class IXBRLStreamingHandler:
    """Streaming handler for large iXBRL HTML documents.

    Uses ``lxml.etree.iterparse`` to process iXBRL HTML documents
    that exceed the DOM threshold. Extracts ix:header content
    (contexts, units, schemaRefs) and inline facts (ix:nonFraction,
    ix:nonNumeric) while maintaining constant memory usage.

    Parameters
    ----------
    file_path:
        Path to the iXBRL HTML file.
    fact_store:
        ``FactStore`` to hold parsed fact references.
    budget:
        ``MemoryBudget`` for memory tracking.
    transform_registry:
        Optional transform registry. If ``None``, a default registry
        with built-in transforms is created.
    """

    def __init__(
        self,
        file_path: str,
        fact_store: FactStore,
        budget: MemoryBudget,
        transform_registry: TransformRegistry | None = None,
    ) -> None:
        self._file_path = file_path
        self._fact_store = fact_store
        self._budget = budget
        self._transforms = transform_registry or TransformRegistry()
        self._fact_index = 0
        self._continuations: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self) -> StreamingParseResult:
        """Parse a large iXBRL HTML file using iterparse.

        Handles ix:header (contexts, units), ix:nonFraction,
        ix:nonNumeric, and continuation chains.

        Returns
        -------
        StreamingParseResult
        """
        result = StreamingParseResult(fact_store=self._fact_store)
        start_time = time.monotonic()

        file_size = os.path.getsize(self._file_path)
        result.total_bytes_scanned = file_size

        counting_wrapper = CountingFileWrapper(self._file_path)

        try:
            # Try XML-mode iterparse first (preserves namespaces)
            self._iterparse_xml(counting_wrapper, result)
        except etree.XMLSyntaxError:
            # Fall back: re-open and try with recovery mode
            counting_wrapper.close()
            counting_wrapper = CountingFileWrapper(self._file_path)
            try:
                self._iterparse_recovery(counting_wrapper, result)
            except Exception as exc:  # noqa: BLE001
                result.parse_errors.append(
                    f"Failed to parse iXBRL in recovery mode: {exc}"
                )
        except Exception as exc:  # noqa: BLE001
            result.parse_errors.append(f"Unexpected parse error: {exc}")
        finally:
            counting_wrapper.close()

        result.total_facts = self._fact_store.count
        result.elapsed_seconds = time.monotonic() - start_time
        result.spill_occurred = (
            self._fact_store.storage_mode.value != "in_memory"
        )

        logger.info(
            "iXBRL streaming parse complete: %s facts in %.2fs (%s bytes)",
            result.total_facts,
            result.elapsed_seconds,
            result.total_bytes_scanned,
        )

        return result

    # ------------------------------------------------------------------
    # Iterparse strategies
    # ------------------------------------------------------------------

    def _iterparse_xml(
        self,
        wrapper: CountingFileWrapper,
        result: StreamingParseResult,
    ) -> None:
        """Parse using strict XML iterparse (namespace-aware)."""
        context = etree.iterparse(
            wrapper,
            events=("start", "end"),
            resolve_entities=False,
            no_network=True,
            huge_tree=True,
            recover=False,
        )

        in_header = False
        header_depth = 0
        root_elem: Optional[etree._Element] = None

        for event, elem in context:
            if not isinstance(elem.tag, str):
                continue

            if event == "start":
                if root_elem is None:
                    root_elem = elem
                    nsmap = elem.nsmap if elem.nsmap else {}
                    for prefix, uri in nsmap.items():
                        if prefix is None:
                            result.namespaces[""] = uri
                        else:
                            result.namespaces[prefix] = uri

                if elem.tag == _IX_HEADER:
                    in_header = True
                    header_depth = 0

                if in_header:
                    header_depth += 1
                continue

            # event == "end"
            if in_header:
                header_depth -= 1
                if elem.tag == _IX_HEADER:
                    in_header = False

            try:
                self._process_element(elem, result, wrapper, in_header)
            except Exception as exc:  # noqa: BLE001
                result.parse_errors.append(
                    f"Error at byte {wrapper.bytes_read}: {exc}"
                )

            # Clean up elements that are not part of the header
            # (header elements need their children for context/unit extraction)
            if not in_header:
                elem.clear()
                parent = elem.getparent()
                if parent is not None:
                    try:
                        parent.remove(elem)
                    except ValueError:
                        pass

    def _iterparse_recovery(
        self,
        wrapper: CountingFileWrapper,
        result: StreamingParseResult,
    ) -> None:
        """Parse using HTML-tolerant recovery mode."""
        context = etree.iterparse(
            wrapper,
            events=("start", "end"),
            resolve_entities=False,
            no_network=True,
            huge_tree=True,
            recover=True,
        )

        for event, elem in context:
            if not isinstance(elem.tag, str):
                continue

            if event == "start":
                # Collect namespaces from first element
                if not result.namespaces and elem.nsmap:
                    for prefix, uri in elem.nsmap.items():
                        if prefix is None:
                            result.namespaces[""] = uri
                        else:
                            result.namespaces[prefix] = uri
                continue

            try:
                self._process_element(elem, result, wrapper, False)
            except Exception as exc:  # noqa: BLE001
                result.parse_errors.append(
                    f"Error at byte {wrapper.bytes_read}: {exc}"
                )

            elem.clear()
            parent = elem.getparent()
            if parent is not None:
                try:
                    parent.remove(elem)
                except ValueError:
                    pass

    # ------------------------------------------------------------------
    # Element processing
    # ------------------------------------------------------------------

    def _process_element(
        self,
        elem: etree._Element,
        result: StreamingParseResult,
        wrapper: CountingFileWrapper,
        in_header: bool,
    ) -> None:
        """Route an element to the appropriate handler."""
        tag = elem.tag

        # Header elements
        if tag == _XBRLI_CONTEXT:
            self._handle_context(elem, result)
        elif tag == _XBRLI_UNIT:
            self._handle_unit(elem, result)
        elif tag == _LINK_SCHEMA_REF:
            href = elem.get(f"{{{NS_XLINK}}}href", "")
            result.schema_refs.append(SchemaRef(href=href))
        elif tag == _LINK_LINKBASE_REF:
            href = elem.get(f"{{{NS_XLINK}}}href", "")
            role = elem.get(f"{{{NS_XLINK}}}role", "")
            arcrole = elem.get(f"{{{NS_XLINK}}}arcrole", "")
            result.linkbase_refs.append(
                LinkbaseRef(href=href, role=role, arcrole=arcrole)
            )
        elif tag == _IX_CONTINUATION:
            cont_id = elem.get("id", "")
            if cont_id:
                text = self._get_text_content(elem)
                self._continuations[cont_id] = text
        elif tag in _IX_FACT_TAGS:
            self._handle_inline_fact(elem, result, wrapper)

    # -- context / unit --------------------------------------------------

    @staticmethod
    def _handle_context(
        elem: etree._Element, result: StreamingParseResult
    ) -> None:
        ctx_id = elem.get("id", "")
        if not ctx_id:
            return

        ctx = RawContext(id=ctx_id)

        entity = elem.find(f"{{{NS_XBRLI}}}entity")
        if entity is not None:
            ident = entity.find(f"{{{NS_XBRLI}}}identifier")
            if ident is not None:
                ctx.entity_scheme = ident.get("scheme", "")
                ctx.entity_id = (ident.text or "").strip()

        period = elem.find(f"{{{NS_XBRLI}}}period")
        if period is not None:
            instant = period.find(f"{{{NS_XBRLI}}}instant")
            forever = period.find(f"{{{NS_XBRLI}}}forever")
            start = period.find(f"{{{NS_XBRLI}}}startDate")
            end = period.find(f"{{{NS_XBRLI}}}endDate")

            if instant is not None:
                ctx.period_type = "instant"
                ctx.instant = (instant.text or "").strip()
            elif forever is not None:
                ctx.period_type = "forever"
            elif start is not None and end is not None:
                ctx.period_type = "duration"
                ctx.start_date = (start.text or "").strip()
                ctx.end_date = (end.text or "").strip()

        result.contexts[ctx_id] = ctx

    @staticmethod
    def _handle_unit(
        elem: etree._Element, result: StreamingParseResult
    ) -> None:
        unit_id = elem.get("id", "")
        if not unit_id:
            return

        unit = RawUnit(id=unit_id)
        divide = elem.find(f"{{{NS_XBRLI}}}divide")
        if divide is not None:
            num = divide.find(f"{{{NS_XBRLI}}}unitNumerator")
            den = divide.find(f"{{{NS_XBRLI}}}unitDenominator")
            if num is not None:
                unit.divide_numerator = [
                    (m.text or "").strip()
                    for m in num.findall(f"{{{NS_XBRLI}}}measure")
                ]
            if den is not None:
                unit.divide_denominator = [
                    (m.text or "").strip()
                    for m in den.findall(f"{{{NS_XBRLI}}}measure")
                ]
        else:
            unit.measures = [
                (m.text or "").strip()
                for m in elem.findall(f"{{{NS_XBRLI}}}measure")
            ]

        result.units[unit_id] = unit

    # -- inline fact -----------------------------------------------------

    def _handle_inline_fact(
        self,
        elem: etree._Element,
        result: StreamingParseResult,
        wrapper: CountingFileWrapper,
    ) -> None:
        """Extract an inline fact and add to the FactStore."""
        tag = elem.tag
        context_ref = elem.get("contextRef", "")
        if not context_ref and tag not in (_IX_TUPLE,):
            return

        # Resolve concept name
        name_attr = elem.get("name", "")
        concept = self._resolve_name(name_attr, elem, result)

        unit_ref = elem.get("unitRef")
        is_numeric = tag in (_IX_NON_FRACTION, _IX_FRACTION) or unit_ref is not None

        nil_val = elem.get(f"{{{NS_XSI}}}nil", elem.get("nil", "false"))
        is_nil = nil_val.lower() in ("true", "1")

        # Get display value and apply transform
        display_value = self._get_text_content(elem) if not is_nil else ""
        format_attr = elem.get("format")

        xbrl_value = display_value
        if format_attr and not is_nil and display_value:
            xbrl_value, err = self._transforms.apply_transform(
                format_attr, display_value
            )
            if err:
                result.parse_errors.append(
                    f"Transform error for fact '{name_attr}': {err}"
                )

        # Apply scale
        scale = elem.get("scale")
        if scale and not is_nil and xbrl_value:
            xbrl_value = self._apply_scale(xbrl_value, scale)

        # Apply sign
        sign = elem.get("sign")
        if sign == "-" and not is_nil and xbrl_value:
            if xbrl_value.startswith("-"):
                xbrl_value = xbrl_value[1:]
            else:
                xbrl_value = f"-{xbrl_value}"

        value_bytes = xbrl_value.encode("utf-8")
        byte_offset = max(0, wrapper.bytes_read - len(value_bytes) - 100)

        ref = FactReference(
            index=self._fact_index,
            concept=concept,
            context_ref=context_ref,
            unit_ref=unit_ref,
            byte_offset=byte_offset,
            value_length=len(value_bytes),
            is_numeric=is_numeric,
            is_nil=is_nil,
            decimals=elem.get("decimals"),
            precision=elem.get("precision"),
            id=elem.get("id"),
            source_line=elem.sourceline or 0,
        )

        self._fact_store.add(ref)
        self._fact_index += 1

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_name(
        name_attr: str,
        elem: etree._Element,
        result: StreamingParseResult,
    ) -> str:
        """Resolve an iXBRL ``@name`` attribute to Clark notation."""
        if not name_attr:
            return ""

        if ":" in name_attr:
            prefix, local = name_attr.split(":", maxsplit=1)
            ns_uri = ""
            if hasattr(elem, "nsmap") and elem.nsmap:
                ns_uri = elem.nsmap.get(prefix, "")
            if not ns_uri:
                ns_uri = result.namespaces.get(prefix, "")
            if ns_uri:
                return f"{{{ns_uri}}}{local}"

        return name_attr

    @staticmethod
    def _get_text_content(elem: etree._Element) -> str:
        """Get text content excluding ix:exclude elements."""
        parts: list[str] = []
        if elem.text:
            parts.append(elem.text)

        for child in elem:
            if isinstance(child.tag, str) and child.tag == _IX_EXCLUDE:
                if child.tail:
                    parts.append(child.tail)
            else:
                child_text = etree.tostring(
                    child, method="text", encoding="unicode"
                )
                if child_text:
                    parts.append(child_text)
                if child.tail:
                    parts.append(child.tail)

        return "".join(parts).strip()

    @staticmethod
    def _apply_scale(value: str, scale: str) -> str:
        """Apply a scale factor to a numeric value."""
        try:
            from decimal import Decimal

            dec = Decimal(value)
            multiplier = Decimal(10) ** int(scale)
            return str((dec * multiplier).normalize())
        except Exception:  # noqa: BLE001
            return value
