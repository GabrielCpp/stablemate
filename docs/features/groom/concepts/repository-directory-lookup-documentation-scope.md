---
type: concept
slug: repository-directory-lookup-documentation-scope
title: Repository-directory lookup documentation scope
---
# Repository-directory lookup documentation scope

`find_repo_dir` has one implementation in `groom/groom/docker_io.py::find_repo_dir`: it calls
`list_repo_dirs(volume)` and returns the first sorted directory, or an empty string when the list
is empty. The Groom Docker I/O module records that public helper in the module-wide API context;
the workspace-volume repository-directory reader records the same method in its repository
discovery context.

Neither documentation context is preferred or deprecated. Use the module entry when navigating
the Docker I/O API as a whole, and the repository-directory reader when reasoning about checkout
discovery, repository-menu data, or the single-repository fallback. Both refer to the same call
and must remain consistent with its one implementation.

- code: groom/groom/docker_io.py::find_repo_dir
- rule: select the documentation context by the question being answered; `find_repo_dir` itself has one current implementation and no ranking between the module-wide and repository-discovery views
