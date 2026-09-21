"""`ostler artifact` — schema-checked workflow artifacts."""

from ostler.artifact.kinds import KINDS, ArtifactKind, get_kind
from ostler.artifact.run import cmd_vet, list_kinds, scaffold, vet

__all__ = ["KINDS", "ArtifactKind", "cmd_vet", "get_kind", "list_kinds", "scaffold", "vet"]
