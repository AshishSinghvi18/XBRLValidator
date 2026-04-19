import unittest

from xbrl_validator import parse_xbrl_instance


SAMPLE_XBRL = """<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl
    xmlns:xbrli="http://www.xbrl.org/2003/instance"
    xmlns:link="http://www.xbrl.org/2003/linkbase"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
    xmlns:ex="http://example.com/taxonomy">
  <link:schemaRef xlink:type="simple" xlink:href="entry-point.xsd"/>
  <link:linkbaseRef xlink:type="simple" xlink:href="calc.xml" xlink:role="calculation" xlink:arcrole="arc"/>

  <xbrli:context id="C1">
    <xbrli:entity>
      <xbrli:identifier scheme="http://example.com/entity">Entity-1</xbrli:identifier>
      <xbrli:segment>
        <ex:RegionAxis>NA</ex:RegionAxis>
      </xbrli:segment>
    </xbrli:entity>
    <xbrli:period>
      <xbrli:instant>2025-12-31</xbrli:instant>
    </xbrli:period>
  </xbrli:context>

  <xbrli:context id="C2">
    <xbrli:entity>
      <xbrli:identifier scheme="http://example.com/entity">Entity-1</xbrli:identifier>
    </xbrli:entity>
    <xbrli:period>
      <xbrli:startDate>2025-01-01</xbrli:startDate>
      <xbrli:endDate>2025-12-31</xbrli:endDate>
    </xbrli:period>
    <xbrli:scenario>
      <ex:ScenarioMember>Base</ex:ScenarioMember>
    </xbrli:scenario>
  </xbrli:context>

  <xbrli:unit id="U1">
    <xbrli:measure>iso4217:USD</xbrli:measure>
  </xbrli:unit>
  <xbrli:unit id="U2">
    <xbrli:divide>
      <xbrli:unitNumerator>
        <xbrli:measure>iso4217:USD</xbrli:measure>
      </xbrli:unitNumerator>
      <xbrli:unitDenominator>
        <xbrli:measure>xbrli:shares</xbrli:measure>
      </xbrli:unitDenominator>
    </xbrli:divide>
  </xbrli:unit>

  <ex:Revenue contextRef="C1" unitRef="U1" decimals="-3">1250000</ex:Revenue>
  <ex:Description contextRef="C1" xml:lang="en">Annual report</ex:Description>
  <ex:NilFact contextRef="C1" xsi:nil="true"/>

  <ex:ManagementTuple>
    <ex:Headcount contextRef="C2" unitRef="U2" precision="2">10</ex:Headcount>
    <ex:NestedTuple>
      <ex:Comment contextRef="C2">Nested tuple fact</ex:Comment>
    </ex:NestedTuple>
  </ex:ManagementTuple>

  <link:footnoteLink xlink:type="extended">
    <link:loc xlink:type="locator" xlink:href="#f-revenue" xlink:label="loc1"/>
    <link:footnote xlink:type="resource" xlink:label="fn1" xml:lang="en">Revenue is rounded.</link:footnote>
    <link:footnoteArc xlink:type="arc" xlink:arcrole="http://www.xbrl.org/2003/arcrole/fact-footnote" xlink:from="loc1" xlink:to="fn1"/>
  </link:footnoteLink>
</xbrli:xbrl>
"""


class TestXBRLParser(unittest.TestCase):
    def test_parse_instance_document(self) -> None:
        result = parse_xbrl_instance(SAMPLE_XBRL)

        self.assertEqual(result.namespaces["xbrli"], "http://www.xbrl.org/2003/instance")
        self.assertEqual(result.namespaces["ex"], "http://example.com/taxonomy")

        self.assertEqual(len(result.schema_refs), 1)
        self.assertEqual(result.schema_refs[0].href, "entry-point.xsd")

        self.assertEqual(len(result.linkbase_refs), 1)
        self.assertEqual(result.linkbase_refs[0].href, "calc.xml")
        self.assertEqual(result.linkbase_refs[0].role, "calculation")

        self.assertEqual(set(result.contexts.keys()), {"C1", "C2"})
        self.assertEqual(result.contexts["C1"].entity_identifier, "Entity-1")
        self.assertEqual(result.contexts["C1"].period_type, "instant")
        self.assertEqual(result.contexts["C2"].period_type, "duration")
        self.assertIn("ScenarioMember", result.contexts["C2"].scenario_xml or "")

        self.assertEqual(set(result.units.keys()), {"U1", "U2"})
        self.assertEqual(result.units["U1"].measures, ["iso4217:USD"])
        self.assertEqual(result.units["U2"].numerator_measures, ["iso4217:USD"])
        self.assertEqual(result.units["U2"].denominator_measures, ["xbrli:shares"])

        self.assertEqual(len(result.facts), 3)
        revenue = next(f for f in result.facts if f.qname == "ex:Revenue")
        self.assertEqual(revenue.context_ref, "C1")
        self.assertEqual(revenue.unit_ref, "U1")
        self.assertEqual(revenue.decimals, "-3")
        self.assertEqual(revenue.value, "1250000")

        description = next(f for f in result.facts if f.qname == "ex:Description")
        self.assertEqual(description.xml_lang, "en")

        nil_fact = next(f for f in result.facts if f.qname == "ex:NilFact")
        self.assertTrue(nil_fact.xsi_nil)

        self.assertEqual(len(result.tuples), 1)
        root_tuple = result.tuples[0]
        self.assertEqual(root_tuple.qname, "ex:ManagementTuple")
        self.assertEqual(root_tuple.children_facts[0].qname, "ex:Headcount")
        self.assertEqual(root_tuple.children_tuples[0].children_facts[0].qname, "ex:Comment")

        self.assertEqual(len(result.footnote_links), 1)
        footnote_link = result.footnote_links[0]
        self.assertEqual(footnote_link.locators[0].href, "#f-revenue")
        self.assertEqual(footnote_link.footnotes[0].text, "Revenue is rounded.")
        self.assertEqual(footnote_link.arcs[0].from_label, "loc1")

    def test_rejects_non_xbrl_root(self) -> None:
        with self.assertRaises(ValueError):
            parse_xbrl_instance("<root/>")


if __name__ == "__main__":
    unittest.main()
