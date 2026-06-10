# farrier — build, test, and publish tasks.
#
# Publishing reads the PyPI token from ~/.pypirc (the [pypi] password entry),
# since `uv publish` does not read .pypirc itself.

.DEFAULT_GOAL := help

DIST        := dist
PYPI_TOKEN   = $(shell awk '/password/{print $$3}' $(HOME)/.pypirc)
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
test: ## Run the standalone test suite
	@for t in tests/test_*.py; do echo ">> $$t"; uv run python $$t || exit 1; done

.PHONY: build
build: clean ## Build sdist + wheel into dist/
	uv build --package $(NAME)

.PHONY: check
check: build ## Build and list the wheel contents (verify packaged files)
	@unzip -l $(DIST)/$(subst -,_,$(NAME))-$(VERSION)-py3-none-any.whl

.PHONY: publish-test
publish-test: build ## Publish to TestPyPI
	@UV_PUBLISH_TOKEN="$(PYPI_TOKEN)" uv publish --publish-url https://test.pypi.org/legacy/

.PHONY: publish
publish: build ## Publish to PyPI (token from ~/.pypirc)
	@UV_PUBLISH_TOKEN="$(PYPI_TOKEN)" uv publish

.PHONY: verify-install
verify-install: ## Install the published package from PyPI and run --help
	uv run --with $(NAME) --no-project --refresh-package $(NAME) -- farrier --help

.PHONY: clean
clean: ## Remove build artifacts
	rm -rf $(DIST) build *.egg-info

.PHONY: version
version: ## Print the current distribution name and version
	@echo "$(NAME) $(VERSION)"
