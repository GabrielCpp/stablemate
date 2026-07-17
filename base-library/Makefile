# The base library — data, not a package. Nothing here is built or published: the tools
# read this directory from disk, or clone it from git into ~/.cache/stablemate.

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: test
test: ## Run the standalone test suite (the base must stand alone, with no overlay)
	@for t in tests/test_*.py; do echo ">> $$t"; uv run python $$t || exit 1; done

.PHONY: test-workflows
test-workflows: ## Run every workflow's own test suite
	uv run pytest workflows -q
