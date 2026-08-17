# State topology

Twenty-seven states cover what was eighty YAML nodes. The factor of three is the `decide_*`
nodes disappearing into the `if` at the end of the state that produced the value they branch
on, and the eight `incr_*`/`reset_*`/`init_*` counter nodes becoming keyword arguments.

**Where a state boundary goes:** a state ends where the *expensive or irreversible* thing
begins — each `handoff` to a sub-flow, each agent turn, each of the two operator gates.
Deterministic nodes fold forward into whichever state branches on them. That is why
`prune_epic` sits inside `open_pr` (a straight line) while `dev`, `review`, `document` and
`qa` are four states rather than one: a kill during QA must not re-run the implementation.

## Story Mode
```
start → prepare → dev → review → document → qa → drain… → finalize
      → commit → commit_pr → done
```
`start` cuts the branch itself in story mode, off the current HEAD, recording the base it
came from — the PR at the far end has to target that base, and re-deriving it from the slug
is how the two drifted once.

## Epic Mode
```
start → select_epic → select_story → prepare → dev → review → document → qa
      → drain → fix_plan → fix_dispatch → fix_implement → fix_check → fix_apply
      → fix_recheck → finalize → commit → select_story        (loop within epic)
                                        ↘ [stories exhausted] open_pr
                                          → merge → merge_operator → select_epic
```
`open_pr` pops the epic off the queue before opening the PR — that order is deliberate.
`merge` returns `Continue | Await`: the CI/merge gate is the one place a human is always
allowed to be the next step.

## `prepare` — the convergence state

Both modes pass through `prepare` before `dev`. Its `prepare_story` node is the **single
canonical source** for `story_path`, `spec_dir`, `qa_dir`, `story_slug` and `story_epic`,
returned as one `StoryPaths` model. Never bypass it and never re-derive those paths.

```python
def prepare(self, slug: str = "", epic: str = "", zero_diff: int = 0) -> Continue:
    story = self.call(prepare_story, self.docs_path, slug or self.story, epic or self.epic)
    return Continue(story, self.dev, epic=epic, zero_diff=zero_diff)
```

## The backlog drain is nested as well as standalone

`flows/fix.py` is the standalone drain. States `drain` through `fix_recheck` are the same
seven steps run *inside* a story's run, right after that story goes green. They are not a
`handoff` to `Fix` because the two differ at the far end: the standalone flow documents and
commits each drained item on its own, while the nested copy leaves both to the story's own
`finalize` and `commit`, so one commit covers the story and everything drained behind it.
The duplication is inherited from the YAML and is preserved deliberately.

## Documentation gate topology

The reviewed implementation enters a standalone, hard-gated `docs` flow before QA:

```text
prepare_story -> resolve_documentation_context -> detect_documentation_okf
-> document_story -> build/validate diff-to-OKF context -> verify_story_documentation
-> review_story_documentation -> documentation_done
```

Repositories without an OKF `docs/features/` tree are explicitly not applicable. Once that tree
exists, an unreadable graph, `ostler doctor` error, surface-only production ownership, blocked
authoring, semantic rejection, or exhausted repair budget ends at `documentation_failed`; it may
not proceed to QA or commit. The parent invokes the same flow again after QA/regression/fix-drain
mutations immediately before commit, and before QA-give-up or standalone fix-story commits.
Local monorepos receive deterministic repository-wide code mapping with document roots excluded;
multi-repo/non-Git docs roots
use scoped doctor findings plus the independent semantic reviewer rather than an invalid cross-repo
diff. CI/merge remediation is contract-preserving and must escalate if behavior would change. Run
the phase independently with `workhorse-coder run docs`.

## QA control-plane topology

The primary QA path is fixed:

```text
prepare_story -> clear_qa_evidence -> resolve_qa_context -> detect_qa_okf
-> build_qa_okf_context -> validate_qa_okf_context -> plan_qa
-> validate_qa_plan -> review_qa_plan -> run_qa_plan -> assess_qa_run
-> verify_qa_evidence -> audit_qa -> regression/completion gates
```

`qa_plan.py` is mandatory for command, browser, and mobile surfaces. Node functions call
`okf.qa_context(...)`, `okf.qa_context_validate(...)`, `okf.qa_validate(...)` and
`okf.qa_run(...)` on the `Ostler` facade directly, reading the `QaOutcome` each returns; no QA agent
drives Playwright/Maestro/commands or authors the run log, manifest, or evidence.
`review_qa_plan` independently checks whether the valid plan can reach and observe its
objectives. `assess_qa_run` constructively judges whether each completed run actually did
so and may request bounded plan repair/extension. `audit_qa` sees only an
objective-confirmed, evidence-valid candidate pass, treats plan/evidence as frozen, and
may only let it stand or refute it.

Routing is fail-closed: `invalid` returns to context/planning repair, `blocked` enters
setup/operator handling, `failed` enters defect triage, and only `passed` reaches the
evidence gate and auditor. Never declare a default output of `passed`.

Audit refutations are classified: plan/evidence defects return to planning, while a
product contradiction becomes the normal failed `qa_result` and enters defect triage.
Context grounding, semantic-plan convergence, and product repair use separate bounded
counters. Regression fixes retain one cumulative budget; a pending marker forces fresh
primary QA after a green fix without resetting that budget.

The reviewed implementation's `code:`/`tests:` grounding is hard-gated by the docs flow before
entering QA so impact generation sees current references. Product fixes loop back through
context generation; setup-only fixes may rerun the already validated plan.

