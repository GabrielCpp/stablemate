"""Render one node and drive retry → cap-wait → compact → reframe → stop."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from workhorse._vendor.stablemate_core.config import resolve_backend_default, resolve_power
from workhorse import otel, reload
from workhorse.config_run import AgentResilience, RunConfig
from workhorse.context import WorkflowContext
from workhorse.runner.caps import cap_delay_seconds, sleep_with_notice
from workhorse.runner.clock import SYSTEM_CLOCK, Clock
from workhorse.runner.extract import extract_outputs
from workhorse.runner.failure import (
    BackendInvocationError,
    OutputParseError,
    error_kind,
    is_cap,
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
    prompt_path.write_text(prompt, encoding="utf-8")
    return prompt_path


def _print_prompt_path(node_id: str, prompt_path: Path) -> None:
    """Echo where the rendered prompt was written, without dumping variables."""
    print(f"[{node_id}] prompt: {prompt_path}", flush=True)


def _resolve_power_settings(
    power: str | None,
    backend_name: str,
    model_override: str | None,
) -> tuple[str | None, str | None]:
    """Resolve a node's abstract ``power`` into concrete backend settings.

    Per field, the power mapping wins when present. Model then falls through to the
    run-level override (``AGENT_MODEL`` / ``AGENT_CLAUDE_MODEL``, resolved once at the
    CLI boundary and handed down), then the config's ``[default.<backend>]`` table;
    effort falls through to that table directly (it has no override). Anything still
    unset stays None so the harness default applies.
    """
    mapped = resolve_power(power, backend_name)
    fallback = resolve_backend_default(backend_name)
    model = mapped.model or model_override or fallback.model
    return model, mapped.effort or fallback.effort


@dataclass(frozen=True)
class AgentRunner:
    """The fail-soft recovery ladder, for one run.

    Every field is a collaborator or a policy the whole run shares — the backend to
    drive, the knobs to drive it with, the clock to wait on, and the two console/model
    settings the CLI boundary resolved from the environment. What varies per node (the
    node itself, its context, where its prompt renders from) is a parameter of
    :meth:`run`, so no caller has to forward the run's context field by field.
    """

    backend: AgentBackend
    resilience: AgentResilience = field(default_factory=AgentResilience)
    #: How the ladder waits and what it calls "now". Injected, so a run that sleeps
    #: through an eight-day cap window is a test that costs microseconds.
    clock: Clock = SYSTEM_CLOCK
    #: Echo each node's rendered-prompt path to the console (WORKHORSE_PRINT_PROMPT).
    print_prompt: bool = True
    #: Run-level model override, already resolved from the environment.
    model_override: str | None = None

    @classmethod
    def from_config(cls, config: RunConfig, *, clock: Clock = SYSTEM_CLOCK) -> AgentRunner:
        """The ladder this run's configuration describes.

        The one construction point: the environment was read once into ``RunConfig``
        at the CLI boundary, and this turns that value into the service the engine
        calls. Nothing below here reads configuration of its own.
        """
        return cls(
            backend=config.backend,
            resilience=config.resilience,
            clock=clock,
            print_prompt=config.print_prompt,
            model_override=config.model_override,
        )

    def run(
        self,
        node: AgentNode,
        context: WorkflowContext,
        workflow_dir: Path,
        session_id_path: Path | None = None,
        *,
        resume_session: bool = False,
        run_dir: Path | None = None,
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
                run_dir=run_dir,
            )

    def _run(
        self,
        node: AgentNode,
        context: WorkflowContext,
        workflow_dir: Path,
        session_id_path: Path | None = None,
        *,
        resume_session: bool = False,
        run_dir: Path | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Render the prompt, invoke the agent, and parse its declared outputs — resiliently.

        This worker is built to run unattended for days, so a recoverable failure must
        never crash the whole run. Recovery escalates through three layers:

        1. **Transient retries** (inside :meth:`turn`): rate limits, overloads,
           network blips, timeouts, *empty* results and spending caps are retried or
           waited out with backoff. That budget is measured in days, not minutes —
           an outage the run can sleep through is not a failure.
        2. **Compact & continue** (here): if the node exhausts the model's context
           window (the headless CLI returns instead of auto-compacting), the session
           is compacted and the node retried on it — preserving the node's progress —
           up to ``resilience.max_compact_attempts`` times before reframing.
        3. **Reframe** (here): if invocation or output parsing still fails, the prompt
           is rephrased from scratch in a fresh session and the node is retried, up to
           ``resilience.max_rephrase_attempts`` times. A node the agent can't answer
           as-phrased often succeeds when re-asked more simply.
        When all three are spent the node **raises**, ending the run at a resumable
        checkpoint for an operator to look at. There is deliberately no fourth layer
        that invents the node's outputs: a null verdict from a review node, or a null
        plan from a dev node, is not a degraded answer but a fabricated one, and every
        node downstream then does real work on it. A run that stops is recoverable by
        resuming it; a run that continues on fabricated outputs is not recoverable at
        all, because nothing downstream records that the answer was never given.

        **Sessions.** Each node is a fresh prompt and starts from a *clean context* —
        we do NOT chain one node's conversation into the next. The persisted agent
        session is resumed only when ``resume_session`` is True, which the controller
        sets solely to continue *this same node* after an interruption (a crash mid
        node). A normal forward move to a new node always starts clean. (The
        compact-and-continue layer above also resumes the session, but only within
        this same call, to recover the node it is already running.)

        **The backend is injected, never resolved here.** ``AGENT_CLI`` is read once at
        the CLI boundary and the chosen adapter is handed down, so the ladder names no
        CLI and imports none — the reason the ladder and ``backends`` no longer have to
        import each other lazily.

        Returns (rendered_prompt, extracted_outputs_dict).
        """
        node_id = node.id
        resilience = self.resilience
        ctx = context.as_dict()

        # The wall-clock budget for this node's turn: the node's own timeout when set,
        # else the engine default. Surfaced to the prompt (node_timeout_s/min) so the
        # agent can size its commands to finish — a turn killed at the budget restarts
        # the node from scratch with no memory, wasting the whole budget.
        effective_timeout = node.timeout if node.timeout else resilience.result_timeout_s
        # An unbounded budget (timeout: infinity) means "never kill this turn". The stream
        # loops compare `elapsed > timeout`, so float('inf') naturally never trips; only the
        # prompt-surfaced ints need a non-numeric stand-in (int(inf) would overflow).
        unbounded = effective_timeout == float("inf")

        # Render per-node CWD first so it can be forwarded into the prompt context.
        # _flavor_override uses _node_cwd to look up flavors relative to the per-node
        # repo root (e.g. web-app) rather than the global _repo_root (the orchestrating
        # repo), enabling each workspace repo to provide its own flavor independently.
        rendered_cwd = render_string(node.cwd, ctx).strip() if node.cwd else None

        # Render node args as Jinja2 strings, merge into context for prompt rendering
        rendered_args = {k: render_string(v, ctx) for k, v in node.args.items()}
        prompt_ctx = {
            **ctx,
            **rendered_args,
            "node_timeout_s": "unbounded" if unbounded else int(effective_timeout),
            "node_timeout_min": "unbounded" if unbounded else int(round(effective_timeout / 60)),
            "_node_cwd": rendered_cwd or "",
        }
        rendered_prompt = render(node.prompt, prompt_ctx, workflow_dir)

        # Persist the full rendered prompt before launching the agent so even failed or
        # interrupted nodes are inspectable. Console output stays compact: only the path.
        prompt_path = _write_prompt_for_inspection(node_id, rendered_prompt, run_dir)
        if prompt_path is not None and self.print_prompt:
            _print_prompt_path(node_id, prompt_path)

        # Render additional directories and the rest of the per-node dispatch config.
        if isinstance(node.add_dirs, str):
            # Template string that resolves to a context list (e.g. "{{ affected_repo_paths }}").
            # Jinja2 renders a list variable as its string repr, so look up the native context
            # value directly when the template is a bare variable reference.
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

        # The backend already sets cwd as the agent's working directory — passing it
        # again via --add-dir is redundant and clutters the CLI invocation.
        if rendered_cwd and rendered_add_dirs:
            cwd_resolved = Path(rendered_cwd).resolve()
            rendered_add_dirs = [d for d in rendered_add_dirs if Path(d).resolve() != cwd_resolved]

        # The node's abstract power tier maps through user config to concrete
        # model/effort for the active backend. Missing config falls back to the run's
        # override then the backend's defaults, preserving harness behavior.
        model, node_effort = _resolve_power_settings(
            node.power, self.backend.name, self.model_override
        )
        model = model or self.backend.default_model

        # New node = clean context: drop any session left by a previous node so this
        # node's first attempt does not --resume someone else's conversation. When
        # resume_session is set we keep it, so the interrupted node continues where it
        # left off (the controller only asks for this on the re-entered node).
        if not resume_session and session_id_path and session_id_path.exists():
            session_id_path.unlink()

        # ``rephrase`` advances only on a genuine reframe; a context-compaction retry
        # re-runs the SAME prompt on the compacted session without consuming a reframe.
        rephrase = 0
        compact_attempts = resilience.max_compact_attempts
        while True:
            prompt = (
                rendered_prompt
                if rephrase == 0
                else rephrase_prompt(rendered_prompt, node, rephrase)
            )
            # A reframed attempt starts a FRESH session so the prior, unhelpful
            # exchange doesn't bias the model toward repeating its mistake.
            if rephrase > 0:
                if session_id_path and session_id_path.exists():
                    session_id_path.unlink()
                print(
                    f"[{node_id}] 🔄 reframing prompt "
                    f"(attempt {rephrase}/{resilience.max_rephrase_attempts})",
                    flush=True,
                )
            try:
                outputs = self._invoke_and_parse(
                    prompt, node, session_id_path, model,
                    timeout=effective_timeout,
                    cwd=rendered_cwd, add_dirs=rendered_add_dirs,
                    effort=node_effort,
                )
                return rendered_prompt, outputs
            except (BackendInvocationError, OutputParseError) as exc:
                # Layer 2: context window exhausted → compact this session and retry the
                # SAME prompt on it, keeping the node's progress. Only when compaction
                # is unavailable/ineffective do we fall through to a (lossy) reframe.
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
                        continue  # retry same prompt on the compacted session
                    print(
                        f"[{node_id}] ⚠ compaction unavailable/ineffective; "
                        f"falling back to reframe",
                        flush=True,
                    )

                # Non-recoverable backend/CLI failure (non-transient, non-overflow):
                # the agent CLI crashed or its server returned a hard error (e.g.
                # "Unexpected server error"). Reframing the prompt can't bring back a
                # dead CLI, and fabricating default outputs would corrupt the workflow
                # (e.g. an empty write_epic), so stop the ladder and surface it for a
                # clean abort. Transient-exhausted and overflow failures fall through to
                # the reframe/default layers below, unchanged.
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

                # Layer 3: reframe in a fresh session.
                if rephrase < resilience.max_rephrase_attempts:
                    print(
                        f"[{node_id}] ⚠ node failed ({exc}); will reframe and retry",
                        flush=True,
                    )
                    otel.turn_event("reframe", node=node_id, attempt=rephrase + 1)
                    # Brief, escalating pause so a reframe doesn't hammer a struggling
                    # service back-to-back.
                    delay = min(10 * (rephrase + 1), 60)
                    budget = active_recovery_wait_budget()
                    if budget is not None:
                        budget.consume("reframe", delay)
                    with otel.wait("reframe", node_id):
                        self.clock.sleep(delay)
                    rephrase += 1
                    continue

                # Nothing left to try. Stop here rather than inventing this node's
                # answer — the run dir holds the checkpoint, so an operator resumes it.
                print(
                    f"[{node_id}] ✖ all {resilience.max_rephrase_attempts} reframings "
                    f"failed ({exc}); stopping the run — resume it once the cause is "
                    f"cleared",
                    flush=True,
                )
                # The class and bucket ride the event as well as the turn span: an
                # OutputParseError is raised after the turn span has already closed
                # cleanly (the CLI answered; the answer would not parse), so this is
                # the only place that failure mode is nameable.
                otel.turn_event(
                    "exhausted",
                    error=True,
                    node=node_id,
                    error_class=type(exc).__name__,
                    error_kind=error_kind(exc),
                )
                raise

    def _invoke_and_parse(
        self,
        prompt: str,
        node: AgentNode,
        session_id_path: Path | None,
        model: str | None,
        *,
        timeout: float,
        cwd: str | None = None,
        add_dirs: list[str] | None = None,
        effort: str | None = None,
    ) -> dict[str, Any]:
        """Invoke the agent and parse the node's declared outputs.

        When the response can't be parsed into the declared outputs, re-prompt within
        the SAME session up to ``resilience.max_output_retries`` times with a corrective
        message
        before giving up (raising ``OutputParseError`` for the caller's reframe layer).
        """
        max_output_retries = self.resilience.max_output_retries
        for attempt in range(max_output_retries + 1):
            result_text = self.turn(
                prompt, node.id, session_id_path, model=model, timeout=timeout,
                cwd=cwd, add_dirs=add_dirs, effort=effort,
            )
            try:
                return extract_outputs(result_text, node)
            except OutputParseError as exc:
                if attempt >= max_output_retries:
                    raise
                print(
                    f"[{node.id}] ⚠ output parse failed "
                    f"(attempt {attempt + 1}/{max_output_retries + 1}): {exc}; retrying",
                    flush=True,
                )
                # Resume the same session (session id was just persisted) and nudge the
                # agent to emit only the required JSON.
                prompt = retry_prompt(node, exc)

        # Unreachable: the loop either returns outputs or raises on the final attempt.
        raise AssertionError("the _invoke_and_parse retry loop exited without a result")

    def turn(
        self,
        prompt: str,
        node_id: str,
        session_id_path: Path | None,
        model: str | None = None,
        *,
        timeout: float,
        cwd: str | None = None,
        add_dirs: list[str] | None = None,
        effort: str | None = None,
    ) -> str:
        """Run one agent-CLI turn for ``prompt``, recovering from transient failures.

        Two recovery modes:
        - **Spending/usage cap** — a *scheduled* failure that clears only when the
          subscription window resets. We sleep until that reset (parsed from the
          message, else a default), announcing it on the console, then retry. This is
          NOT bounded by the short-retry budget: a cap always recovers eventually, so
          the run rides it out instead of dying.
        - **Short transient** (rate limit, overload, network) — bounded exponential
          backoff, then fail fast.

        Persists the resulting session id (when available) so a subsequent call
        resumes the same conversation.

        ``self.backend`` is the injected port: this drives ``run_turn`` and knows
        nothing else about which CLI is behind it.
        """
        resilience = self.resilience
        backend = self.backend
        budget = active_recovery_wait_budget() or RecoveryWaitBudget.from_resilience(resilience)
        max_invoke_retries = resilience.max_invoke_retries
        short_attempt = 0
        cap_waits = 0
        # The prompt sent on the current attempt. After a budget timeout we prepend a
        # warning (see below) so the retry knows it overran and how long it has.
        attempt_prompt = prompt
        while True:
            try:
                print(f"[{node_id}] 🚀 Invoking {backend.name} (model: {model or 'default'})", flush=True)
                # One agent-turn span per CLI invocation; the result event's
                # duration/usage attach via otel.turn_result, from inside the adapter.
                otel.turn_start(node_id, model, effort, timeout, backend=backend.name)
                with recovery_wait_scope(budget):
                    result = backend.run_turn(
                        attempt_prompt,
                        node_id,
                        session_id_path,
                        model,
                        timeout=timeout,
                        resilience=resilience,
                        cwd=cwd,
                        add_dirs=add_dirs,
                        effort=effort,
                    )
                otel.turn_end()
                return result
            except reload.ReloadRequested:
                # The one exit from this loop that consumes nothing: no short retry, no
                # cap wait, no backoff, and no budget. The operator cut the turn; the
                # turn did not fail, so a counter incremented here would spend part of
                # the recovery the *next* genuine failure is entitled to.
                #
                # It still has to close the span — and close it *cleanly*. The turn
                # accrued real tokens, cost and wall clock before the cut, and the
                # `reload_kill` event the stream loop already recorded is on this span;
                # ending it with an ERROR status would make groom count a deliberate
                # reload among the failures. Not closing it at all is the unclosed span
                # this whole feature exists to avoid.
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
                # A budget timeout: warn the next attempt that it overran and give it the
                # wall-clock budget so it can size its work to fit. Other transients
                # (rate limit, overload, network) retry the prompt unchanged.
                # Cap-triggered early aborts also carry timed_out=True (the stream loop
                # breaks the same way) but must NOT get the budget warning — the model
                # never actually ran; the cap cleared externally.
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
                    print(
                        f"[{node_id}] ⏸ spending/usage cap reached — pausing ~{int(delay)}s "
                        f"(resuming around {when}). The cap clears only when the window "
                        f"resets, so the run sleeps through it. ({str(exc).strip()})",
                        flush=True,
                    )
                    otel.turn_event(
                        "cap_wait", node=node_id, delay_s=int(delay), resume_around=when
                    )
                    budget.consume("cap", delay)
                    with otel.wait("cap", node_id):
                        sleep_with_notice(
                            delay, node_id, "cap reset", resilience=resilience, clock=self.clock
                        )
                    print(f"[{node_id}] ▶ cap wait elapsed — resuming node", flush=True)
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
                # Ticked, not silent: once the backoff reaches its cap a single sleep
                # is half an hour, which to a collector is indistinguishable from a
                # wedged turn. The same notice loop the cap wait uses proves liveness.
                budget.consume("retry", delay)
                with otel.wait("retry", node_id):
                    sleep_with_notice(
                        delay,
                        node_id,
                        "transient failure",
                        resilience=resilience,
                        clock=self.clock,
                    )
