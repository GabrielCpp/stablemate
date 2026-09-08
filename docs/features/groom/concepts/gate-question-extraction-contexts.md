---
type: concept
slug: gate-question-extraction-contexts
title: Gate question extraction contexts
---
# Gate question extraction contexts

`extract_question` has one implementation but two documentation contexts. The
[Groom gates module](groom-gates-module.md#extract-question) is the callable's
general pure-string helper contract. The [operator gate context
file](../operator-gate-context-file.md#method-extract-question) is the same
callable's input-format contract: it defines which Markdown-like heading is
recognized and what the fallback means for a gate file.

Neither context supersedes the other. Read the module node when calling or
reusing the helper outside a particular file-format discussion; read the format
node when preparing or interpreting operator gate context text. The shared
implementation collects every recognized question section and returns the
stripped body from the latest one; when none is recognized, it returns stripped
whole-file text. Both results are limited to the first 4000 characters.

- code: groom/groom/gates.py::extract_question
- rule: use the module node for the helper contract and the format node for the operator-gate text rules; neither is a replacement for the other.
