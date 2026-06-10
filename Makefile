# stablemate workspace — delegates build/test/publish to each member package.

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: sync
sync: ## Sync the workspace venv (all members) from the root uv.lock
	uv sync --all-packages

.PHONY: test
test: ## Run both packages' test suites
	$(MAKE) -C workhorse test
	$(MAKE) -C farrier test

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
