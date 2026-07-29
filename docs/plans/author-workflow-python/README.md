# `author`, rewritten as Python

`workflow.py` here is the `author` workflow expressed in the shape proposed by
[../workflow-as-python-state-machine.md](../workflow-as-python-state-machine.md).
It is a **design artifact**: nothing imports it, nothing runs it, and nothing
under `workhorse/` or `base-library/workflows/` was changed to produce it. The
`workhorse.pyflow` import at the top does not exist — that import *is* the
proposal.

**Gathering everything into one file is a convenience of the artifact, not the
proposed shape.** A real workflow is a package: a `workflow.py` holding the state
machine and nothing else, beside `nodes/`, `flows/` and `models.py`. This file is
the argument for that split — it is 1,459 lines, and `class Author` does not
start until line 900, so two thirds of it is node bodies a reader of the state
machine never needs. See "One workflow, several files" in the plan.

It exists because the design should be judged against the hardest thing we
actually run, not a sketch. `base-library/workflows/author/` is the largest
workflow in the tree: 2,389 lines of YAML over 159 nodes, plus 23 sibling
scripts totalling 2,650 lines.

## The three layers

```python
@blueprint.node
def select_story(logger, cfg, epic) -> StoryChoice: ...      # a node library

class Author(Workflow):                                      # the state machine
    mode: Mode = "epic"                                      #   an input, fixed at launch

    def setup(self) -> RunContext: ...                       #   resolved once, then frozen

    def next_story(self, epic):                              #   a method is a state
        choice = self.call(select_story, cfg=self.ctx, epic=epic)
        return Continue(choice, self.write_story,             #   the transition...
                        epic=epic, story=choice.story_slug)  #   ...carries the state

workflow = Workflow()
workflow.add_blueprints(scriptutil.blueprint, blueprint)     # plural: the shared one too
workflow.add_flows(Surveyor, ParitySurveyor)                 #   so the CLI can name them
main = workflow.main(Author)                                 #   the console-script callable
```

| Layer | Is | Why it is separate |
| --- | --- | --- |
| **Blueprint** | free functions, `logger` first | The reusable layer. Same contract `scripts/*.py` already has via `main(logger)`, so today's scripts port as-is — and a workflow picks up `scriptutil`'s nodes rather than re-implementing `await_operator` for the fourth time. |
| **`Workflow` subclass** | methods as states, parameters as state | The class holds no mutable state. A state reads what it was handed and hands the next one what it needs, so the checkpoint is `(method, params)` — see below. |
| **`self.call` / `.agent` / `.handoff`** | the seams | Calling a node directly would work and be invisible. Going through `self.call` is what makes it a node: its own span, its own recorded `output.json` — which is what a later state's `self.output(...)` reads back — and a no-op that merely records itself under `--dry-run`, which is what lets `dot` render without executing. |

## Where state lives

Three tiers, and the rule is mechanical: **if a state writes it, it is a
parameter of the next state.**

| tier | written by | lifetime | checkpointed |
| --- | --- | --- | --- |
| inputs (class fields) | the operator | the whole run | once, at launch |
| `self.ctx` (`RunContext`, frozen) | `setup()`, once | the whole run | once, after setup |
| state parameters | the state before it | one hop | every transition |

So a checkpoint is a line of JSON you can read, and hand-edit:

```json
{"state": "write_story", "params": {"epic": "auth", "story": "login-form", "resolves": 1}}
```

That is not just a smaller checkpoint — it is what makes finding #2 below
*unwriteable*. `close()` has no `epic` in scope and never will, so the commit
message cannot render an ambient one. A dependency that survives nine states
has to be threaded through nine signatures, and being annoying to write is the
point: it prices the coupling instead of hiding it.

Two consequences worth reading the file for:

- **Derived values are derived, not carried.** `epic_dir`, `story_dir`,
  `story_path` and the `*-context.md` paths were fields on the previous draft
  of `Author`, and were also returned by three node result models. Every one is
  a pure function of `(ctx, epic, story)`, so they are four module functions
  and nothing passes them anywhere.
- **Loop budgets become legible, and get billed.** `cov_reworks` and `resolves`
  are ordinary parameters, so "this run is on coverage rework 2 of 3" is
  visible in the checkpoint instead of living in a counter node's output. The
  bill: `cov_reworks` must be passed through `write_story` and
  `story_feedback`, which never read it, because the story loop sits inside the
  loop that owns it. Two states of pass-through is the honest price of a
  run-scoped counter; if it were seven, that would be the design telling us the
  loop is wrong.

`setup()` is the residue, and is deliberately narrow: `base_branch` is decided
at the top of the run and used only at the very bottom, and threading it
through seven uninterested states would be worse than the disease. Two strings.
It is not a place to stash progress — states cannot write it.

## What checks the arguments

Every seam takes `**kwargs`, and loose kwargs are how the YAML's untyped `with:`
bag would sneak back in one layer up. `ParamSpec` closes it — the engine side is
four signatures:

```python
def call(self, node: Callable[Concatenate[Logger, P], T],
         *a: P.args, **kw: P.kwargs) -> T: ...        # Concatenate strips the
                                                     # logger; -> T types the result
def agent(self, prompt: str, *, returns: type[T], args: dict) -> T: ...
def handoff(self, wf: Callable[P, W], *a: P.args, **kw: P.kwargs) -> W: ...

class Continue(Generic[P]):
    def __init__(self, result: object, next: Callable[P, Transition], /,
                 *a: P.args, **kw: P.kwargs): ...
```

That gives a checker the state's own parameter list *and* the node's return
type, so `choice.story_slug` is checked as well as the call that produced it.
`agent` is the one seam that keeps an untyped `args` dict, correctly: a prompt
has no signature to check against, and `returns=` supplies what it can.

**The transition target is positional** — `Continue(result, self.write_story,
epic=...)`, not `next=self.write_story` — because `P.kwargs` has to own the
whole keyword namespace. Under the keyword form no state could ever have a
parameter named `next` or `result`, so this is the right shape independent of
the typing.

`ParamSpec` covers author time. Two other moments need their own answer:

| moment | mechanism | catches |
| --- | --- | --- |
| author time | `ParamSpec` | wrong name, missing required param, wrong type |
| transition time | `inspect.signature(next).bind(**kw)` in `Continue.__init__` | dynamically-built transitions, and anyone not running a checker — *before* the checkpoint is written |
| resume time | `pydantic.validate_call`-style coercion against the signature | JSON off disk: `"docs/epics"` back into a `Path`, and a hand-edited checkpoint naming a parameter that does not exist |

The annotations on these states are load-bearing three times over — which is
the argument for spelling them out even where they are all `str`.

## What to read it for

| Question | Where |
| --- | --- |
| What does a fat state look like? | `write_story(epic, story, bullet_id, resolves)` — one story end to end, 6 nodes and 4 agents |
| Why fat? | Fatness is free; *coupling* is what costs, and the parameter list is where it gets paid, visibly. The seam is drawn where losing work to a crash would hurt |
| What happens to the counter nodes? | `write_story` — `range(MAX_REWORKS)` replaces 3 nodes and a script |
| What happens to a counter *reset*? | Nothing. It is a state re-entered with the parameter at its default. See `_unblock`'s docstring |
| Which budget travels and which doesn't? | `write_story`: the rework budget resets on re-entry (a local `for`), the resolve budget must not (a parameter), and `cov_reworks` is neither — it belongs to an outer loop and is only passed through |
| What happens to the operator gates? | `_unblock` — one method for what was 5 nodes repeated 5 times. `attempt` is passed in, because whose budget it is differs per caller |
| What is `handoff` for, given `Continue`? | `start` — `Continue` names a method of *this* class; `handoff` runs another `Workflow` to its own `Done` and returns the result. That is what a `flow:` node was |
| Where does the CLI bind? | The block above `workflow = Workflow()` at the end of the file. `workhorse-author run surveyor --run-id=test123 --params …` — the positional is a flow, and `--params` binds to the *entry class's* model rather than to an untyped context bag, which makes the CLI a fourth front door onto the same validation as transition, resume and handoff |
| What has since been superseded? | `_unblock`'s blocking `await_operator` call. The plan decided the wait is an `Await` transition, and the runtime's wait is a portable poll — the 280 lines of ctypes inotify get deleted, not moved. The comment there says what converting it costs |

## The count

| | YAML | Python |
| --- | --- | --- |
| Nodes / states | 159 | 20 blueprint nodes + 9 states |
| of which pure counter machinery | 39 | 0 |
| Branch nodes | 58 | 0 (`if` / `match`) |
| Budget constants | 9 vars, each duplicated as a literal into a guard condition | 2 module constants |
| Distinct `resolve_*` agent nodes | 5 (one prompt, five `block_stage:` strings) | 1 call, 1 argument |
| Mutable run-scoped state | the run context, written by any node | 0 fields; params + a frozen `RunContext` |

The nine states: `start`, `split_epics`, `next_epic`, `author_epic`,
`next_story`, `write_story`, `story_feedback`, `check_coverage`, `close`.
The two `next_*` states exist only because something re-enters the work
without re-selecting — `check_coverage` returns to `author_epic`,
`story_feedback` returns to `next_story`. Every other seam is a checkpoint
boundary chosen on how much work a crash should cost.

## Three findings, preserved rather than fixed

1. **`mode: story` never commits.** `story_prune -> done` is terminal, so a
   single-story run skips reconcile, integrity, `validate_artifacts`, the
   commit and the PR, leaving its work uncommitted on the author branch. See
   `Author.story_feedback`.
2. **`{{ epic }}` at commit time is ambient.** It resolves to whatever
   `select_epic` last wrote into the run context, many nodes earlier and
   possibly several times over. Under this layout `close()` simply has no
   `epic` — the value never travelled that far — so the message says what the
   state actually knows. The bug is not fixed here so much as made
   unwriteable.
3. **`cov_rework_count` is reset before `split_stories` but read by the
   coverage stage** — the two are one loop wearing two hats. That is why
   `author_epic` is re-entrant and `check_coverage` returns to it, carrying
   the budget back as a parameter.

## Open questions this raised

- **Two things are called `Workflow`**: the base class `Author` extends, and
  the module-level runner singleton. Inside a state, `self.call(...)` and
  `workflow.call(...)` would both work, but only the first is resolvable
  without a forward reference to a global — so the states here use `self`, and
  the singleton only registers and runs.
- **What enforces "no mutable fields"?** Nothing in this file does; `Author`
  simply declares none. A `Workflow` base that froze the instance after
  `setup()` would make the rule real rather than observed, at the cost of
  ruling out any escape hatch — worth deciding before this shape is built.
- **How much can a parameter be?** These are strings, ints and `Path`s, so the
  checkpoint stays hand-editable. Passing a whole `StoryChoice` would be
  convenient and would quietly end that property. Probably a stated convention
  rather than an enforced one.

## Deliberately not gathered in

The two sub-graphs under the YAML's `flows:` — `surveyor` (23 nodes) and
`parity-surveyor` (8 nodes) — are their own state machines with their own
scripts. Under this design each is its own `Workflow` subclass in its own
module, reached by `self.handoff(...)`, and each would get this same treatment.
