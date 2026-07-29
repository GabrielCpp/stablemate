# workhorse-workflows — build and test tasks.

.DEFAULT_GOAL := help

DIST  := dist
NAME  := $(shell grep -m1 '^name' pyproject.toml | cut -d'"' -f2)

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: test
test: ## Run the standalone test suite (no network, no real sleeps)
	@for t in tests/test_*.py; do \
		[ -e "$$t" ] || continue; \
		echo ">> $$t"; uv run python $$t || exit 1; \
	done

.PHONY: build
build: clean ## Build sdist + wheel into this package's dist/
	uv build --package $(NAME) --out-dir dist

.PHONY: clean
clean: ## Remove build artifacts
	rm -rf $(DIST) build *.egg-info
