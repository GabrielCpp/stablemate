"""saddlebag: a Vault-backed daemon that fills secrets without printing them."""

from __future__ import annotations

__all__ = ["Secret", "SecretUnavailable", "secret_value"]

TYPE_CHECKING = False
if TYPE_CHECKING:
    from saddlebag.lookup import SecretUnavailable, secret_value
    from saddlebag.models import Secret


def __getattr__(name: str) -> object:
    if name == "Secret":
        from saddlebag.models import Secret

        return Secret
    if name in ("SecretUnavailable", "secret_value"):
        from saddlebag import lookup

        return getattr(lookup, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
