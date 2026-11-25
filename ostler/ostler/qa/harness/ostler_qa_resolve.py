from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from ostler_qa_diagnostics import _CAPTURE_REF, _NODE_REF, MISSING
from ostler_qa_dsl import REGISTRY
from ostler_qa_files import checkout_files
from ostler_qa_paths import is_projection, resolve_path
from ostler_qa_state import QaState
from ostler_qa_tools import Tool, ToolResult
from ostler_qa_verifiers import (
    Tree,
)

if TYPE_CHECKING:
    from ostler_qa import Qa

class QaResolve(QaState):
    """References, fixtures and captured values resolved into request data."""

    def tool(self, name: str) -> "Tool":
        """An external command found on PATH."""
        return Tool(cast("Qa", self), name, name)

    def tree(self, where: str | Path) -> Tree:
        """Every file under *where* in the run's qa directory, read once, so a differential check can compare the reads either side of an action."""
        base = self.dir.resolve()
        root = (base / where).resolve()
        if not root.is_relative_to(base):
            raise ValueError(
                f"qa.tree: {str(where)!r} must stay inside the run's qa directory ({base})"
            )
        return Tree(root)

    def checkout_tree(self) -> Tree:
        """Every file the checkout holds, less its ignored directories and the run's qa directory, read once, so a differential check can compare the reads either side of an action."""
        root = self.root.resolve()
        return Tree(root, checkout_files(root, self.dir.resolve()))

    def fixture(self, name: str, *args: str) -> "ToolResult":
        """Put the product into a state this repo declared, and write down that it happened."""
        spec = self._fixtures.get(name)
        if spec is None:
            declared = ", ".join(sorted(self._fixtures)) or "(none declared)"
            raise RuntimeError(
                f"qa fixture {name!r} is not declared — add it to this repo's agents.yml "
                f"under `qa: {{fixtures: {{{name}: ...}}}}`. Declared here: {declared}"
            )
        argv = [*spec.get("args", []), *args]
        result = self.tool(str(spec["tool"])).run(*argv, timeout=float(spec.get("timeout", 120.0)))
        self._recorder.emit(
            {
                "kind": "fixture",
                "scenario": self.scenario_id,
                "name": name,
                "provides": spec.get("provides", ""),
                "command": result.command,
                "exit_code": result.exit_code,
                "ok": result.ok,
            }
        )
        if not result.ok:
            raise RuntimeError(
                f"qa fixture {name!r} failed (exit {result.exit_code}) and the state it "
                f"promises — {spec.get('provides', '')!r} — is not there: "
                f"{(result.stderr or result.stdout).strip()[:500]}"
            )
        return result

    def _resolve_ref(self, owner: str, value: str) -> str:
        """*value*, with every embedded `@node.key` and `$name` reference substituted."""
        failures: list[str] = []
        spans: list[tuple[int, int, str]] = []
        for match in _NODE_REF.finditer(value):
            node, key = match.group(1), match.group(2)
            facts = self._node_facts.get(node)
            if facts is None or key not in facts:
                detail = (
                    f"reference @{node}.{key} has no resolved value — "
                    f"{node!r} has not run (or does not provide {key!r})"
                )
                self._fault(owner, -1, "reference", "defect", detail)
                failures.append(detail)
                continue
            spans.append((match.start(), match.end(), facts[key]))
        for match in _CAPTURE_REF.finditer(value):
            captured = match.group(1)
            declared = REGISTRY.secrets.get(captured)
            if captured not in self._captures and declared is not None:
                spans.append((match.start(), match.end(), declared.get()))
                continue
            if captured not in self._captures:
                detail = f"reference ${captured} has no resolved value — nothing has captured it"
                self._fault(owner, -1, "reference", "defect", detail)
                failures.append(detail)
                continue
            spans.append((match.start(), match.end(), self._captures[captured]))
        if failures:
            raise RuntimeError(f"qa {owner!r}: " + "; ".join(failures))
        spans.sort(key=lambda span: span[0])
        out: list[str] = []
        cursor = 0
        for start, end, replacement in spans:
            out.append(value[cursor:start])
            out.append(replacement)
            cursor = end
        out.append(value[cursor:])
        return "".join(out)

    def resolve(self, value: str) -> str:
        """A scenario's own value, with every embedded `@node.key`/`$name` substituted."""
        return self._resolve_ref(self.scenario_id, value)

    def resolve_body(self, value: str) -> Any:
        """A body member's value: the object or array itself when *value* is one whole `@node.key` reference to one, `resolve()` otherwise."""
        whole = _NODE_REF.fullmatch(value)
        if whole is not None and whole.group(2) in self._node_structures.get(whole.group(1), {}):
            return self._node_structures[whole.group(1)][whole.group(2)]
        return self.resolve(value)

    def _resolve_value(self, value: Any) -> Any:
        """`resolve()`, recursively, for a JSON-shaped dict/list body."""
        if isinstance(value, str):
            return self.resolve(value)
        if isinstance(value, dict):
            return {key: self._resolve_value(v) for key, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_value(v) for v in value]
        return value

    def capture_field(self, key: str, data: Any, path: str) -> Any:
        """Capture a JSON-path read from observed data — a defect if the path finds nothing."""
        value = self.field(data, path)
        if value is MISSING:
            detail = f"capture {key!r} from {path!r} found nothing in the observed data"
            self._fault(self.scenario_id, -1, "capture", "defect", detail)
            raise RuntimeError(f"qa {self.scenario_id!r}: {detail}")
        self.capture(key, value)
        return value

    def scenario_env(self, env: Mapping[str, str]) -> dict[str, str]:
        """*env* with each `$NAME` expanded from this process and each relative path resolved against the checkout.

        An entry of a value split on the path separator is a path when it is relative and either
        holds a slash or names something that exists in the checkout. A value such as
        `0` or `claude` stays as written.
        """
        base = self.root.resolve()
        return {name: self._resolved_env_value(os.path.expandvars(value), base) for name, value in env.items()}

    @staticmethod
    def _resolved_env_value(value: str, base: Path) -> str:
        entries = []
        for entry in value.split(os.pathsep):
            relative = bool(entry) and not os.path.isabs(entry)
            if relative and ("/" in entry or (base / entry).exists()):
                entry = str(base / entry)
            entries.append(entry)
        return os.pathsep.join(entries)

    def field(self, data: Any, path: str, default: Any = MISSING) -> Any:
        """Read one value out of observed product data without ever raising."""
        try:
            hit = resolve_path(data, path)
        except ValueError:
            return default
        if not hit.found:
            return default
        if is_projection(path) and isinstance(hit.value, list) and len(hit.value) == 1:
            return hit.value[0]
        return hit.value
