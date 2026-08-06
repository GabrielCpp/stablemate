# saddlebag — build and test tasks.
#
# Nothing here publishes: saddlebag is not on PyPI (see the README). Versions still
# come from release-please so a changelog exists when it ever ships.

.DEFAULT_GOAL := help

DIST        := dist
NAME        := $(shell grep -m1 '^name' pyproject.toml | cut -d'"' -f2)
VERSION     := $(shell grep -m1 '^version' pyproject.toml | cut -d'"' -f2)

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Create/sync the workspace venv from the root uv.lock
	uv sync

.PHONY: test
test: ## Run the test suite
	# pytest, not a `python tests/test_*.py` loop: these tests are pytest-style
	# (fixtures, tmp_path) with no __main__ runner — see ostler/Makefile for the
	# incident that comment records.
	uv run --extra test pytest tests -q

.PHONY: build
build: clean ## Build sdist + wheel into this package's dist/
	uv build --package $(NAME) --out-dir dist

.PHONY: check
check: build ## Build and list the wheel contents (verify packaged files)
	@unzip -l $(DIST)/$(subst -,_,$(NAME))-$(VERSION)-py3-none-any.whl

.PHONY: clean
clean: ## Remove build artifacts
	rm -rf $(DIST) build *.egg-info

.PHONY: version
version: ## Print the current distribution name and version
	@echo "$(NAME) $(VERSION)"
