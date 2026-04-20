"""SAX/iterparse handler for large XBRL instance XML files.

Parses XBRL XML instance documents larger than the DOM threshold
(typically 100 MB) using ``lxml.etree.iterparse`` with aggressive
memory cleanup to keep resident memory O(1) regardless of file size.

Each parsed fact is stored as a ``FactReference`` in the provided
``FactStore``, which transparently handles in-memory → disk spill
transitions.

Spec references:
- XBRL 2.1 §4 (instance documents)
- lxml iterparse documentation
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from lxml import etree

from src.core.constants import (
    NS_LINK,
    NS_XBRLI,
    NS_XLINK,
    NS_XSI,
)
from src.core.parser.streaming.fact_index import FactReference
from src.core.parser.streaming.fact_store import FactStore
from src.core.parser.streaming.memory_budget import MemoryBudget
from src.core.parser.xml_parser import (
    LinkbaseRef,
    RawContext,
    RawUnit,
    SchemaRef,
)
from src.utils.xml_utils import get_namespace, strip_namespace

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Clark-notation tags (same as xml_parser but duplicated to avoid coupling)
# ---------------------------------------------------------------------------

_XBRLI_XBRL = f"{{{NS_XBRLI}}}xbrl"
_XBRLI_CONTEXT = f"{{{NS_XBRLI}}}context"
_XBRLI_UNIT = f"{{{NS_XBRLI}}}unit"
_XBRLI_ENTITY = f"{{{NS_XBRLI}}}entity"
_XBRLI_IDENTIFIER = f"{{{NS_XBRLI}}}identifier"
_XBRLI_PERIOD = f"{{{NS_XBRLI}}}period"
_XBRLI_INSTANT = f"{{{NS_XBRLI}}}instant"
_XBRLI_START = f"{{{NS_XBRLI}}}startDate"
_XBRLI_END = f"{{{NS_XBRLI}}}endDate"
_XBRLI_FOREVER = f"{{{NS_XBRLI}}}forever"
_XBRLI_SEGMENT = f"{{{NS_XBRLI}}}segment"
_XBRLI_SCENARIO = f"{{{NS_XBRLI}}}scenario"
_XBRLI_MEASURE = f"{{{NS_XBRLI}}}measure"
_XBRLI_DIVIDE = f"{{{NS_XBRLI}}}divide"
_XBRLI_NUMERATOR = f"{{{NS_XBRLI}}}unitNumerator"
_XBRLI_DENOMINATOR = f"{{{NS_XBRLI}}}unitDenominator"

_LINK_SCHEMA_REF = f"{{{NS_LINK}}}schemaRef"
_LINK_LINKBASE_REF = f"{{{NS_LINK}}}linkbaseRef"
_LINK_FOOTNOTE_LINK = f"{{{NS_LINK}}}footnoteLink"

_RESERVED_NAMESPACES = frozenset({NS_XBRLI, NS_LINK, NS_XLINK, NS_XSI})


@dataclass
class StreamingParseResult:
    """Result of streaming parse of an XBRL document.

    Attributes:
        namespaces: Namespace prefix → URI mapping.
        schema_refs: Taxonomy schema references.
        linkbase_refs: Linkbase references.
        contexts: Context id → RawContext mapping.
        units: Unit id → RawUnit mapping.
        fact_store: The FactStore holding all parsed facts.
        parse_errors: Non-fatal error messages.
        total_facts: Total number of facts parsed.
        total_bytes_scanned: Total bytes scanned from the file.
        elapsed_seconds: Wall-clock time for the parse.
        spill_occurred: Whether facts spilled to disk.
    """

    namespaces: dict[str, str] = field(default_factory=dict)
    schema_refs: list[SchemaRef] = field(default_factory=list)
    linkbase_refs: list[LinkbaseRef] = field(default_factory=list)
    contexts: dict[str, RawContext] = field(default_factory=dict)
    units: dict[str, RawUnit] = field(default_factory=dict)
    fact_store: Optional[FactStore] = None
    parse_errors: list[str] = field(default_factory=list)
    total_facts: int = 0
    total_bytes_scanned: int = 0
    elapsed_seconds: float = 0.0
    spill_occurred: bool = False


class CountingFileWrapper:
    """File wrapper that tracks the current read position.

    Wraps a binary file object and counts the total number of bytes
    read, providing an approximate byte offset for elements during
    iterparse.

    Parameters
    ----------
    file_path:
        Path to the file to read.
    """

    def __init__(self, file_path: str) -> None:
        self._fh = open(file_path, "rb")  # noqa: SIM115
        self._bytes_read: int = 0

    @property
    def bytes_read(self) -> int:
        """Total bytes read so far."""
        return self._bytes_read

    def read(self, size: int = -1) -> bytes:
        """Read bytes from the file, tracking the count."""
        data = self._fh.read(size)
        self._bytes_read += len(data)
        return data

    def close(self) -> None:
        """Close the underlying file."""
        self._fh.close()

    def __enter__(self) -> CountingFileWrapper:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class XBRLSAXHandler:
    """SAX/iterparse handler for large XBRL XML instance files.

    Uses ``lxml.etree.iterparse`` with ``("start", "end")`` events
    to process XBRL XML files with O(1) memory usage. After each
    element is processed, ``elem.clear()`` and ``parent.remove(elem)``
    are called to release memory immediately.

    Parameters
    ----------
    file_path:
        Path to the XBRL XML instance file.
    fact_store:
        ``FactStore`` to hold parsed fact references.
    budget:
        ``MemoryBudget`` for memory tracking.
    """

    def __init__(
        self,
        file_path: str,
        fact_store: FactStore,
        budget: MemoryBudget,
    ) -> None:
        self._file_path = file_path
        self._fact_store = fact_store
        self._budget = budget
        self._fact_index = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self) -> StreamingParseResult:
        """Parse a large XBRL XML file using iterparse.

        Uses lxml.etree.iterparse with events=("start","end").
        After processing each top-level child of <xbrli:xbrl>,
        ``elem.clear()`` + ``parent.remove(elem)`` is called to
        keep memory constant.

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
            context = etree.iterparse(
                counting_wrapper,
                events=("start", "end"),
                resolve_entities=False,
                no_network=True,
                huge_tree=True,  # Large files need huge_tree
            )

            root_elem: Optional[etree._Element] = None
            depth = 0

            for event, elem in context:
                if not isinstance(elem.tag, str):
                    continue

                if event == "start":
                    depth += 1
                    if depth == 1:
                        root_elem = elem
                        # Collect namespaces from root
                        nsmap = elem.nsmap if elem.nsmap else {}
                        for prefix, uri in nsmap.items():
                            if prefix is None:
                                result.namespaces[""] = uri
                            else:
                                result.namespaces[prefix] = uri
                    continue

                # event == "end"
                depth -= 1

                # Only process direct children of root (depth == 1 → now 0 after decrement)
                # We process when depth returns to 1 (direct children of xbrl)
                if depth == 1 and root_elem is not None:
                    try:
                        self._process_element(elem, result, counting_wrapper)
                    except Exception as exc:  # noqa: BLE001
                        result.parse_errors.append(
                            f"Error processing element at byte offset "
                            f"{counting_wrapper.bytes_read}: {exc}"
                        )

                    # Critical: free memory
                    elem.clear()
                    if root_elem is not None:
                        try:
                            root_elem.remove(elem)
                        except ValueError:
                            pass

                # For deeper elements that are children of processed elements,
                # cleanup happens through parent's clear()

        except etree.XMLSyntaxError as exc:
            result.parse_errors.append(f"XML syntax error: {exc}")
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
            "Streaming parse complete: %s facts in %.2fs (%s bytes)",
            result.total_facts,
            result.elapsed_seconds,
            result.total_bytes_scanned,
        )

        return result

    # ------------------------------------------------------------------
    # Element dispatch
    # ------------------------------------------------------------------

    def _process_element(
        self,
        elem: etree._Element,
        result: StreamingParseResult,
        wrapper: CountingFileWrapper,
    ) -> None:
        """Route a top-level child element to the appropriate handler."""
        tag = elem.tag
        if tag == _LINK_SCHEMA_REF:
            self._handle_schema_ref(elem, result)
        elif tag == _LINK_LINKBASE_REF:
            self._handle_linkbase_ref(elem, result)
        elif tag == _XBRLI_CONTEXT:
            self._handle_context(elem, result)
        elif tag == _XBRLI_UNIT:
            self._handle_unit(elem, result)
        elif tag == _LINK_FOOTNOTE_LINK:
            pass  # Footnotes not stored in FactStore
        else:
            ns = get_namespace(tag)
            if ns and ns not in _RESERVED_NAMESPACES:
                self._handle_fact(elem, result, wrapper)

    # -- schemaRef / linkbaseRef -----------------------------------------

    @staticmethod
    def _handle_schema_ref(
        elem: etree._Element, result: StreamingParseResult
    ) -> None:
        href = elem.get(f"{{{NS_XLINK}}}href", "")
        result.schema_refs.append(SchemaRef(href=href))

    @staticmethod
    def _handle_linkbase_ref(
        elem: etree._Element, result: StreamingParseResult
    ) -> None:
        href = elem.get(f"{{{NS_XLINK}}}href", "")
        role = elem.get(f"{{{NS_XLINK}}}role", "")
        arcrole = elem.get(f"{{{NS_XLINK}}}arcrole", "")
        result.linkbase_refs.append(
            LinkbaseRef(href=href, role=role, arcrole=arcrole)
        )

    # -- context ---------------------------------------------------------

    @staticmethod
    def _handle_context(
        elem: etree._Element, result: StreamingParseResult
    ) -> None:
        ctx_id = elem.get("id", "")
        if not ctx_id:
            return

        ctx = RawContext(id=ctx_id)

        entity = elem.find(_XBRLI_ENTITY)
        if entity is not None:
            ident = entity.find(_XBRLI_IDENTIFIER)
            if ident is not None:
                ctx.entity_scheme = ident.get("scheme", "")
                ctx.entity_id = (ident.text or "").strip()

        period = elem.find(_XBRLI_PERIOD)
        if period is not None:
            instant = period.find(_XBRLI_INSTANT)
            forever = period.find(_XBRLI_FOREVER)
            start = period.find(_XBRLI_START)
            end = period.find(_XBRLI_END)

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

    # -- unit ------------------------------------------------------------

    @staticmethod
    def _handle_unit(
        elem: etree._Element, result: StreamingParseResult
    ) -> None:
        unit_id = elem.get("id", "")
        if not unit_id:
            return

        unit = RawUnit(id=unit_id)
        divide = elem.find(_XBRLI_DIVIDE)
        if divide is not None:
            num = divide.find(_XBRLI_NUMERATOR)
            den = divide.find(_XBRLI_DENOMINATOR)
            if num is not None:
                unit.divide_numerator = [
                    (m.text or "").strip()
                    for m in num.findall(_XBRLI_MEASURE)
                ]
            if den is not None:
                unit.divide_denominator = [
                    (m.text or "").strip()
                    for m in den.findall(_XBRLI_MEASURE)
                ]
        else:
            unit.measures = [
                (m.text or "").strip()
                for m in elem.findall(_XBRLI_MEASURE)
            ]

        result.units[unit_id] = unit

    # -- fact ------------------------------------------------------------

    def _handle_fact(
        self,
        elem: etree._Element,
        result: StreamingParseResult,
        wrapper: CountingFileWrapper,
    ) -> None:
        """Convert an element to a FactReference and add to FactStore."""
        context_ref = elem.get("contextRef", "")
        if not context_ref:
            return

        tag = elem.tag
        nil_attr = elem.get(f"{{{NS_XSI}}}nil", "false")
        is_nil = nil_attr.lower() in ("true", "1")
        unit_ref = elem.get("unitRef")
        is_numeric = unit_ref is not None

        # Get value text
        value_text = ""
        if not is_nil:
            value_text = (elem.text or "").strip()

        value_bytes = value_text.encode("utf-8")
        byte_offset = max(0, wrapper.bytes_read - len(value_bytes) - 100)

        ref = FactReference(
            index=self._fact_index,
            concept=tag,
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
