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
test: ## Run the packages' test suites
	$(MAKE) -C workhorse test
	$(MAKE) -C farrier test
	# Guards the public/private split: the base library must resolve with no
	# private overlay configured. Without this, coupling creeps back invisibly —
	# it keeps working on a machine where the overlay shadows everything.
	$(MAKE) -C base-library test

.PHONY: build
build: ## Build sdists + wheels for both packages (into each package's dist/)
	$(MAKE) -C workhorse build
	$(MAKE) -C farrier build

.PHONY: publish-test
publish-test: ## Publish both packages to TestPyPI
	$(MAKE) -C workhorse publish-test
	$(MAKE) -C farrier publish-test

.PHONY: publish
publish: ## Publish both packages to PyPI
	$(MAKE) -C workhorse publish
	$(MAKE) -C farrier publish

.PHONY: version
version: ## Print both package versions
	@$(MAKE) -s -C workhorse version
	@$(MAKE) -s -C farrier version

.PHONY: next-version
next-version: ## Print the next inferred version for both packages (no changes)
	@$(MAKE) -s -C workhorse next-version
	@$(MAKE) -s -C farrier next-version

.PHONY: bump
bump: ## Stamp inferred next versions into both pyprojects (no commit)
	@$(MAKE) -s -C workhorse bump
	@$(MAKE) -s -C farrier bump

.PHONY: release
release: ## Release BOTH packages: bump from history, build, publish, commit, tag, push (DRY_RUN=1, …)
	$(MAKE) -C workhorse release
	$(MAKE) -C farrier release

.PHONY: release-test
release-test: ## Release both packages to TestPyPI
	$(MAKE) -C workhorse release-test
	$(MAKE) -C farrier release-test

# >>> farrier: agent launcher include (generated) >>>
# Surfaces agent-run / agent-install / agent-check etc. from the generated
# launcher. Re-created by `farrier install`; remove this block to opt out.
include .agents/agents.mk
# <<< farrier: agent launcher include <<<
