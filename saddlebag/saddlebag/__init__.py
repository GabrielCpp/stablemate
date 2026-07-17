"""saddlebag — the runtime credential pool for the stablemate ecosystem.

Ostler owns the *spec* of what a test needs (roles, envs, surface). saddlebag owns
the *runtime identity* that satisfies that spec: scan, select, lease, release.
"""

from __future__ import annotations

__all__ = ["Credential", "Lease"]

from saddlebag.models import Credential, Lease
