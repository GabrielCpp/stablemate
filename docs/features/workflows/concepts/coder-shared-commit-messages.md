---
type: concept
slug: coder-shared-commit-messages
title: Coder shared commit messages
---
# Coder shared commit messages

The Coder workflow uses this contract whenever it creates a commit subject or derives a
description from a story document. Subjects use Conventional Commit syntax, scope the affected
package, preserve an optional QA-failure marker, and keep epic/story provenance in git trailers
rather than in the subject. The helpers are shared so story commits, status commits, marker
commits, queue pruning, pull-request titles, and merge commits cannot drift into incompatible
formats.

- code: `workflows/src/workhorse_workflows/coder/shared/commits.py`
- tests: `workflows/tests/coder/test_commits.py`

## Fields

### SUBJECT_LIMIT

- type: `int`
- default: `72`
- required: true
- semantics: maximum preferred subject length used to trim the description while preserving its marker suffix
- code: `workflows/src/workhorse_workflows/coder/shared/commits.py::SUBJECT_LIMIT`

## Methods

### scope

- sig: `scope(name: str) -> str`
- does: trims surrounding whitespace and lowercases the package name
- verify: json_path(path="$.scope", equals="api-service")
- does: replaces every run of characters outside lowercase letters, digits, dot, underscore, and hyphen with a hyphen
- verify: json_path(path="$.scope", equals="api-service")
- does: removes leading and trailing dots and hyphens, returning an empty scope when no valid name remains
- verify: json_path(path="$.scope", absent=true)
- returns: the cleaned package scope without adding Conventional Commit punctuation
- code: `workflows/src/workhorse_workflows/coder/shared/commits.py::scope`
- tests: `workflows/tests/coder/test_commits.py::test_a_package_name_is_lowercased_and_stripped_to_what_a_scope_may_hold`

### describe

- sig: `describe(text: str) -> str`
- does: collapses all whitespace runs to single spaces and removes surrounding whitespace
- verify: json_path(path="$.description", equals="spaced out")
- does: removes one trailing period from the normalized text
- verify: json_path(path="$.description", equals="add password reset")
- does: lowercases the first character when the remainder of the first word is lowercase or empty
- verify: json_path(path="$.description", equals="add password reset")
- does: preserves an identifier-shaped first word when lowercasing it would change that identifier
- verify: json_path(path="$.description", equals="OAuth token refresh")
- returns: an empty string for empty or whitespace-only input
- code: `workflows/src/workhorse_workflows/coder/shared/commits.py::describe`
- tests: `workflows/tests/coder/test_commits.py::test_a_heading_becomes_a_description_without_becoming_a_different_word`

### subject

- sig: `subject(kind: str, package: str, description: str, marker: str = "") -> str`
- does: prefixes the normalized description with `kind(package):`, omitting parentheses when package is empty
- verify: json_path(path="$.subject", equals="feat(api-service): add guest cart")
- does: uses `no description` when the normalized description is empty
- verify: json_path(path="$.subject", equals="feat(api): no description")
- does: appends the optional marker after the description
- verify: json_path(path="$.subject", matches="^feat\\(api-service\\): .+\\[QA FAILED")
- does: trims the description to the available subject budget without trimming the marker suffix
- verify: json_path(path="$.subject", matches="\\[QA FAILED after 3 attempts")
- returns: a Conventional Commit subject string
- code: `workflows/src/workhorse_workflows/coder/shared/commits.py::subject`
- tests: `workflows/tests/coder/test_commits.py::test_a_long_description_is_trimmed_but_the_give_up_marker_never_is`

### message

- sig: `message(kind: str, package: str, description: str, marker: str = "", epic: str = "", story: str = "") -> str`
- does: places the generated subject on the first line
- verify: json_path(path="$.lines[0]", equals="feat(api-service): add guest cart")
- does: adds a blank line followed by an `Epic:` trailer when epic is non-empty
- verify: json_path(path="$.lines[2]", equals="Epic: checkout")
- does: adds a `Story:` trailer after the epic trailer when story is non-empty
- verify: json_path(path="$.lines[3]", equals="Story: guest-cart")
- does: returns only the subject when neither provenance value is supplied
- verify: count(subject="message lines without provenance trailers", equals=1)
- returns: the subject plus optional provenance trailers in epic-then-story order
- code: `workflows/src/workhorse_workflows/coder/shared/commits.py::message`
- tests: `workflows/tests/coder/test_commits.py::test_the_story_id_is_an_exact_footer_and_nothing_else`

### story_description

- sig: `story_description(root: Path, story_path: str, fallback: str = "") -> str`
- does: reads the first level-one Markdown heading from the file at `root / story_path` when that path is a regular file
- verify: json_path(path="$.description", equals="paginate the widget list")
- does: removes a leading `Story:` or `Epic` heading label before normalizing the heading
- verify: json_path(path="$.description", equals="record an expense against a group")
- does: uses the supplied fallback when the file is absent, unreadable, has no level-one heading, or the stripped heading is empty
- verify: json_path(path="$.description", equals="expense-record")
- returns: the normalized heading description or the normalized fallback text
- code: `workflows/src/workhorse_workflows/coder/shared/commits.py::story_description`
- tests: `workflows/tests/coder/test_commits.py::test_the_description_comes_from_the_story_heading`
- tests: `workflows/tests/coder/test_commits.py::test_a_heading_that_labels_itself_a_story_does_not_say_so_twice`
- tests: `workflows/tests/coder/test_commits.py::test_a_heading_that_is_nothing_but_its_label_falls_back_to_the_slug`
- tests: `workflows/tests/coder/test_commits.py::test_a_story_with_no_heading_or_no_file_falls_back_to_the_slug`
