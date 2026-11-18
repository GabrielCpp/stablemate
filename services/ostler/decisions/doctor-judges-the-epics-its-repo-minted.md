story: none
date: 2026-11-18
elements: Doctor

`ostler doctor` judges only the epics its repo minted. One artifacts dir holds the epics of every repo that shares it,
and each repo mints ids under the `repo.id_prefix` its `agents.yml` sets. An epic whose id carries another prefix
belongs to the repo that minted it. Its milestones and declared fixtures live there, so judging it here would report
`epic-without-milestone` and `unknown-story-fixture` for an epic that is sound in its own repo. Doctor leaves such an
epic out of its findings and its epic list.

`ostler doctor --epic <id>` on an epic another repo minted answers one `foreign-epic` warning. The warning names both
prefixes and tells the reader to run the command from the repo that minted the epic.

An epic whose id carries no prefix stays judged, and so does every epic in a repo that sets no prefix.
