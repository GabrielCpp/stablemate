### `code-cites-test` — a `code:` bullet cites test source beside the product

The node documents product code and also cites a test, mock or fixture under `code:`. `code:`
says which product symbol the node *is*; a test is evidence about that symbol, not the symbol.

- **Remove each `code:` bullet whose path is test source** (the finding names them). This is
  the shared rule's exception: the product citation stays, so the node's grounding is intact.
- **When the test proves one of the node's claims and the type admits `tests:`**, cite it there
  instead — `- tests: \`<path>::<TestName>\`` — unless an identical `tests:` bullet already
  exists. Cite a test function, never a mock or fake type: a double proves nothing.
- Leave every other bullet alone.
