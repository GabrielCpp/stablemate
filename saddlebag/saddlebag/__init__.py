"""saddlebag: a Vault-backed daemon that fills secrets without printing them."""

from __future__ import annotations

__all__ = ["Secret"]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from saddlebag.models import Secret


def __getattr__(name: str) -> object:
    if name == "Secret":
        from saddlebag.models import Secret

        return Secret
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
