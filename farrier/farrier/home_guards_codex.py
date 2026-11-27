"""Codex guard approval: which installed guards Codex skips until the user approves them."""

from __future__ import annotations

import json
from pathlib import Path

from farrier._vendor.stablemate_core.schema import HomeConfig
from farrier.home_entries import Entry, entry_drift, read_entry_file, read_ledger
from farrier.home_guards import CODEX_GUARDS, installed_command, selected_guards

CODEX_CONFIG = ".codex/config.toml"
APPROVE = "Open Codex and run /hooks to approve them. Farrier never approves a guard."


def approval_keys(path: Path) -> dict[str, str]:
    """Each command in the Codex guard file at *path*, with the key Codex records its approval under."""
    if not path.exists():
        return {}
    hooks = json.loads(path.read_text(encoding="utf-8")).get("hooks", {})
    return {
        hook["command"]: f"{path.resolve()}:{key}:{group}:{handler}"
        for event, key in (("PreToolUse", "pre_tool_use"), ("Stop", "stop"))
        for group, entry in enumerate(hooks.get(event, []))
        for handler, hook in enumerate(entry.get("hooks", []))
        if "command" in hook
    }


def pending_guards(config: HomeConfig, home: Path) -> list[str]:
    """The installed guards Codex will skip, because no approval is recorded for them."""
    keys = approval_keys(home / CODEX_GUARDS)
    state = read_entry_file(home / CODEX_CONFIG).entries("hooks").get("state", {})
    pending: list[str] = []
    for guard in selected_guards(config).get("codex", []):
        key = keys.get(installed_command(guard, home, "codex"))
        if key is not None and not state.get(key, {}).get("trusted_hash"):
            pending.append(guard.name)
    return pending


def check_pending(config: HomeConfig, home: Path) -> int:
    """Report the guards still waiting for approval by name, writing nothing."""
    pending = pending_guards(config, home)
    if not pending:
        return 0
    for name in pending:
        print(f"pending approval: Codex skips guard {name}")
    print(APPROVE)
    return 1


def codex_guards_move(home: Path, intended: list[Entry]) -> bool:
    """True when installing *intended* adds, changes or removes a guard Codex holds."""
    drift = entry_drift(home, intended, read_ledger(home))
    return any(item.rel == CODEX_GUARDS for item in drift)
