---
type: concept
slug: livesource-documentation-context
title: LiveSource documentation context
---
# LiveSource documentation context

`LiveSource` has one implementation. It receives a package name, a read-only host bind, a
container-local generation root, and optionally additional editable packages; staging then
copies that bind into an immutable generation before installing it. The source is deliberately
generic over the package so callers do not need a second implementation.

Use [LiveSource configuration fields](live-source-configuration.md) when constructing a
`LiveSource` and deciding whether an accompanying local package belongs in `with_editable`.
Use [LiveSource — immutable bind-source generations](live-source.md) when reasoning about
staging, installation, failure recovery, and generation retention. These are complementary
views of the same type, not choices between implementations.

- code: `workhorse/livesource.py::LiveSource`
- rule: use the configuration-fields concept for constructor inputs and the immutable-generations concept for staging and refresh behavior; neither supersedes the other
- detail: [LiveSource documentation guide](live-source-documentation-guide.md)
