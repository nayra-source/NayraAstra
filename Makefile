VENV ?= $(shell if [ -d .venv/bin ]; then echo .venv/bin/; fi)

.PHONY: install lint format typecheck test check clean

# Install project in editable mode with dev dependencies
install:
	$(VENV)pip install -e .[dev]

# Run ruff linter
lint:
	$(VENV)ruff check src tests

# Auto-fix formatting
format:
	$(VENV)ruff format src tests
	$(VENV)ruff check --fix src tests

# Run mypy strict type checking
typecheck:
	$(VENV)mypy src

# Run pytest with coverage
test:
	$(VENV)pytest

# Run all checks (lint, format-check, typecheck, test)
check:
	$(VENV)ruff check src tests
	$(VENV)ruff format --check src tests
	$(VENV)mypy src
	$(VENV)pytest

# Remove build artifacts and caches
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true
	find . -name "coverage.xml" -delete 2>/dev/null || true
	rm -rf dist/ build/ htmlcov/
