# __WORKFLOW_NAME__

A workhorse workflow. It runs one agent turn, then runs `__CHECK__` in your repo. A non-zero exit sends the agent back with the tail of the check output. Exit 0 ends the run.

## Run it

```bash
uv tool install .
cd path/to/your/repo
workhorse-__WORKFLOW_NAME__ run --dry-run
workhorse-__WORKFLOW_NAME__ run --cli claude
```

The dry run stubs the agent and the check, so it needs no agent CLI. It proves the workflow loads and every state is reachable.

The real run starts an agent that edits your repo and runs commands without asking you first. Run it where that is safe: a throwaway clone, a VM, or a container you set up. Isolating it is your job.

## Parameters

Pass these with `--params '{"max_rounds": 8}'`.

- `check`: the shell command that decides when the work is done. Default: `__CHECK__`.
- `task`: extra instructions for the agent. Empty means "make the check pass".
- `max_rounds`: how many agent turns to allow before the run fails. Default: 5.

## Map

- `src/__PACKAGE__/workflow.py`: the `CheckLoop` states, the `run_check` node and the `workhorse-__WORKFLOW_NAME__` command.
- `src/__PACKAGE__/prompts/fix.md`: the prompt each agent turn gets.
