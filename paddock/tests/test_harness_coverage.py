"""The sandbox names only harnesses workhorse can drive."""

from __future__ import annotations

from paddock._vendor.stablemate_core.harness import workhorse_harnesses
from paddock.sandbox import LOGINS


def test_every_sandbox_login_belongs_to_a_workhorse_harness() -> None:
    assert set(LOGINS) <= {harness.name for harness in workhorse_harnesses()}
