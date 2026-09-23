# Developer tasks. `make pre-commit` runs the same checks as CI, in the same order.

.PHONY: help install lint format format-check typecheck test pre-commit install-hooks

help:
	@echo "make install        Sync dependencies"
	@echo "make lint           ruff check"
	@echo "make format         ruff format (rewrites files)"
	@echo "make format-check   ruff format --check"
	@echo "make typecheck      mypy --strict"
	@echo "make test           pytest with the 90% coverage gate"
	@echo "make pre-commit     Everything CI runs"
	@echo "make install-hooks  Run 'make pre-commit' before every git commit"

install:
	uv sync

lint:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

typecheck:
	uv run mypy

test:
	uv run pytest

pre-commit: lint format-check typecheck test

install-hooks:
	@printf '#!/bin/sh\n# Installed by `make install-hooks`. Skip once with: git commit --no-verify\nexec make pre-commit\n' > .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "Installed .git/hooks/pre-commit"
