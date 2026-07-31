# stablemate workspace — delegates build/test/publish to each member package.

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: sync
sync: ## Sync the workspace venv (all members) from the root uv.lock
	uv sync --all-packages

.PHONY: hooks
hooks: ## Install the git hooks (blocks private overlay names from this public repo)
	git config core.hooksPath .githooks
	@echo "hooks installed. Names come from \$$STABLEMATE_PRIVATE_NAMES or"
	@echo "\$$GIT_DIR/private-names (both untracked); with neither, the hook is a no-op."

.PHONY: test
test: ## Run the packages' test suites, the workflow suites, and the public/private guard
	$(MAKE) -C core test
	$(MAKE) -C workhorse test
	$(MAKE) -C workflows test
	$(MAKE) -C ostler test
	$(MAKE) -C farrier test
	$(MAKE) -C groom test
	$(MAKE) test-bench
	$(MAKE) check-public
	$(MAKE) check-no-env
	$(MAKE) check-parsers

.PHONY: test-bench
test-bench: ## Run the benchmark harness's own tests (its scoring must be trustworthy)
	# A benchmark whose scoring is wrong is worse than no benchmark: it reports a number
	# that nobody re-derives. These cover the properties that number rests on.
	uv run pytest benchmarks/tests -q

.PHONY: okf-verify
okf-verify: ## Verify every OKF book's coverage against its source (non-zero = incomplete)
	# The predicate a stop condition can be held to. A goal phrased as prose ("the books
	# are complete") is judged by the self-assessment the coverage instrument exists to
	# remove; `make okf-verify exits 0` is something a run can be refused by.
	uv run python scripts/okf_verify.py

.PHONY: check-public
check-public: ## Guard the public/private split (no private names; the base stands alone)
	# Two silent failure modes, both invisible on a machine where the private overlay
	# is configured and shadows everything: a private name reaching this public repo,
	# and a base skill/workflow quietly depending on the overlay.
	uv run python scripts/check_public.py

.PHONY: check-no-env
check-no-env: ## Guard the no-environment rule (a workflow's inputs are parameters)
	# A value read from os.environ is in no checkpoint and no telemetry, so a resume
	# silently takes a different one and nobody can tell what the run worked on.
	uv run python scripts/check_no_env.py

.PHONY: check-parsers
check-parsers: ## Guard the parse-don't-match rule (a format with a grammar gets its parser)
	# A regex over a structured document is that format's parser rewritten without its
	# cases, and it fails silently in both directions — a `//` inside a JSON string read
	# as a comment, a link matched inside a fenced code block.
	uv run python scripts/check_parsers.py

.PHONY: build
build: ## Build sdists + wheels (into each package's dist/)
	$(MAKE) -C core build
	$(MAKE) -C workhorse build
	# workflows carries the workflows themselves and depends on workhorse-agent,
	# so it builds after the engine. It is not published yet — see workflows/README.md.
	$(MAKE) -C workflows build
	$(MAKE) -C farrier build

.PHONY: publish-test
publish-test: ## Publish both packages to TestPyPI
	$(MAKE) -C core publish-test
	$(MAKE) -C workhorse publish-test
	$(MAKE) -C farrier publish-test

.PHONY: publish
publish: ## Publish to PyPI. core goes FIRST — workhorse and farrier depend on it
	$(MAKE) -C core publish
	$(MAKE) -C workhorse publish
	$(MAKE) -C farrier publish

.PHONY: version
version: ## Print both package versions
	@$(MAKE) -s -C core version
	@$(MAKE) -s -C workhorse version
	@$(MAKE) -s -C farrier version

.PHONY: next-version
next-version: ## Print the next inferred version for both packages (no changes)
	@$(MAKE) -s -C core next-version
	@$(MAKE) -s -C workhorse next-version
	@$(MAKE) -s -C farrier next-version

.PHONY: bump
bump: ## Stamp inferred next versions into both pyprojects (no commit)
	@$(MAKE) -s -C core bump
	@$(MAKE) -s -C workhorse bump
	@$(MAKE) -s -C farrier bump

.PHONY: release
release: ## Release: bump from history, build, publish, commit, tag, push (DRY_RUN=1, …)
	# core leads: workhorse and farrier declare stablemate-core, so releasing them
	# against an unpublished core produces installs that cannot resolve.
	$(MAKE) -C core release
	$(MAKE) -C workhorse release
	$(MAKE) -C farrier release

.PHONY: release-test
release-test: ## Release both packages to TestPyPI
	$(MAKE) -C core release-test
	$(MAKE) -C workhorse release-test
	$(MAKE) -C farrier release-test

# >>> farrier: agent launcher include (generated) >>>
# Surfaces agent-install / agent-check from the generated
# launcher. Re-created by `farrier install`; remove this block to opt out.
include .agents/agents.mk
# <<< farrier: agent launcher include <<<
