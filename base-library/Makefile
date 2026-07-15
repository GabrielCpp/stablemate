# stablemate-library — the base library layer (content, not logic).

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: test
test: ## Run the standalone test suite (the base must stand alone, with no overlay)
	@for t in tests/test_*.py; do echo ">> $$t"; uv run python $$t || exit 1; done

.PHONY: build
build: ## Build the sdist + wheel into dist/
	uv build --package stablemate-library --out-dir dist
