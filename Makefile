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
	$(MAKE) -C farrier test
	$(MAKE) test-workflows
	$(MAKE) check-public

.PHONY: test-workflows
test-workflows: ## Run each workflow's own test suite (the base library is data; its workflows are tested)
	# One pytest per workflow, from inside the workflow dir, because each owns its
	# pytest.ini (coder's sets `-n auto`) and a config only applies from its own
	# directory. Collecting them together would also collide: author/ and coder/ ship
	# same-named test modules, which pytest cannot import side by side.
	@for d in base-library/workflows/*/; do \
		[ -d "$$d/tests" ] || continue; \
		echo ">> $$d"; \
		( cd "$$d" && uv run pytest tests -q ) || exit 1; \
	done

.PHONY: check-public
check-public: ## Guard the public/private split (no private names; the base stands alone)
	# Two silent failure modes, both invisible on a machine where the private overlay
	# is configured and shadows everything: a private name reaching this public repo,
	# and a base skill/workflow quietly depending on the overlay.
	uv run python scripts/check_public.py

.PHONY: build
build: ## Build sdists + wheels (into each package's dist/)
	$(MAKE) -C core build
	$(MAKE) -C workhorse build
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
# Surfaces agent-run / agent-install / agent-check etc. from the generated
# launcher. Re-created by `farrier install`; remove this block to opt out.
include .agents/agents.mk
# <<< farrier: agent launcher include <<<
