---
type: concept
slug: repository-directory-listing-documentation-scope
title: Repository-directory listing documentation scope
---
# Repository-directory listing documentation scope

`list_repo_dirs` is documented from two complementary contexts. The Docker I/O module records
the callable as one of the module's Docker subprocess wrappers. The workspace-volume
repository-directory reader records the same callable as checkout discovery for repository menus
and unspecified-repository diff requests.

Both views are current. `list_repo_dirs` itself discovers every `.git` directory one or two
levels below `/vol`, converts accepted paths to volume-relative checkout directories, and sorts
the result; it does not distinguish a preferred documentation entry point. Use the module view
when navigating the Docker I/O API and the reader view when understanding repository discovery's
role in the workspace-volume flow.

- code: groom/groom/docker_io.py::list_repo_dirs
- rule: use the Docker I/O module view for the callable's module API and the workspace-volume reader view for its repository-discovery context; neither view is preferred.
- tests: groom/tests/test_docker_io.py::test_find_repo_dir_extracts_parent_of_dot_git,
  groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_when_none_found,
  groom/tests/test_docker_io.py::test_find_repo_dir_returns_empty_on_docker_failure
- detail: [Repository-directory listing documentation scope](repository-directory-listing-documentation-scope.md)
