# workhorse_workflows

The stablemate workflows as code. Each subpackage is one workflow that workhorse drives, except `kit/`, which they all share.

## Map

- `author/`: the `author` workflow, which turns one approved roadmap into a milestone, epics and stories.
- `coder/`: the `coder` workflow, which implements, documents, reviews and QAs stories from the plan.
- `kit/`: the helpers every workflow's nodes reuse: git, GitHub, workspaces, paths, JSON, external CLIs and QA stacks.
- `loop_runner/`: the `loop-runner` workflow, which hands a plan to one agent turn.
- `okf_book/`: the okf book builder, which enumerates, repairs and exercises a service's book.
- `research/`: the `research` workflow, which drives a program's gate ladder with measurements run outside any agent turn.
