from __future__ import annotations

import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import ostler_qa_diagnostics
from ostler_qa_elements import maestro_pattern
from ostler_qa_http import ClaimFault
from ostler_qa_verifiers import (
    JsonValue,
    json_value,
)

if TYPE_CHECKING:
    from ostler_qa import Qa


class Maestro:
    """Run a Maestro flow from inside the scenario, and hand back what it did."""

    def __init__(self, qa: Qa) -> None:
        self._qa = qa

    def flow(self, commands: Sequence[Any]) -> str:
        """Build flow text from Maestro commands."""
        app_id = self._qa.target.app_id
        if not app_id:
            raise ValueError(f"target '{self._qa.target.name}' declares no app_id")
        return json.dumps({"appId": app_id}) + "\n---\n" + json.dumps(list(commands), indent=2)

    def pattern(self, name: str = "", *, text: str | None = None) -> str:
        """The Maestro `text:` regex for the element the book calls *name*, holding *text* when given."""
        return maestro_pattern(name, text=text)

    def run(
        self,
        flow: str | Path,
        *,
        name: str = "",
        timeout: float = 600.0,
        require: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> MaestroResult:
        if shutil.which("maestro") is None:
            raise RuntimeError("the maestro CLI is not installed on this machine")
        qa = self._qa
        label = name or qa.scenario_id
        if isinstance(flow, Path):
            path = flow
        else:
            path = qa.dir / "generated" / f"{label}.yaml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(flow, encoding="utf-8")
            qa.artifact(path, kind="generated-maestro-flow")
        junit = qa.dir / "traces" / f"{label}-junit.xml"
        junit.parent.mkdir(parents=True, exist_ok=True)
        test_output = qa.dir / "generated" / f"{label}-maestro-output"
        test_output.mkdir(parents=True, exist_ok=True)
        command = [
            "maestro", "test",
            *(part for key, value in sorted((env or {}).items()) for part in ("-e", f"{key}={value}")),
            "--format", "junit",
            "--output", str(junit),
            "--test-output-dir", str(test_output),
            str(path),
        ]
        ostler_qa_diagnostics.harness_module("ostler_qa_hierarchy").release_device()
        try:
            done = subprocess.run(  # noqa: S603 - fixed argv, flow path built above
                command, cwd=qa.root, capture_output=True, text=True, timeout=timeout, check=False
            )
            output, code = f"{done.stdout}{done.stderr}", done.returncode
        except subprocess.TimeoutExpired as exc:
            output = f"{exc.stdout or ''}{exc.stderr or ''}"
            code = 124
        log = qa.dir / "traces" / f"{label}-maestro.txt"
        log.write_text(output, encoding="utf-8")
        qa.artifact(log, kind="maestro-output")
        if junit.is_file():
            qa.artifact(junit, kind="junit")
        for produced in sorted(test_output.rglob("*")):
            if produced.is_file() and produced.stat().st_size:
                kind = (
                    "maestro-screenshot"
                    if produced.suffix.lower() == ".png"
                    else "maestro-diagnostic"
                )
                qa.artifact(produced, kind=kind)
        seen = _maestro_seen(junit, output) if code != 0 else ""
        if require and code != 0:
            tail = "\n".join(output.strip().splitlines()[-10:])
            raise RuntimeError(f"maestro flow {path.name} exited {code}:\n{tail}\n{seen}")
        return MaestroResult(exit_code=code, output=output, flow=path, seen=seen)


def _failing_step(junit: Path, output: str) -> str:
    if junit.is_file():
        try:
            failure = ET.parse(junit).getroot().find(".//failure")  # noqa: S314 - maestro's own report
        except (ET.ParseError, OSError):
            failure = None
        if failure is not None:
            text = (failure.get("message") or failure.text or "").strip()
            if text:
                return text
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _maestro_seen(junit: Path, output: str) -> str:
    seen = f"maestro stopped at: {_failing_step(junit, output)}"
    try:
        reading = ostler_qa_diagnostics.harness_module("ostler_qa_hierarchy").DeviceScreen().read(30)
        inventory = reading.inventory() if reading is not None else ""
    except Exception as exc:
        return f"{seen}. The screen could not be read: {type(exc).__name__}"
    return f"{seen}. The screen showed: {inventory}" if inventory else seen


@dataclass
class MaestroResult:
    exit_code: int
    output: str
    flow: Path
    seen: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass
class ToolResult:
    command: list[str]
    stdout: str
    stderr: str
    exit_code: int

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def json(self) -> JsonValue:
        """Parse stdout as JSON, naming the command and a stdout excerpt when it is not."""
        try:
            return json_value(json.loads(self.stdout))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{' '.join(self.command)} exited {self.exit_code} with a stdout that is not JSON: "
                f"{self.stdout[:200]!r}"
            ) from exc


class Tool:
    """One external command found on PATH."""

    def __init__(self, qa: Qa, name: str, command: str) -> None:
        self._qa = qa
        self.name = name
        self._command = command

    def run(
        self,
        *args: str,
        timeout: float = 60.0,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> ToolResult:
        """Run the tool once, from the repo root unless *cwd* says where, with *env* overlaid."""
        if shutil.which(self._command) is None:
            self._qa._claim_fault = ClaimFault("capability", f"qa-tool-{self.name}", "")
            raise RuntimeError(f"qa tool {self.name!r} is not on PATH")
        argv = [self._command, *args]
        where = self._qa.root if cwd is None else self._cwd(cwd)
        overlay = None if env is None else {**os.environ, **self._env(env)}
        try:
            done = subprocess.run(  # noqa: S603 - argv built from a config-declared command
                argv,
                cwd=where,
                env=overlay,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return ToolResult(command=argv, stdout=done.stdout, stderr=done.stderr, exit_code=done.returncode)
        except subprocess.TimeoutExpired as exc:
            return ToolResult(
                command=argv,
                stdout=str(exc.stdout) if exc.stdout else "",
                stderr=str(exc.stderr) if exc.stderr else "",
                exit_code=124,
            )

    def _cwd(self, cwd: str | Path) -> Path:
        base = self._qa.dir.resolve()
        candidate = Path(cwd)
        resolved = (candidate if candidate.is_absolute() else base / candidate).resolve()
        if not resolved.is_relative_to(base):
            raise ValueError(
                f"qa tool {self.name!r}: cwd {str(cwd)!r} must stay inside the run's qa "
                f"directory ({base})"
            )
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    def _env(self, env: Mapping[str, str]) -> dict[str, str]:
        undeclared = sorted(name for name in env if name not in self._qa._tool_env_allowed)
        if undeclared:
            raise ValueError(
                f"qa tool {self.name!r}: env name(s) {', '.join(undeclared)} are not declared "
                "— add them to the plan's tool_env(...) so validation can see them"
            )
        return {name: str(value) for name, value in env.items()}


class Tesseract:
    """OCR over an image, via the `tesseract` CLI on PATH."""

    def __init__(self, qa: Qa) -> None:
        self._qa = qa

    def ocr(self, image: str | Path, *, timeout: float = 60.0) -> str:
        result = self._qa.tool("tesseract").run(str(image), "stdout", timeout=timeout)
        if not result.ok:
            raise RuntimeError(f"tesseract failed on {image}: {result.stderr or result.stdout}")
        return result.stdout


class Convert:
    """Resize (and, over time, other transforms) via ImageMagick's `convert`."""

    def __init__(self, qa: Qa) -> None:
        self._qa = qa

    def resize(
        self,
        image: str | Path,
        width: int,
        height: int,
        *,
        out: str | Path | None = None,
        timeout: float = 60.0,
    ) -> Path:
        src = Path(image)
        dest = (
            Path(out)
            if out is not None
            else self._qa.dir / "generated" / f"{src.stem}-{width}x{height}{src.suffix}"
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        result = self._qa.tool("convert").run(
            str(src), "-resize", f"{width}x{height}", str(dest), timeout=timeout
        )
        if not result.ok:
            raise RuntimeError(f"convert failed on {image}: {result.stderr or result.stdout}")
        self._qa.artifact(dest, kind="resized-image")
        return dest
