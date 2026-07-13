---
type: concept
slug: groom-a11y-html-tree-parser
title: Groom a11y HTML tree parser
---
# Groom a11y HTML tree parser

Groom a11y HTML tree parser is the private parser-state concept used by
[Groom a11y lint](groom-a11y-lint.md) to turn one HTML document or fragment into
ordered [Groom a11y node](../groom-a11y-node.md) records. It preserves source
line numbers, parent/child relationships, direct text chunks, and normalized
attribute maps so the lint engine can evaluate static accessibility rules without
a browser DOM.

- code: groom/groom/a11y_lint.py::_Tree

## Contract

- input: token callbacks produced from one HTML text stream.
- output: a synthetic root [Groom a11y node](../groom-a11y-node.md), a source-order
  list of every parsed non-root node, and parent/child/text relationships among
  those nodes.
- root-node: the root always has `tag="#root"`, empty attributes, `line=0`, no
  parent, and starts as the only open node.
- node-order: every parsed start tag or self-closing tag appends exactly one
  non-root node to `nodes` in parser encounter order.
- source-lines: each non-root node records the parser line number at the tag that
  created it.
- attribute-normalization: attribute names are lowercased and attributes without
  values are represented as empty strings.
- text-normalization: only non-whitespace character data is retained, and retained
  chunks keep the text delivered by the parser.
- void-elements: tags in the module's void-element set produce nodes but never
  remain open for later children or text.
- malformed-markup-tolerance: unmatched end tags are ignored, and a matching end
  tag closes that tag plus any still-open descendants above it.
- scope: this concept builds the structural parse tree only; it does not classify
  accessibility findings, resolve labels, compute accessible names, or inspect CSS,
  JavaScript, browser layout, or post-swap DOM state.
- errors: no parser-specific accessibility diagnostic is emitted by this concept;
  caller-visible failures follow the underlying HTML parser/feed behavior.

## State

- `root`: synthetic [Groom a11y node](../groom-a11y-node.md) that owns the parsed
  top-level element children.
- `_stack`: open-node stack; index `0` is always `root`, and the final item is the
  node that receives subsequent child nodes and direct text.
- `nodes`: source-order list of parsed element nodes, excluding `root`.

## Methods

### method-__init__

- sig: `__init__(self) -> None`
- abstract: false
- raises: no parser-specific exception is part of this method's contract.
- code: groom/groom/a11y_lint.py::_Tree.__init__
- does:
  - Enables character-reference conversion for subsequent HTML parsing.
  - Creates the synthetic root node with no parent and no source element.
  - Initializes the open-node stack with the root as the only open node.
  - Initializes the source-order parsed-node list as empty.

### method-_open

- sig: `_open(self, tag: str, attrs: list[tuple[str, str | None]]) -> Node`
- abstract: false
- raises: no parser-specific exception is part of this method's contract.
- code: groom/groom/a11y_lint.py::_Tree._open
- does:
  - Reads the current open node from the top of `_stack` and uses it as the new
    node's parent.
  - Creates one [Groom a11y node](../groom-a11y-node.md) for the supplied tag.
  - Normalizes the supplied attributes into a dictionary with lowercase keys and
    empty strings for missing values.
  - Captures the parser's current source line number on the node.
  - Appends the new node to its parent's `children` list.
  - Appends the new node to `nodes` in source encounter order.
  - Returns the new node so the caller can decide whether it should remain open.

### method-handle_starttag

- sig: `handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None`
- abstract: false
- raises: no parser-specific exception is part of this method's contract.
- code: groom/groom/a11y_lint.py::_Tree.handle_starttag
- does:
  - Creates and records a node for the start tag using the current open parent.
  - Leaves void elements closed after node creation.
  - Pushes non-void elements onto `_stack` so following tags and text become their
    descendants until a matching end tag closes them.

### method-handle_startendtag

- sig: `handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None`
- abstract: false
- raises: no parser-specific exception is part of this method's contract.
- code: groom/groom/a11y_lint.py::_Tree.handle_startendtag
- does:
  - Creates and records a node for the self-closing tag using the current open
    parent.
  - Does not push the node onto `_stack`, so later tags and text are not assigned
    beneath it.

### method-handle_endtag

- sig: `handle_endtag(self, tag: str) -> None`
- abstract: false
- raises: no parser-specific exception is part of this method's contract.
- code: groom/groom/a11y_lint.py::_Tree.handle_endtag
- does:
  - Searches the open-node stack from innermost open node toward the root for the
    requested tag.
  - When a match exists, removes that matched node and every open descendant above
    it from `_stack`.
  - When no match exists, leaves parser state unchanged and ignores the end tag.

### method-handle_data

- sig: `handle_data(self, data: str) -> None`
- abstract: false
- raises: no parser-specific exception is part of this method's contract.
- code: groom/groom/a11y_lint.py::_Tree.handle_data
- does:
  - Ignores whitespace-only character data.
  - Appends each retained text chunk to the current open node's `text` list.
  - Assigns direct text to the node open at the time the parser delivers the data;
    descendant text is stored on descendant nodes and reached through `children`.
