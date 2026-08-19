"""`farrier doctor` — read a repo's `agents.yml` and say what a workflow will miss.

Everything the coder workflow does to a repo it does from declarations: the `workspace:`
block says where the services are, and the `services:` block says what command gates each
one. A missing declaration is never an error at run time — the dev lane skips a gate no
service adopted, on purpose, because guessing a command means failing a story on a command
nobody wrote. The cost is that the silence is indistinguishable from a repo that meant it,
and a repo that simply forgot finds out several stories later that nothing was ever checked.

That gap is what this command closes. It warns; it does not fail. The exit code is 0 for
any repo whose `agents.yml` parses, because "you have not adopted the test gate" is a fact
about the repo's choices and not a defect in it — the one non-zero case is a config that
cannot be read at all, which is a defect in it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

#: The gates the coder workflow's dev lane runs, in the order it asks for them. Kept here
#: rather than imported: farrier installs into repos that have no workflow package at all,
#: and a doctor that could not run without one would be useless in exactly the repo that
#: most needs telling.
GATES = ("lint", "test")


@dataclass(frozen=True)
class Finding:
    """One thing worth telling the repo's owner, and what to do about it."""

    level: str
    message: str


def _services_block(config: dict[str, Any]) -> dict[str, Any]:
    """The `services:` mapping, top-level or nested under `workflow:`."""
    block = config.get("services") or (config.get("workflow") or {}).get("services") or {}
    return block if isinstance(block, dict) else {}


def diagnose(repo: Path) -> list[Finding]:
    """Everything `agents.yml` in *repo* leaves the coder workflow unable to do."""
    path = repo / "agents.yml"
    if not path.is_file():
        return [
            Finding(
                "error",
                f"no agents.yml in {repo} — run `farrier init` to write a starter one.",
            )
        ]
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return [Finding("error", f"agents.yml could not be read: {exc}")]
    if not isinstance(config, dict):
        return [Finding("error", "agents.yml is not a YAML mapping.")]

    findings: list[Finding] = []
    workspace = config.get("workspace")
    workspace = workspace if isinstance(workspace, dict) else {}
    roots = [str(r) for r in (workspace.get("service_roots") or [])]
    if not roots:
        findings.append(
            Finding(
                "warning",
                "workspace.service_roots is empty — a planner has no service to target, "
                "so every story dispatches one layer at the repo root.",
            )
        )
    if not (workspace.get("service_markers") or []):
        findings.append(
            Finding(
                "warning",
                "workspace.service_markers is empty — nothing proves a service directory "
                "is really there, so a plan naming a missing path is caught late.",
            )
        )

    services = _services_block(config)
    legacy_lint = config.get("lint") or (config.get("workflow") or {}).get("lint") or {}
    if not services:
        findings.append(
            Finding(
                "warning",
                "no services: block — the dev lane will skip every gate. Declare the "
                "commands that check a service, keyed by its name or its type:\n"
                "    services:\n"
                "      <service-or-type>:\n"
                + "".join(f"        {gate}: <command>\n" for gate in GATES).rstrip("\n"),
            )
        )
    else:
        for name, entry in services.items():
            if not isinstance(entry, dict):
                findings.append(
                    Finding("warning", f"services.{name} is not a mapping — it is ignored.")
                )
                continue
            missing = [
                gate
                for gate in GATES
                if not str(entry.get(gate) or "").strip()
                and not (gate == "lint" and isinstance(legacy_lint, dict) and legacy_lint.get(name))
            ]
            if missing:
                findings.append(
                    Finding(
                        "warning",
                        f"services.{name} declares no {' or '.join(missing)} command — "
                        f"{'that gate is' if len(missing) == 1 else 'those gates are'} "
                        "skipped for it, never guessed at.",
                    )
                )

    undeclared = [
        root
        for root in roots
        if Path(root).name not in services and root not in services
    ]
    if services and undeclared:
        findings.append(
            Finding(
                "warning",
                "these service roots match no services: key, so they are gated by type "
                "only (or not at all): " + ", ".join(undeclared),
            )
        )
    return findings


def report(repo: Path) -> int:
    """Print the diagnosis. Non-zero only when `agents.yml` could not be read."""
    findings = diagnose(repo)
    if not findings:
        print(f"agents.yml in {repo}: nothing to report.")
        return 0
    for finding in findings:
        print(f"{finding.level}: {finding.message}")
    errors = sum(1 for f in findings if f.level == "error")
    warnings = len(findings) - errors
    print(f"\n{errors} error(s), {warnings} warning(s).")
    return 1 if errors else 0
