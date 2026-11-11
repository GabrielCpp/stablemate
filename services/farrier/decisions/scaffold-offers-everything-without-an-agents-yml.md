story: track50
date: 2026-11-11
elements: Scaffold, enabled, not_enabled

A repository with no agents.yml may apply any scaffold the library defines, and one with an agents.yml may apply
only the scaffolds it lists (farrier/farrier/scaffolds.py:160-167). The model reads that off the watched
agents.yml: no file, or a file that holds "- service-gitignore". The same test decides whether the listing prints
the scaffold or the "No scaffolds available" sentence (farrier/farrier/cli.py:582-583). Aimed at a directory that
does not exist, scaffold finds no agents.yml there and creates the directory with the files in it, so the
"elsewhere" class of the repo argument succeeds.
