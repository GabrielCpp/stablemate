from __future__ import annotations

import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from ostler_qa_diagnostics import (
    _CREDENTIAL_HEADERS,
    _ID_TOKEN,
    _PROCESS_START,
    CEILING_S,
    CheckFailed,
    FixtureFault,
    HttpError,
    _Recorder,
)
from ostler_qa_dsl import REGISTRY, Target
from ostler_qa_grpc import Caller, Grpc, GrpcError, GrpcurlCaller
from ostler_qa_http import ClaimFault, Exchange, ExchangeEvidence, Http
from ostler_qa_responses import reply_excerpt
from ostler_qa_tools import Convert, Maestro, Tesseract

if TYPE_CHECKING:
    from ostler_qa import Qa

class QaState:
    """The ledger, captures and exchange evidence every scenario call writes to."""

    def __init__(
        self,
        *,
        scenario_id: str,
        target: Target,
        root: Path,
        spec_dir: Path,
        qa_dir: Path,
        covers: Sequence[str],
        recorder: _Recorder,
        offset_base_ms: int = 0,
        fixtures: Mapping[str, Mapping[str, Any]] | None = None,
        tool_env: Sequence[str] = (),
        ceiling_s: float = CEILING_S,
        grpc_caller: Caller | None = None,
    ) -> None:
        self.ceiling_s = ceiling_s
        self.scenario_id = scenario_id
        self.target = target
        self.root = root
        self.spec_dir = spec_dir
        self.dir = qa_dir
        self.covers = list(covers)
        self._fixtures = {name: dict(spec) for name, spec in (fixtures or {}).items()}
        self._node_facts: dict[str, dict[str, str]] = {}
        self._node_structures: dict[str, dict[str, Any]] = {}
        self._last_fault: FixtureFault | None = None
        self._tool_env_allowed = frozenset(tool_env)
        self._recorder = recorder
        self._captures: dict[str, str] = {}
        self._exchange: ExchangeEvidence | None = None
        self._claim_fault: ClaimFault | None = None
        self._held: list[str] = []
        self._node: str | None = None
        self.http = Http(target.base_url, on_unexpected_status=self._status_mismatch, on_exchange=self._saw_exchange)

        self._grpc_caller = grpc_caller
        self.grpc = Grpc(target.base_url, self._grpc_caller_for, on_unexpected_status=self._grpc_status_mismatch)
        self._index = 0
        self.assertions = 0
        self.failures = 0
        self.offset_base_ms = offset_base_ms
        self.page: Any = None
        self.diagnostics: Any = None
        self.maestro = Maestro(cast("Qa", self))
        self.tesseract = Tesseract(cast("Qa", self))
        self.convert = Convert(cast("Qa", self))

    def http_for(self, target_name: str) -> Http:
        """An HTTP client bound to another declared target's `base_url` — one journey may reach several servers.

        The target must be named by this plan's own `target(...)` declarations; requests through
        the returned client record and status-check exactly like the scenario's own.
        """
        declared = REGISTRY.targets.get(target_name)
        if declared is None:
            raise ValueError(f"this plan declares no target {target_name!r} to send a request to")
        if declared.base_url is None:
            raise ValueError(f"target {target_name!r} declares no base_url to send a request to")
        return Http(declared.base_url, on_unexpected_status=self._status_mismatch,
                    on_exchange=self._saw_exchange)

    def _grpc_caller_for(self) -> Caller:
        """The caller `qa.grpc` makes its calls with: the one a test handed over, else grpcurl found on PATH."""
        if self._grpc_caller is None:
            if shutil.which("grpcurl") is None:
                self._claim_fault = ClaimFault("capability", "qa-tool-grpcurl", "")
                raise RuntimeError("qa tool 'grpcurl' is not on PATH")
            self._grpc_caller = GrpcurlCaller("grpcurl")
        return self._grpc_caller

    def _grpc_status_mismatch(
        self, method: str, address: str, status: str, allowed: Sequence[str], message: str
    ) -> None:
        """Write down an `expect_status` the product did not meet, with what it replied, before it raises."""
        self._record(
            f"{method} on {address} answers {list(allowed)}",
            False,
            {"status": status, "message": reply_excerpt(message)} if message.strip() else {"status": status},
            list(allowed),
            self.covers,
        )

    def _saw_exchange(self, exchange: Exchange) -> None:
        """Keep what the last request asked and got, and which precondition issued the credential it sent, never the credential itself."""
        sent = [value for key, value in exchange.headers.items() if key.lower() in _CREDENTIAL_HEADERS and value.strip()]
        self._exchange = ExchangeEvidence(
            method=exchange.method,
            path=urllib.parse.urlsplit(exchange.url).path,
            status=exchange.status,
            expected=exchange.expected,
            credential_sent=bool(sent),
            precondition="",
            invented=self._invented_ids(exchange),
        )

    def _invented_ids(self, exchange: Exchange) -> list[str]:
        """Each id-shaped value the request's path, query or body carried that no precondition fact and no capture holds."""
        known = {
            token.lower()
            for value in [*(fact for facts in self._node_facts.values() for fact in facts.values()), *self._captures.values()]
            for token in _ID_TOKEN.findall(value)
        }
        split = urllib.parse.urlsplit(exchange.url)
        sent = f"{split.path}?{split.query} " + (exchange.body or b"").decode("utf-8", errors="replace")
        return list(dict.fromkeys(token for token in _ID_TOKEN.findall(sent) if token.lower() not in known))

    def _status_mismatch(
        self, method: str, url: str, status: int, allowed: Sequence[int], reply: str
    ) -> None:
        """Write down an `expect_status` the product did not meet, with what it replied, before it raises."""
        self._record(
            f"{method} {url} answers {list(allowed)}",
            False,
            {"code": status, "reply": reply_excerpt(reply)} if reply.strip() else status,
            list(allowed),
            self.covers,
        )

    def _record(
        self,
        label: str,
        condition: Any,
        actual: Any,
        expected: Any,
        covers: Sequence[str] | None,
        *,
        extra: Mapping[str, Any] | None = None,
    ) -> bool:
        passed = bool(condition)
        self._index += 1
        self.assertions += 1
        if not passed:
            self.failures += 1
        record: dict[str, Any] = {
            "type": "assert",
            "id": f"{self.scenario_id}-{self._index}",
            "label": label,
            "passed": passed,
            "actual": actual,
            "expected": expected,
            "covers": list(covers) if covers is not None else [],
        }
        if self._node is not None:
            record["node"] = self._node
        if not passed:
            if self._exchange is not None:
                record["exchange"] = asdict(self._exchange)
            if self._claim_fault is not None:
                record["fault"] = asdict(self._claim_fault)
            if self._held:
                record["held"] = list(self._held)
        if extra:
            record.update(extra)
        self._recorder.emit(record)
        return passed

    def _fault(self, fixture: str, step_index: int, step_kind: str, fault_class: str, detail: str) -> None:
        fault = FixtureFault(
            fixture=fixture, step_index=step_index, step_kind=step_kind,
            fault_class=fault_class, detail=detail,
        )
        self._recorder.emit({"type": "fixture_fault", **asdict(fault)})
        self._last_fault = fault
        self._claim_fault = ClaimFault(fault_class, fixture, "")

    def stop_evidence(self, exc: BaseException) -> dict[str, Any]:
        """What stopped the scenario: the last request and the fixture fault it met, and the exception's type when no request explains it."""
        evidence: dict[str, Any] = {}
        if self._exchange is not None:
            evidence["exchange"] = asdict(self._exchange)
        if self._claim_fault is not None:
            evidence["fault"] = asdict(self._claim_fault)
        if self._held:
            evidence["held"] = list(self._held)
        if not isinstance(exc, HttpError | GrpcError):
            evidence["raised"] = type(exc).__name__
        return evidence

    @contextmanager
    def at_node(self, ref: str) -> Iterator[None]:
        """Record the checks inside against the book node `ref`, and stop the scenario after them when any failed."""
        failed_before = self.failures
        self._node = ref
        try:
            yield
        finally:
            self._node = None
        if self.failures > failed_before:
            raise CheckFailed(ref)

    @contextmanager
    def claim(self, covers: Sequence[str]) -> Iterator[None]:
        """Run one claim's request and checks, so a claim that fails is recorded against it alone and the scenario goes on to the next."""
        scenario_covers = self.covers
        self.covers = list(covers)
        self._exchange = None
        self._claim_fault = None
        try:
            yield
        except CheckFailed:
            pass
        except (HttpError, GrpcError) as exc:
            if not exc.recorded:
                _ = self._record(str(exc), False, str(exc), "a response", covers)
        except Exception as exc:
            _ = self._record(
                f"the claim raised {type(exc).__name__}", False, str(exc), "no error", covers,
                extra={"raised": type(exc).__name__},
            )
        finally:
            self.covers = scenario_covers
            self._claim_fault = None

    @contextmanager
    def step(self, label: str) -> Iterator[None]:
        """Group the work of one phase under a named step record in the ledger."""
        self._index += 1
        step_id = f"{self.scenario_id}-step-{self._index}"
        self._recorder.emit(
            {"type": "step_start", "id": step_id, "label": label, "offset_ms": self.offset_ms()}
        )
        try:
            yield
        except BaseException as exc:
            self._recorder.emit(
                {
                    "type": "step_end",
                    "id": step_id,
                    "label": label,
                    "failed": True,
                    "error": repr(exc),
                    "offset_ms": self.offset_ms(),
                }
            )
            raise
        self._recorder.emit(
            {"type": "step_end", "id": step_id, "label": label, "failed": False, "offset_ms": self.offset_ms()}
        )

    def capture(self, key: str, value: Any) -> None:
        """Publish a value into the run ledger so a later report can name it."""
        self._captures[key] = str(value)
        self._recorder.emit({"type": "capture", "key": key, "value": str(value)})

    def get(self, key: str) -> str:
        return self._captures[key]

    def artifact(self, path: str | Path, *, kind: str) -> Path:
        """Register a file — or a directory of files — as evidence."""
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = self.dir / resolved
        resolved.parent.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {"type": "artifact", "path": str(resolved), "kind": kind}
        if resolved.is_dir():
            record["directory"] = True
        self._recorder.emit(record)
        return resolved

    def secret(self, name: str) -> str:
        declared = REGISTRY.secrets.get(name)
        if declared is None:
            raise KeyError(f"secret {name!r} is not declared in this plan")
        return declared.get()

    def offset_ms(self) -> int:
        """Now, on the run's clock — the same scale every other driver's records use."""
        return self.offset_base_ms + round((time.monotonic() - _PROCESS_START) * 1000)
