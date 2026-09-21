"""Render one node and drive retry → cap-wait → compact → reframe → stop."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from workhorse._vendor.stablemate_core.config import (
    UnknownProfileError,
    load_config,
    profile_has_backend,
    resolve_backend_default,
    resolve_power,
    select_profile,
)
from workhorse import control, otel, reload
from workhorse.artifacts import write_unlinked
from workhorse.config_run import AgentResilience, RunConfig
from workhorse.context import WorkflowContext
from workhorse.runner.caps import cap_delay_seconds, sleep_with_notice
from workhorse._vendor.stablemate_core.clock import SYSTEM_CLOCK, Clock
from workhorse.runner.extract import extract_outputs
from workhorse.runner.failure import (
    BackendInvocationError,
    OutputParseError,
    error_kind,
    is_cap,
    is_unresumable_session,
)
from workhorse.runner.reframe import (
    rephrase_prompt,
    retry_prompt,
    timeout_retry_prompt,
)
from workhorse.runner.spec import AgentNode
from workhorse.runner.waits import (
    RecoveryWaitBudget,
    active_recovery_wait_budget,
    recovery_wait_scope,
)
from workhorse.templates import render, render_string

if TYPE_CHECKING:
    from workhorse.runner.backends import AgentBackend


def _write_prompt_for_inspection(node_id: str, prompt: str, run_dir: Path | None) -> Path | None:
    """Persist the rendered prompt before invocation so failed nodes are inspectable."""
    if run_dir is None:
        return None
    prompt_path = run_dir / node_id / "prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    write_unlinked(prompt_path, prompt)
    return prompt_path


def _print_prompt_path(node_id: str, prompt_path: Path) -> None:
    """Echo where the rendered prompt was written, without dumping variables."""
    print(f"[{node_id}] prompt: {prompt_path}", flush=True)


_warned_missing_profile: set[str] = set()


def _profile_config(profile: str) -> dict[str, Any] | None:
    """The config the resolvers below read: narrowed to ``profile``, or the whole file."""
    if not profile:
        return None
    try:
        return select_profile(load_config(), profile)
    except UnknownProfileError as exc:
        if profile not in _warned_missing_profile:
            _warned_missing_profile.add(profile)
            print(f"[workhorse] WARNING: {exc}; resolving no models from it", flush=True)
        return {}


def resolved_profile(profile: str) -> dict[str, Any]:
    """What ``profile`` holds right now, for the record rather than for a resolution."""
    return _profile_config(profile) or {}


@dataclass
class ProfileSelection:
    """Which named model set the run is on *now* — one box every frame shares."""

    name: str = ""


def switch_profile(runner: "AgentRunner | None", name: str) -> dict[str, object]:
    """Move a live run onto the ``name`` model set, and say what happened."""
    if runner is None:
        return {"ok": False, "error": "this run drives no agent, so it resolves no models"}
    try:
        tables = select_profile(load_config(), name)
    except UnknownProfileError as exc:
        return {"ok": False, "error": str(exc)}
    backend = runner.backend.name
    if not profile_has_backend(tables, backend):
        return {
            "ok": False,
            "error": f"profile {name!r} declares cli = {tables.get('cli')!r} which does "
            f"not match the CLI backend {backend!r} this run is driving. Switch-cli "
            f"first, or pick a profile whose cli matches the new backend.",
        }
    was, runner.profile.name = runner.profile.name, name
    _warned_missing_profile.discard(name)
    otel.run_attribute("workhorse.profile", name)
    return {"ok": True, "profile": name, "was": was}


def _resolve_power_settings(
    power: str | None,
    backend_name: str,
    model_override: str | None,
    profile: str = "",
) -> tuple[str | None, str | None, float]:
    """Resolve a node's abstract ``power`` into concrete backend settings."""
    cfg = _profile_config(profile)
    mapped = resolve_power(power, backend_name, cfg)
    fallback = resolve_backend_default(backend_name, cfg)
    model = mapped.model or model_override or fallback.model
    scale = mapped.timeout_scale or fallback.timeout_scale or 1.0
    return model, mapped.effort or fallback.effort, scale


@dataclass(frozen=True)
class AgentRunner:
    """The fail-soft recovery ladder, for one run."""

    backend: AgentBackend
    resilience: AgentResilience = field(default_factory=AgentResilience)
    clock: Clock = SYSTEM_CLOCK
    print_prompt: bool = True
    model_override: str | None = None
    profile: ProfileSelection = field(default_factory=ProfileSelection)

    @classmethod
    def from_config(cls, config: RunConfig, *, clock: Clock = SYSTEM_CLOCK) -> AgentRunner:
        """The ladder this run's configuration describes."""
        return cls(
            backend=config.backend,
            resilience=config.resilience,
            clock=clock,
            print_prompt=config.print_prompt,
            model_override=config.model_override,
            profile=ProfileSelection(config.profile),
        )

    def run(
        self,
        node: AgentNode,
        context: WorkflowContext,
        workflow_dir: Path,
        session_id_path: Path | None = None,
        *,
        resume_session: bool = False,
        session_chain: str = "",
        run_dir: Path | None = None,
        validate: Callable[[dict[str, Any]], object] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Run one node with cumulative recovery waits that nested retries cannot renew."""
        budget = RecoveryWaitBudget.from_resilience(self.resilience)
        with recovery_wait_scope(budget):
            return self._run(
                node,
                context,
                workflow_dir,
                session_id_path,
                resume_session=resume_session,
                session_chain=session_chain,
                run_dir=run_dir,
                validate=validate,
            )

    def _run(
        self,
        node: AgentNode,
        context: WorkflowContext,
        workflow_dir: Path,
        session_id_path: Path | None = None,
        *,
        resume_session: bool = False,
        session_chain: str = "",
        run_dir: Path | None = None,
        validate: Callable[[dict[str, Any]], object] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Render the prompt, invoke the agent, and parse its declared outputs — resiliently."""
        node_id = node.id
        resilience = self.resilience
        ctx = context.as_dict()

        model, node_effort, timeout_scale = _resolve_power_settings(
            node.power, self.backend.name, self.model_override, self.profile.name
        )
        model = model or self.backend.default_model

        base_timeout = (
            node.timeout
            if node.timeout is not None and node.timeout > 0
            else resilience.result_timeout_s
        )
        effective_timeout = base_timeout * timeout_scale
        unbounded = effective_timeout == float("inf")

        rendered_cwd = render_string(node.cwd, ctx).strip() if node.cwd else None

        rendered_args = {k: render_string(v, ctx) for k, v in node.args.items()}
        prompt_ctx = {
            **ctx,
            **rendered_args,
            "node_timeout_s": "unbounded" if unbounded else int(effective_timeout),
            "node_timeout_min": "unbounded" if unbounded else int(round(effective_timeout / 60)),
            "_node_cwd": rendered_cwd or "",
        }
        rendered_prompt = render(node.prompt, prompt_ctx, workflow_dir)

        prompt_path = _write_prompt_for_inspection(node_id, rendered_prompt, run_dir)
        if prompt_path is not None and self.print_prompt:
            _print_prompt_path(node_id, prompt_path)

        if isinstance(node.add_dirs, str):
            bare = re.fullmatch(r"\{\{\s*(\w+)\s*\}\}", node.add_dirs.strip())
            if bare:
                native = ctx.get(bare.group(1), [])
                rendered_add_dirs = [str(d).strip() for d in (native if isinstance(native, list) else [native]) if d]
            else:
                rendered = render_string(node.add_dirs, ctx).strip()
                rendered_add_dirs = [rendered] if rendered else []
        else:
            rendered_add_dirs = [
                d for d in (render_string(d, ctx).strip() for d in node.add_dirs) if d
            ]

        if rendered_cwd and rendered_add_dirs:
            cwd_resolved = Path(rendered_cwd).resolve()
            rendered_add_dirs = [d for d in rendered_add_dirs if Path(d).resolve() != cwd_resolved]

        if not resume_session and session_id_path and session_id_path.exists():
            session_id_path.unlink()

        rephrase = 0
        rephrase_budget = (
            resilience.max_rephrase_attempts if node.retries is None else node.retries
        )
        compact_attempts = resilience.max_compact_attempts
        while True:
            prompt = (
                rendered_prompt
                if rephrase == 0
                else rephrase_prompt(rendered_prompt, node, rephrase)
            )
            if rephrase > 0:
                if session_id_path and session_id_path.exists():
                    session_id_path.unlink()
                print(
                    f"[{node_id}] 🔄 reframing prompt "
                    f"(attempt {rephrase}/{rephrase_budget})",
                    flush=True,
                )
            try:
                outputs = self._invoke_and_parse(
                    prompt, node, session_id_path, model,
                    prompt_path=prompt_path,
                    timeout=effective_timeout,
                    budget_scale=timeout_scale,
                    base_timeout_s=base_timeout,
                    cwd=rendered_cwd, add_dirs=rendered_add_dirs,
                    effort=node_effort,
                    validate=validate,
                )
                return rendered_prompt, outputs
            except (BackendInvocationError, OutputParseError) as exc:
                if (
                    isinstance(exc, BackendInvocationError)
                    and is_unresumable_session(str(exc))
                    and session_id_path
                    and session_id_path.exists()
                ):
                    session_id_path.unlink()
                    label = f"chain {session_chain}" if session_chain else "session"
                    print(
                        f"[{node_id}] ⚠ {label}: session not resumable, starting fresh",
                        flush=True,
                    )
                    otel.turn_event(
                        "session_unresumable", node=node_id, chain=session_chain
                    )
                    continue

                if (
                    isinstance(exc, BackendInvocationError)
                    and exc.overflow
                    and self.backend.supports_compaction
                    and compact_attempts > 0
                ):
                    compact_attempts -= 1
                    attempt_no = resilience.max_compact_attempts - compact_attempts
                    print(
                        f"[{node_id}] 🗜 context window exhausted; compacting session "
                        f"and continuing "
                        f"(attempt {attempt_no}/{resilience.max_compact_attempts})",
                        flush=True,
                    )
                    otel.turn_event("compact", node=node_id, attempt=attempt_no)
                    if self.backend.compact(
                        session_id_path,
                        node_id,
                        model,
                        timeout=resilience.result_timeout_s,
                        resilience=resilience,
                    ):
                        continue
                    print(
                        f"[{node_id}] ⚠ compaction unavailable/ineffective; "
                        f"falling back to reframe",
                        flush=True,
                    )

                if (
                    isinstance(exc, BackendInvocationError)
                    and not exc.transient
                    and not exc.overflow
                ):
                    print(
                        f"[{node_id}] ✖ non-recoverable {self.backend.name} failure: {exc}",
                        flush=True,
                    )
                    raise

                if rephrase < rephrase_budget:
                    print(
                        f"[{node_id}] ⚠ node failed ({exc}); will reframe and retry",
                        flush=True,
                    )
                    otel.turn_event("reframe", node=node_id, attempt=rephrase + 1)
                    delay = min(10 * (rephrase + 1), 60)
                    budget = active_recovery_wait_budget()
                    if budget is not None:
                        budget.consume("reframe", delay)
                    with otel.wait("reframe", node_id):
                        interrupted = control.wait_until(
                            None,
                            timeout=delay,
                            clock=self.clock,
                            channel=control.armed(),
                            tick=delay,
                        )
                    self._reenter_on(
                        reload.cut_by(interrupted), node_id, "a reframe pause"
                    )
                    rephrase += 1
                    continue

                print(
                    f"[{node_id}] ✖ all {rephrase_budget} reframings "
                    f"failed ({exc}); stopping the run — resume it once the cause is "
                    f"cleared",
                    flush=True,
                )
                otel.turn_event(
                    "exhausted",
                    error=True,
                    node=node_id,
                    error_class=type(exc).__name__,
                    error_kind=error_kind(exc),
                )
                raise

    def _reenter_on(self, cut: control.Request | None, node_id: str, where: str) -> None:
        """Unwind the ladder for a reload that ended one of its waits, or do nothing."""
        if cut is None:
            return
        print(f"[{node_id}] ⟳ reload requested during {where}", flush=True)
        otel.turn_event("reload_wait_cut", node=node_id, wait=where)
        raise reload.ReloadRequested(
            f"reload requested during {where}", core=cut.core, cli=cut.cli
        )

    def _invoke_and_parse(
        self,
        prompt: str,
        node: AgentNode,
        session_id_path: Path | None,
        model: str | None,
        *,
        prompt_path: Path | None = None,
        timeout: float,
        budget_scale: float = 1.0,
        base_timeout_s: float | None = None,
        cwd: str | None = None,
        add_dirs: list[str] | None = None,
        effort: str | None = None,
        validate: Callable[[dict[str, Any]], object] | None = None,
    ) -> dict[str, Any]:
        """Invoke the agent and parse the node's declared outputs."""
        max_output_retries = self.resilience.max_output_retries
        for attempt in range(max_output_retries + 1):
            result_text = self.turn(
                prompt, node.id, session_id_path, model=model, timeout=timeout,
                prompt_path=prompt_path,
                budget_scale=budget_scale, base_timeout_s=base_timeout_s,
                cwd=cwd, add_dirs=add_dirs, effort=effort,
                invoke_retries=node.invoke_retries,
            )
            try:
                outputs = extract_outputs(result_text, node)
                if validate is not None:
                    try:
                        validate(outputs)
                    except Exception as invalid:
                        raise OutputParseError(
                            f"Node '{node.id}': outputs parsed but did not validate "
                            f"against the node's result model: {invalid}"
                        ) from invalid
                return outputs
            except OutputParseError as exc:
                if attempt >= max_output_retries:
                    raise
                print(
                    f"[{node.id}] ⚠ output parse failed "
                    f"(attempt {attempt + 1}/{max_output_retries + 1}): {exc}; retrying",
                    flush=True,
                )
                prompt = retry_prompt(node, exc)

        raise AssertionError("the _invoke_and_parse retry loop exited without a result")

    def turn(
        self,
        prompt: str,
        node_id: str,
        session_id_path: Path | None,
        model: str | None = None,
        *,
        prompt_path: Path | None = None,
        timeout: float,
        budget_scale: float = 1.0,
        base_timeout_s: float | None = None,
        cwd: str | None = None,
        add_dirs: list[str] | None = None,
        effort: str | None = None,
        invoke_retries: int | None = None,
    ) -> str:
        """Run one agent-CLI turn for ``prompt``, recovering from transient failures."""
        resilience = self.resilience
        backend = self.backend
        budget = active_recovery_wait_budget() or RecoveryWaitBudget.from_resilience(resilience)
        max_invoke_retries = (
            resilience.max_invoke_retries if invoke_retries is None else invoke_retries
        )
        short_attempt = 0
        cap_waits = 0
        attempt_prompt = prompt
        while True:
            try:
                print(f"[{node_id}] 🚀 Invoking {backend.name} (model: {model or 'default'})", flush=True)
                otel.turn_start(
                    node_id,
                    model,
                    effort,
                    timeout,
                    backend=backend.name,
                    cwd=cwd,
                    add_dirs=tuple(add_dirs or ()),
                )
                if budget_scale != 1.0:
                    otel.turn_event(
                        "budget_scaled",
                        scale=budget_scale,
                        base_timeout_s=base_timeout_s,
                    )
                with recovery_wait_scope(budget):
                    result = backend.run_turn(
                        attempt_prompt,
                        node_id,
                        session_id_path,
                        model,
                        prompt_path=prompt_path,
                        timeout=timeout,
                        resilience=resilience,
                        cwd=cwd,
                        add_dirs=add_dirs,
                        effort=effort,
                    )
                otel.turn_end()
                return result
            except reload.ReloadRequested:
                otel.turn_end()
                raise
            except BackendInvocationError as exc:
                otel.turn_end(
                    error=str(exc),
                    error_class=type(exc).__name__,
                    error_kind=error_kind(exc),
                )
                print(f"[{node_id}] ⚠ {backend.name} invocation failed: {exc}", flush=True)
                if not exc.transient:
                    raise
                is_cap_hit = exc.reset_at is not None or is_cap(str(exc))
                if exc.timed_out and not is_cap_hit:
                    print(
                        f"[{node_id}] ⏱ previous attempt exceeded its ~{int(timeout)}s "
                        f"budget; warning the retry to size its work to fit",
                        flush=True,
                    )
                    attempt_prompt = timeout_retry_prompt(prompt, timeout)
                else:
                    attempt_prompt = prompt
                if is_cap_hit:
                    if cap_waits >= resilience.max_cap_waits:
                        raise
                    cap_waits += 1
                    delay, when = cap_delay_seconds(
                        exc, resilience=resilience, clock=self.clock
                    )
                    probing = 0 < resilience.cap_probe_s < delay
                    sleep_s = resilience.cap_probe_s if probing else delay
                    if probing:
                        print(
                            f"[{node_id}] ⏸ spending/usage cap reached — sleeping "
                            f"~{int(sleep_s)}s, then re-attempting in case the cap has "
                            f"cleared early. The window is scheduled to reopen around "
                            f"{when}. ({str(exc).strip()})",
                            flush=True,
                        )
                    else:
                        print(
                            f"[{node_id}] ⏸ spending/usage cap reached — pausing ~{int(sleep_s)}s "
                            f"(resuming around {when}). The cap clears only when the window "
                            f"resets, so the run sleeps through it. ({str(exc).strip()})",
                            flush=True,
                        )
                    otel.turn_event(
                        "cap_wait",
                        node=node_id,
                        delay_s=int(sleep_s),
                        resume_around=when,
                        probing=probing,
                    )
                    budget.consume("cap", sleep_s)
                    with otel.wait("cap", node_id):
                        interrupted = sleep_with_notice(
                            sleep_s,
                            node_id,
                            "cap probe" if probing else "cap reset",
                            resilience=resilience,
                            clock=self.clock,
                            channel=control.armed(),
                            honour=reload.cut_by,
                        )
                    self._reenter_on(interrupted, node_id, "a cap wait")
                    print(
                        f"[{node_id}] ▶ cap probe interval elapsed — re-attempting "
                        f"(cap wait {cap_waits}/{resilience.max_cap_waits})"
                        if probing
                        else f"[{node_id}] ▶ cap wait elapsed — resuming node",
                        flush=True,
                    )
                    continue
                if short_attempt >= max_invoke_retries:
                    raise
                delay = min(
                    resilience.invoke_backoff_base_s * (2 ** short_attempt),
                    resilience.invoke_backoff_cap_s,
                )
                short_attempt += 1
                print(
                    f"[{node_id}] ⚠ transient {backend.name} CLI failure "
                    f"(attempt {short_attempt}/{max_invoke_retries}): {exc}; "
                    f"retrying in {int(delay)}s",
                    flush=True,
                )
                otel.turn_event(
                    "retry", node=node_id, attempt=short_attempt, delay_s=int(delay)
                )
                budget.consume("retry", delay)
                with otel.wait("retry", node_id):
                    interrupted = sleep_with_notice(
                        delay,
                        node_id,
                        "transient failure",
                        resilience=resilience,
                        clock=self.clock,
                        channel=control.armed(),
                        honour=reload.cut_by,
                    )
                self._reenter_on(interrupted, node_id, "a retry backoff")
