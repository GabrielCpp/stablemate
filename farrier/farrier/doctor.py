"""`farrier doctor` — read a repo's `agents.yml` and say what a workflow will miss."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from farrier._vendor.stablemate_core.config import ConfigError
from farrier._vendor.stablemate_core.manifest import load_manifest, locate_manifest

GATES = ("lint", "test")


@dataclass(frozen=True)
class Finding:
    """One thing worth telling the repo's owner, and what to do about it."""

    level: str
    message: str


def diagnose(repo: Path) -> list[Finding]:
    """Everything `agents.yml` in *repo* leaves the coder workflow unable to do."""
    path = locate_manifest(repo)
    if path is None:
        return [
            Finding(
                "error",
                f"no agents.yml in {repo} — run `farrier init` to write a starter one.",
            )
        ]
    try:
        config = load_manifest(path)
    except ConfigError as exc:
        return [Finding("error", f"{path.name} could not be read: {exc}")]

    findings: list[Finding] = []
    if "workspace" in (config.model_extra or {}):
        findings.append(
            Finding(
                "error",
                "agents.yml still has a workspace: section, which nothing reads any more. "
                "Move each service root to services.<name>.path, move base_branch to repo:, "
                "drop qa_mode, qa_skills and verification, and delete the section.",
            )
        )

    services = config.services
    legacy_lint = config.lint
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
            declared_path = entry.path
            if declared_path is not None and not (repo / str(declared_path)).exists():
                findings.append(
                    Finding(
                        "error",
                        f"services.{name}.path {declared_path!s} does not exist in {repo}.",
                    )
                )
            missing = [
                gate
                for gate in GATES
                if not str(getattr(entry, gate) or "").strip()
                and not (gate == "lint" and legacy_lint.get(name))
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

    return findings


def report(repo: Path) -> int:
    """Print the diagnosis."""
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
