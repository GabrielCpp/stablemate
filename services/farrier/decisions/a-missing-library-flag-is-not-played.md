story: track50
date: 2026-11-11
elements: Install, Scaffold

The book always sends --library and never plays it left out. Without it farrier falls back to the library of the
machine it runs on: $FARRIER_LIBRARY_DIR, the home config, then the base library it finds or fetches
(farrier/farrier/layers.py:95-118). The sandbox cuts the first two and sets STABLEMATE_FETCH_BASE=0, but a base
library installed beside farrier would still answer, so the result would depend on the machine and not on the
claim. The library argument is therefore optional in the declaration, which keeps the runtime from deriving a
"missing" class for it.
