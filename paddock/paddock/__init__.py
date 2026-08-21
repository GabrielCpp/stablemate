"""paddock — one benchmark harness.

A **task** unpacks a **seed** (a repo captured as a zip, `.git` included), runs **steps**
(real CLI invocations under a task-chosen stablemate config), stages the **result** (the
mutated repo plus each step's artifacts), and optionally **scores** it with a ruler the
task brought itself. The harness never judges; it runs, stages, and measures only when
told how.

A task module imports the two declaration helpers from here:

```python
from paddock import Score, step, task

task(name="policy-desk-qa", seed="policy-desk", config="configs/opencode.toml")

@step()
def run_qa(run):
    run.cli("workhorse-coder", "run", "qa", "--config", str(run.config), check=True)

def score(run) -> Score:
    ...
```
"""

from __future__ import annotations

from paddock.registry import Score, Step, Task, TaskError, step, task
from paddock.runner import CommandResult, Run, RunError

__all__ = [
    "CommandResult",
    "Run",
    "RunError",
    "Score",
    "Step",
    "Task",
    "TaskError",
    "step",
    "task",
]
