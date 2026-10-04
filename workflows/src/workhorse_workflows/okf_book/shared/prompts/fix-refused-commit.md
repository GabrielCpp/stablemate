This repository refused a commit of its OKF book. Fix what the refusal names, so the same
commit passes when it is tried again.

You run from the repository's root. You do not commit: the commit is tried again in code when
your turn ends, with the same message and the same paths.

## The commit

These paths, each relative to the repository's root:

{% for path in paths %}
- `{{ path }}`
{% endfor %}

## What the repository said

```
{{ refusal }}
```

## How to fix it

Read the refusal first. It usually names the hook or the check that refused, the files it
refused on, and often the command that repairs them.

- When it names a command that regenerates or re-renders files, run that command as the
  repository spells it, then run the check it names and read that it passes.
- When it refuses a page of the commit, on its format, a link or a check of the book, correct
  the page. Change what the refusal names and nothing else on it.
- When it refuses a file outside the commit, find why that file is in the state the check
  refuses. Repair it with the repository's own command where it has one. Do not delete, revert
  or overwrite work in the tree that is not yours to judge: a file somebody else is editing
  stays as it is.

Run the check that refused, on its own, before you end the turn. Running it is how you know.

## What you never do

- Never commit, amend, stash, reset, check out, or change a branch. Never stage or unstage a path.
- Never pass `--no-verify`, set a variable that skips a hook, or edit, disable or remove a hook
  or the check it runs. A check that is wrong for this commit is a finding for the operator.
- Never push, deploy, build an image, or run a command against anything outside this machine.

## Your reply

Reply with one JSON object and nothing else:

```json
{"fixed": "re-rendered the agent files with `make agent-install`; `make agent-check` passes"}
```

- `fixed` says in one or two sentences what you changed and the check you ran.
- Leave `fixed` empty when you changed nothing, and say why in `blocked`: what the refusal
  needs that you could not or must not do. An operator reads it.
