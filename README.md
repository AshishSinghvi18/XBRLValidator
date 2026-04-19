# XBRLValidator

Python parser for XBRL 2.1 instance documents.

## Supported extraction

- Namespace declarations (`xmlns:*`)
- `link:schemaRef`
- `link:linkbaseRef`
- Contexts (`xbrli:context`)
- Units (`xbrli:unit`, including divide units)
- Facts (including `contextRef`, `unitRef`, `decimals`, `precision`, `xml:lang`, `xsi:nil`, value)
- Footnote links (`link:footnoteLink`, `link:loc`, `link:footnote`, `link:footnoteArc`)
- Tuples (nested tuple/fact structures)

## Usage

```python
from xbrl_validator import parse_xbrl_instance

with open("filing.xml", "r", encoding="utf-8") as f:
    instance = parse_xbrl_instance(f.read())

print(instance.facts)
```
