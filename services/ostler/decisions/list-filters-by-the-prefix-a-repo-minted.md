story: none
date: 2026-11-23
elements: ListRepoStoryRows, ListUnknownRepoRows

`ostler list --repo` keeps the epics, stories and seeds one repo minted. One artifacts folder holds the epics of every
repo that shares it, so a plain `list` from any repo prints all of them. The id prefix is the only mark of a repo an
epic carries, so the filter compares the prefix of the epic's id. A story or a seed belongs to the repo of its epic.

`--repo` takes this repo's name, read from `repo.name` in its `agents.yml` or the folder name, or an id prefix in any
case. Another repo's name cannot resolve, because only that repo's `agents.yml` maps it to a prefix. A value that
matches neither exits 2 and names the prefixes it knows.

`--repo` on a kind outside the epics exits 2, because milestones, decisions and template kinds already live in the
repo that keeps them.
