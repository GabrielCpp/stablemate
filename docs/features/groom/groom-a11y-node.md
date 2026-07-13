---
type: format
slug: groom-a11y-node
title: Groom a11y node
---
# Groom a11y node

Groom a11y node is the in-memory element record built while the [Groom a11y lint](concepts/groom-a11y-lint.md)
engine parses one HTML document. It gives the lint rules a normalized view of each
element's tag name, attributes, source line, parent/child relationships, and
direct text content; findings are emitted separately in the [Groom a11y finding](groom-a11y-finding.md)
format.

- file: not an on-disk artifact; this is an in-memory parser-node item.
- code: groom/groom/a11y_lint.py::Node

## Contract

- producer: [Groom a11y lint](concepts/groom-a11y-lint.md) creates one root node and one node for each parsed HTML start or self-closing tag.
- consumer: [Groom a11y lint](concepts/groom-a11y-lint.md) rules inspect nodes for labels, names, focusability, ancestor tags, and live-region semantics.
- identity: nodes are tree records, not value identifiers; equality follows field values.
- mutability: mutable while parsing and linting; children and text are appended as source is parsed.
- ordering: non-root nodes are stored in source encounter order, matching the order in which lint rules evaluate them.
- root-node: the synthetic root has `tag="#root"`, empty attributes, `line=0`, no parent, parsed element children, and any direct text parser data attached before a child opens.
- void-elements: void HTML elements are represented as nodes but are not kept on the open-element stack, so they cannot receive later child or text content from a closing tag.
- attribute-normalization: attribute names are lowercased and missing attribute values become the empty string.
- text-normalization: direct text chunks are recorded only when they contain non-whitespace content; original text spacing inside each retained chunk is preserved.

## Fields

### field-tag

- type: `str`
- default: none
- required: true
- source: parsed HTML tag name supplied by the HTML parser, or `#root` for the synthetic root.
- meaning: identifies the element kind used by rule dispatch and native-interactive checks.
- normalization: preserved as supplied by the parser; the root sentinel is not an HTML tag.

### field-attrs

- type: `dict[str, str]`
- default: none
- required: true
- source: parsed HTML attribute pairs for the element.
- meaning: maps attribute names to string values for accessible-name, focusability, label, HTMX action, websocket action, and live-region checks.
- normalization: keys are lowercase; attributes with no value are stored with `""`; duplicate attribute handling follows the parser's delivered pair order and dictionary overwrite semantics.
- empty-state: elements with no attributes use an empty dictionary.

### field-line

- type: `int`
- default: none
- required: true
- source: parser source position at the start tag.
- meaning: one-based source line copied into any finding caused by this element.
- root-value: `0` for the synthetic root, which is never itself linted.

### field-parent

- type: `Groom a11y node | None`
- default: `None`
- required: false
- source: current open element when this node is created.
- meaning: points to the containing element so rules can test ancestor tags and tree context.
- root-value: `None` for the synthetic root.
- consistency: for every non-root node, the same node appears in `parent.children`.

### field-children

- type: `list[Groom a11y node]`
- default: empty list
- required: false
- source: child elements appended as nested start or self-closing tags are parsed.
- meaning: preserves the element subtree used for accessible-text accumulation and child image-alt contribution.
- ordering: children are stored in source encounter order.
- isolation: every node owns its own children list; an empty element has an empty list rather than `None`.

### field-text

- type: `list[str]`
- default: empty list
- required: false
- source: non-whitespace character data parsed while this node is the current open element.
- meaning: stores the element's direct text chunks used when calculating visible or announced subtree text.
- ordering: text chunks are stored in source encounter order among chunks assigned to that node.
- exclusion: whitespace-only chunks are omitted; descendant text belongs to descendant nodes and is reached through `children`.
