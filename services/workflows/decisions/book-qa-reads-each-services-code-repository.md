story: none
date: 2026-11-23
elements: DryRunCoder
sources: workflows/src/workhorse_workflows/coder/book_qa/apps.py::service_app, workflows/src/workhorse_workflows/coder/book_qa/nodes.py::book_plan

In a workspace of several repositories the book lives in the artifacts folder and the code lives in other repositories. The book lane used to treat the artifacts folder as the code repository, so it found no change for the story's service and parked the run. It now reads each service's code from the repository that holds it. The `ostler` commands get that repository as `--app`, the story base and the stamp come from its history, and the lane commits the book and the code in their own repositories.

When two repositories hold a book for one bare service name, the lane prefers the repository whose `agents.yml` declares the service under `services:`, then the order of the workspace, and logs a warning. A service no repository holds is a usage error, exit 2, and the message names `agents.yml` and `ostler book move`. A book that stays flat, `services/<name>` in a repository with `book.home: repo`, keeps its own root as the code repository. A repository that keeps its own book is unchanged: its root is both the book and the code.
