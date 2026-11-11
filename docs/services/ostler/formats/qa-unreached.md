---
type: format
slug: qa-unreached
title: QA unreached claims
---
# QA unreached claims

The list of claims a story's scenario plan owes when every service of the story has an executable
book. The caller writes it into the story's spec directory before it builds the QA context packet.
Every build of the packet, a repair rebuild included, reads it and makes those claims the packet's
only acceptance criteria, so a plan is validated against the claims and nothing else.

- file: `qa-unreached.json` in the story's spec directory, beside `qa-okf-context.json`
- code: `ostler/ostler/qa/compile.py::apply_unreached` @da9f18b6fa49
- code: `ostler/ostler/qa/context.py::cmd_context` @4bda2b351c61
- detail: [QA deferrals](qa-deferrals.md)
- detail: [compiling a book into a QA plan](../concepts/compiling-a-book-into-a-qa-plan.md)
- detail: [coder book qa package](../../workflows/concepts/coder-book-qa-package.md)
- tests: `ostler/tests/test_qa_book_only_claims.py::test_the_unreached_claims_replace_the_story_criteria_in_the_packet`
- tests: `ostler/tests/test_qa_book_only_claims.py::test_no_claims_file_leaves_the_story_criteria_and_the_unmapped_change`
- tests: `ostler/tests/test_qa_book_only_claims.py::test_a_plan_whose_covers_are_the_claims_alone_validates`
- tests: `ostler/tests/test_qa_book_only_claims.py::test_a_plan_that_leaves_a_claim_uncovered_is_refused`
- rule: the file's presence marks the story as judged by its books, so the packet drops the `unmapped-change` findings, because no markdown page owns the code of a service whose book holds its claims
- rule: a claim is a criterion named `claim:<n>`, numbered from 1 in the order listed, and a plan covers it with `covers=["claim:<n>"]`, because a claim has no id of its own and its words are too long to copy into a plan exactly
- rule: a plan that leaves a claim uncovered fails validation as an uncovered acceptance criterion, and a `claim:<n>` cover with no file naming it fails as an unknown id
- rule: an empty list leaves the packet with no criterion, and a missing or unreadable file changes nothing

The file is a JSON list of strings. A value that is not a list is ignored.

## Fields

### claims

- type: `list[str]`
- required: true
- semantics: each string is a claim of the story, in the story's words, that no call of the service books can show
- semantics: the packet's `acceptanceCriteria` holds one row per string, with the id `claim:<n>`, the string as its `requirement`, kind `behavioral` and category `functional`
- verify: json_path(path="$[0]", equals="the export lands in the mailbox")
- code: `ostler/ostler/qa/compile.py::apply_unreached` @da9f18b6fa49
