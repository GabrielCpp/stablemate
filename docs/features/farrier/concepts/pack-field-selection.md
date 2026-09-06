---
type: concept
slug: pack-field-selection
title: Pack field selection
---
# Pack field selection

The fields in a pack mapping have separate roles and are not alternative
implementations. `load_pack` reads `skills`, `prompts`, and `roots` into
separate selection sets; follows `includes` to merge another pack's sets; and
does not read `description` while collecting selections. The loader gives none
of these fields precedence over another.

Choose `includes` to compose selections from another pack. Choose `skills`,
`prompts`, or `roots` for the corresponding category of source selection, and
use `description` only for human-readable metadata. A pack can use any
combination of those roles.

- code: `farrier/farrier/sources.py::load_pack`
- rule: select the field by its distinct role; no ranking exists among pack fields
