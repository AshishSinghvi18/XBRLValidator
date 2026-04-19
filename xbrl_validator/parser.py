from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET


XBRLI_NS = "http://www.xbrl.org/2003/instance"
LINK_NS = "http://www.xbrl.org/2003/linkbase"
XLINK_NS = "http://www.w3.org/1999/xlink"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
XML_NS = "http://www.w3.org/XML/1998/namespace"


@dataclass(frozen=True)
class SchemaReference:
    href: Optional[str]


@dataclass(frozen=True)
class LinkbaseReference:
    href: Optional[str]
    role: Optional[str]
    arcrole: Optional[str]


@dataclass(frozen=True)
class ContextData:
    id: str
    entity_scheme: Optional[str]
    entity_identifier: Optional[str]
    period_type: Optional[str]
    instant: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    segment_xml: Optional[str]
    scenario_xml: Optional[str]


@dataclass(frozen=True)
class UnitData:
    id: str
    measures: List[str]
    numerator_measures: List[str]
    denominator_measures: List[str]


@dataclass(frozen=True)
class FactData:
    qname: str
    context_ref: Optional[str]
    unit_ref: Optional[str]
    decimals: Optional[str]
    precision: Optional[str]
    xml_lang: Optional[str]
    xsi_nil: bool
    value: Optional[str]


@dataclass(frozen=True)
class TupleData:
    qname: str
    children_facts: List[FactData] = field(default_factory=list)
    children_tuples: List["TupleData"] = field(default_factory=list)


@dataclass(frozen=True)
class FootnoteData:
    label: Optional[str]
    role: Optional[str]
    language: Optional[str]
    text: str


@dataclass(frozen=True)
class FootnoteLocator:
    label: Optional[str]
    href: Optional[str]


@dataclass(frozen=True)
class FootnoteArc:
    arcrole: Optional[str]
    from_label: Optional[str]
    to_label: Optional[str]


@dataclass(frozen=True)
class FootnoteLinkData:
    footnotes: List[FootnoteData]
    locators: List[FootnoteLocator]
    arcs: List[FootnoteArc]


@dataclass(frozen=True)
class XBRLInstanceData:
    namespaces: Dict[str, str]
    schema_refs: List[SchemaReference]
    linkbase_refs: List[LinkbaseReference]
    contexts: Dict[str, ContextData]
    units: Dict[str, UnitData]
    facts: List[FactData]
    footnote_links: List[FootnoteLinkData]
    tuples: List[TupleData]


def _collect_namespaces(xml_bytes: bytes) -> Dict[str, str]:
    namespaces: Dict[str, str] = {}
    for _, (prefix, uri) in ET.iterparse(BytesIO(xml_bytes), events=("start-ns",)):
        namespaces[prefix or ""] = uri
    return namespaces


def _split_tag(tag: str) -> Tuple[Optional[str], str]:
    if tag.startswith("{"):
        uri, local = tag[1:].split("}", 1)
        return uri, local
    return None, tag


def _qname(tag: str, namespaces: Dict[str, str]) -> str:
    uri, local = _split_tag(tag)
    if uri is None:
        return local
    for prefix, mapped in namespaces.items():
        if mapped == uri:
            return f"{prefix}:{local}" if prefix else local
    return f"{{{uri}}}{local}"


def _first_child(element: ET.Element, namespace: str, local_name: str) -> Optional[ET.Element]:
    return element.find(f"{{{namespace}}}{local_name}")


def _serialize_children(element: Optional[ET.Element]) -> Optional[str]:
    if element is None:
        return None
    return "".join(ET.tostring(child, encoding="unicode") for child in list(element)) or None


def _parse_context(context: ET.Element) -> ContextData:
    context_id = context.attrib["id"]
    entity = _first_child(context, XBRLI_NS, "entity")
    identifier = _first_child(entity, XBRLI_NS, "identifier") if entity is not None else None

    period = _first_child(context, XBRLI_NS, "period")
    instant_element = _first_child(period, XBRLI_NS, "instant") if period is not None else None
    start_element = _first_child(period, XBRLI_NS, "startDate") if period is not None else None
    end_element = _first_child(period, XBRLI_NS, "endDate") if period is not None else None
    instant = instant_element.text.strip() if instant_element is not None and instant_element.text else None
    start_date = start_element.text.strip() if start_element is not None and start_element.text else None
    end_date = end_element.text.strip() if end_element is not None and end_element.text else None

    period_type = "instant" if instant else "duration" if start_date and end_date else None

    return ContextData(
        id=context_id,
        entity_scheme=identifier.attrib.get("scheme") if identifier is not None else None,
        entity_identifier=identifier.text.strip() if identifier is not None and identifier.text else None,
        period_type=period_type,
        instant=instant,
        start_date=start_date,
        end_date=end_date,
        segment_xml=_serialize_children(_first_child(entity, XBRLI_NS, "segment") if entity is not None else None),
        scenario_xml=_serialize_children(_first_child(context, XBRLI_NS, "scenario")),
    )


def _parse_measure_texts(parent: Optional[ET.Element], namespaces: Dict[str, str]) -> List[str]:
    if parent is None:
        return []
    measures: List[str] = []
    for measure in parent.findall(f"{{{XBRLI_NS}}}measure"):
        if measure.text:
            raw = measure.text.strip()
            if ":" in raw:
                prefix, local = raw.split(":", 1)
                uri = namespaces.get(prefix)
                if uri:
                    measures.append(f"{prefix}:{local}")
                    continue
            measures.append(raw)
    return measures


def _parse_unit(unit: ET.Element, namespaces: Dict[str, str]) -> UnitData:
    divide = _first_child(unit, XBRLI_NS, "divide")
    numerator = _first_child(divide, XBRLI_NS, "unitNumerator") if divide is not None else None
    denominator = _first_child(divide, XBRLI_NS, "unitDenominator") if divide is not None else None
    return UnitData(
        id=unit.attrib["id"],
        measures=_parse_measure_texts(unit, namespaces),
        numerator_measures=_parse_measure_texts(numerator, namespaces),
        denominator_measures=_parse_measure_texts(denominator, namespaces),
    )


def _parse_fact(element: ET.Element, namespaces: Dict[str, str]) -> FactData:
    return FactData(
        qname=_qname(element.tag, namespaces),
        context_ref=element.attrib.get("contextRef"),
        unit_ref=element.attrib.get("unitRef"),
        decimals=element.attrib.get("decimals"),
        precision=element.attrib.get("precision"),
        xml_lang=element.attrib.get(f"{{{XML_NS}}}lang"),
        xsi_nil=element.attrib.get(f"{{{XSI_NS}}}nil", "").lower() == "true",
        value=element.text.strip() if element.text and element.text.strip() else None,
    )


def _is_infrastructure(element: ET.Element) -> bool:
    uri, local = _split_tag(element.tag)
    if (uri, local) in {
        (XBRLI_NS, "context"),
        (XBRLI_NS, "unit"),
        (LINK_NS, "schemaRef"),
        (LINK_NS, "linkbaseRef"),
        (LINK_NS, "footnoteLink"),
    }:
        return True
    return False


def _parse_tuple(element: ET.Element, namespaces: Dict[str, str]) -> TupleData:
    facts: List[FactData] = []
    tuples: List[TupleData] = []
    for child in list(element):
        if _is_infrastructure(child):
            continue
        if len(child):
            tuples.append(_parse_tuple(child, namespaces))
        else:
            facts.append(_parse_fact(child, namespaces))
    return TupleData(qname=_qname(element.tag, namespaces), children_facts=facts, children_tuples=tuples)


def _parse_footnote_link(footnote_link: ET.Element) -> FootnoteLinkData:
    footnotes: List[FootnoteData] = []
    locators: List[FootnoteLocator] = []
    arcs: List[FootnoteArc] = []

    for child in list(footnote_link):
        uri, local = _split_tag(child.tag)
        if uri != LINK_NS:
            continue
        if local == "footnote":
            footnotes.append(
                FootnoteData(
                    label=child.attrib.get(f"{{{XLINK_NS}}}label"),
                    role=child.attrib.get(f"{{{XLINK_NS}}}role"),
                    language=child.attrib.get(f"{{{XML_NS}}}lang"),
                    text=(child.text or "").strip(),
                )
            )
        elif local == "loc":
            locators.append(
                FootnoteLocator(
                    label=child.attrib.get(f"{{{XLINK_NS}}}label"),
                    href=child.attrib.get(f"{{{XLINK_NS}}}href"),
                )
            )
        elif local == "footnoteArc":
            arcs.append(
                FootnoteArc(
                    arcrole=child.attrib.get(f"{{{XLINK_NS}}}arcrole"),
                    from_label=child.attrib.get(f"{{{XLINK_NS}}}from"),
                    to_label=child.attrib.get(f"{{{XLINK_NS}}}to"),
                )
            )

    return FootnoteLinkData(footnotes=footnotes, locators=locators, arcs=arcs)


def parse_xbrl_instance(xml_content: str) -> XBRLInstanceData:
    xml_bytes = xml_content.encode("utf-8")
    namespaces = _collect_namespaces(xml_bytes)
    root = ET.fromstring(xml_bytes)
    root_uri, root_local = _split_tag(root.tag)
    if (root_uri, root_local) != (XBRLI_NS, "xbrl"):
        raise ValueError("Document root must be xbrli:xbrl")

    schema_refs: List[SchemaReference] = []
    linkbase_refs: List[LinkbaseReference] = []
    contexts: Dict[str, ContextData] = {}
    units: Dict[str, UnitData] = {}
    facts: List[FactData] = []
    footnote_links: List[FootnoteLinkData] = []
    tuples: List[TupleData] = []

    for child in list(root):
        uri, local = _split_tag(child.tag)
        if (uri, local) == (LINK_NS, "schemaRef"):
            schema_refs.append(SchemaReference(href=child.attrib.get(f"{{{XLINK_NS}}}href")))
        elif (uri, local) == (LINK_NS, "linkbaseRef"):
            linkbase_refs.append(
                LinkbaseReference(
                    href=child.attrib.get(f"{{{XLINK_NS}}}href"),
                    role=child.attrib.get(f"{{{XLINK_NS}}}role"),
                    arcrole=child.attrib.get(f"{{{XLINK_NS}}}arcrole"),
                )
            )
        elif (uri, local) == (XBRLI_NS, "context"):
            contexts[child.attrib["id"]] = _parse_context(child)
        elif (uri, local) == (XBRLI_NS, "unit"):
            units[child.attrib["id"]] = _parse_unit(child, namespaces)
        elif (uri, local) == (LINK_NS, "footnoteLink"):
            footnote_links.append(_parse_footnote_link(child))
        else:
            if len(child):
                tuples.append(_parse_tuple(child, namespaces))
            else:
                facts.append(_parse_fact(child, namespaces))

    return XBRLInstanceData(
        namespaces=namespaces,
        schema_refs=schema_refs,
        linkbase_refs=linkbase_refs,
        contexts=contexts,
        units=units,
        facts=facts,
        footnote_links=footnote_links,
        tuples=tuples,
    )
