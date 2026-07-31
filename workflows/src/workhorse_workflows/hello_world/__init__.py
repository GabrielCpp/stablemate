"""`hello-world` — the smallest workflow that runs, and the one the docs point at.

It exists to be *copied*: two states, one node, one agent turn, no repo, no context
manifest, no external service. `workhorse run hello-world --dry-run` walks it green on
a bare checkout with no agent CLI installed at all, which is what makes it usable as a
quick start rather than a listing.

Nothing else in the tree imports it, and nothing should. It is documentation that
happens to execute — the moment it grows a second dependency it stops being the
example someone can paste.
"""
from __future__ import annotations
