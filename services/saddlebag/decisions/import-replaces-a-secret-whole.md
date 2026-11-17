story: none
date: 2026-11-16
elements: Import

`import` loads an export all or nothing: every secret is checked first, and a name already in the store is refused unless
--replace is given. With --replace the existing secret is removed and created again from the document, so what the document
leaves out, such as metadata, is gone (saddlebag/saddlebag/transfer.py, load). A file that is not JSON is exit 2, and one
that is JSON and no export is exit 1.
