story: track50
date: 2026-11-11
elements: Install, Scaffold

The book always sends --library and never plays it left out. Without it farrier falls back to the library of the
machine it runs on: $FARRIER_LIBRARY_DIR, the home config, then the base library it finds or ships
(farrier/farrier/layers.py:114-149). The sandbox cuts the first two and names an empty base, so the fall-back would
render no skill the book could compare. The library argument is therefore optional in the declaration, which keeps
the runtime from deriving a "missing" class for it.
