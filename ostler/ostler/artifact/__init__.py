"""`ostler artifact` — schema-checked workflow artifacts.

See docs/ARTIFACT-CONTRACTS.md: workflow artifacts an agent writes for a
deterministic consumer (plan-context.json, qa-evidence.json, backlog-items.json)
carry their contract as data — scaffolded at write time, vetted at the producer,
never discovered broken stages later.
"""

from .kinds import KINDS, ArtifactKind, get_kind
from .run import list_kinds, scaffold, vet

__all__ = ["KINDS", "ArtifactKind", "get_kind", "list_kinds", "scaffold", "vet"]
