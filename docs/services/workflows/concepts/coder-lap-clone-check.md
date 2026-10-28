---
type: concept
slug: coder-lap-clone-check
title: Coder lap clone check
---
# Coder lap clone check

The lap's clone check refuses a story that adds a copy of code its repository already has. It
runs the code-structure skill's clone script in range mode on each code repository the story
dispatches into, measured from the story's base, and turns each copy into a finding the review
phase repairs. The repair extracts the repeated code to one owner both callers use, in the same
story. When the two copies sit in separately built services, the finding names both builds and
the repair is a library the repository's workspace lists, as code-structure rule 2.13 says. Two
copies that change for different reasons stay, through a coincidence entry the
repository tracks in `.agent-checks.toml`. The check runs in the
[coder development flow](../flows/coder-dev.md) after the story status check and before any
service gate.

- code: `workflows/src/workhorse_workflows/coder/shared/clones.py::__all__` @b6d534e7b30f
- rule: a copy the story added is a failure of the lap, never a follow-up, because a second copy left for later drifts from the first before anyone extracts it
- rule: a check that cannot run stops the run instead of filing a finding, because no repair by the story's owner brings back a missing detector
- rule: the check runs the script the highest-precedence library layer carries, so a layer that overrides the code-structure skill overrides the check with it
- rule: a copy in another build asks for a library instead of a module, because a module inside one service is not an owner the other service's build can reach
- prefers: the story's base over the last commit as the range, because a copy the build turn committed must still reach the review turn
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_copy_the_story_added_comes_back_as_a_copies_failure_before_any_service_gate`
- tests: `workflows/tests/coder/dev/test_flow.py::test_the_clone_check_is_not_consulted_when_the_story_status_check_fails`
- tests: `workflows/tests/coder/dev/test_flow.py::test_the_clone_check_receives_the_dispatch_repos_and_the_story_identity`
- detail: [coder development flow](../flows/coder-dev.md)
- detail: [coder review shared nodes](coder-review-shared-review.md)

## Methods

### check_copies

- sig: `check_copies(logger, roots, story_slug="", story_id="", library_dirs=()) -> CopyCheck`
- does: runs the script once per git repository, however many of the roots sit inside it
- verify: count(subject="clone script runs per repository", equals=1)
- does: passes the repository's story base to the script as `--base`
- verify: count(subject="clone script runs from the story base", equals=1)
- does: sets `STABLEMATE_CACHE_DIR` to the shared cache for the script, so the detector the commit hook fetched is reused
- verify: count(subject="clone script runs with the shared cache", equals=1)
- does: turns each pair into a finding whose target is the added range
- verify: json_path(path="$.findings[0].target", matches="^api-service/.+:[0-9]+-[0-9]+$")
- does: names the existing range, both enclosing functions and the line count in that finding's issue
- verify: json_path(path="$.findings[0].issue", matches="^this story added a copy of .+:[0-9]+-[0-9]+")
- does: names both builds in the issue and code-structure rule 2.13 in the repair when the two ranges sit under different nearest build manifests
- verify: json_path(path="$.findings[0].repair", matches="code-structure rule 2\\.13")
- does: turns each problem with a coincidence entry into a finding on `.agent-checks.toml`
- verify: json_path(path="$.findings[0].target", matches="/\\.agent-checks\\.toml$")
- raises: `WorkflowFailed` when no library layer carries the clone script, naming the layers it searched
- verify: json_path(path="$.error", matches="check_clones\\.py.*searched")
- raises: `WorkflowFailed` with the script's stderr when the script exits with neither 0 nor 1, or prints no report
- verify: json_path(path="$.error", matches="^the clone check could not run in ")
- raises: `WorkflowFailed` when the script outlives its timeout
- verify: json_path(path="$.error", matches="^the clone check did not finish in ")
- raises: `WorkflowFailed` when the repository has no story base
- verify: json_path(path="$.error", matches="^the clone check found no story base in ")
- returns: a `CopyCheck` carrying the findings of the first repository that has any, with that repository as its `cwd`
- verify: json_path(path="$.cwd", matches="api-service$")
- returns: an empty `CopyCheck` when every repository is clean
- verify: json_path(path="$.findings", equals="[]")
- code: `workflows/src/workhorse_workflows/coder/shared/clones.py::check_copies` @b6d534e7b30f
- tests: `workflows/tests/coder/shared/test_clones.py::test_a_pair_becomes_a_finding_naming_the_copy_the_original_and_both_units`
- tests: `workflows/tests/coder/shared/test_clones.py::test_a_pair_across_two_builds_names_both_and_asks_for_a_library`
- tests: `workflows/tests/coder/shared/test_clones.py::test_a_pair_in_one_build_keeps_the_single_owner_repair`
- tests: `workflows/tests/coder/shared/test_clones.py::test_a_pair_without_units_names_only_the_ranges`
- tests: `workflows/tests/coder/shared/test_clones.py::test_a_config_problem_becomes_a_finding_on_the_check_config`
- tests: `workflows/tests/coder/shared/test_clones.py::test_a_clean_run_returns_no_finding`
- tests: `workflows/tests/coder/shared/test_clones.py::test_a_script_that_exits_two_stops_the_run_with_its_stderr`
- tests: `workflows/tests/coder/shared/test_clones.py::test_output_that_is_not_the_report_stops_the_run`
- tests: `workflows/tests/coder/shared/test_clones.py::test_a_script_that_outlives_the_timeout_stops_the_run`
- tests: `workflows/tests/coder/shared/test_clones.py::test_a_repository_with_no_story_base_stops_the_run`
- tests: `workflows/tests/coder/shared/test_clones.py::test_a_missing_script_stops_the_run_naming_the_layers_searched`
- tests: `workflows/tests/coder/shared/test_clones.py::test_two_roots_in_one_repository_run_the_check_once`
- tests: `workflows/tests/coder/shared/test_clones.py::test_the_script_gets_the_repo_the_base_and_the_cache_directory`
- tests: `workflows/tests/coder/shared/test_clones.py::test_the_cache_directory_defaults_to_the_shared_cache`

### check_script

- sig: `check_script(library_dirs: tuple[str, ...]) -> Path | None`
- does: looks for `library/skills/**/code-structure/scripts/check_clones.py` in each library layer, highest precedence first
- verify: json_path(path="$", matches="^.*/base/library/skills/.+/check_clones\\.py$")
- returns: `None` when no layer carries the script
- verify: json_path(path="$", equals="null")
- code: `workflows/src/workhorse_workflows/coder/shared/clones.py::check_script` @b6d534e7b30f
- tests: `workflows/tests/coder/shared/test_clones.py::test_the_first_layer_with_the_script_wins`

### story_base

- sig: `story_base(root: Path, refs: tuple[str, ...]) -> str`
- does: on a branch, returns the merge base with trunk
- verify: count(subject="story bases taken from the merge base with trunk", equals=1)
- does: on trunk, returns the parent of the earliest commit whose `Story` trailer names one of `refs`
- verify: count(subject="story bases taken from the parent of the earliest story commit", equals=1)
- returns: the commit `HEAD` names, on trunk before the story's first commit
- verify: json_path(path="$", matches="^[0-9a-f]{40}$")
- code: `workflows/src/workhorse_workflows/coder/shared/okf.py::story_base` @3794756de838
- tests: `workflows/tests/coder/shared/test_clones.py::test_on_trunk_the_story_base_is_the_parent_of_the_earliest_story_commit`
- tests: `workflows/tests/coder/shared/test_clones.py::test_on_trunk_a_story_with_no_commit_yet_measures_from_head`
- tests: `workflows/tests/coder/shared/test_clones.py::test_on_a_branch_the_story_base_is_the_merge_base_with_trunk`
