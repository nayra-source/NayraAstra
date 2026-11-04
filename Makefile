.PHONY: install lint format typecheck test check clean

# Install project in editable mode with dev dependencies
install:
	pip install -e .[dev]

# Run ruff linter
lint:
	ruff check src tests

# Auto-fix formatting
format:
	ruff format src tests
	ruff check --fix src tests

# Run mypy strict type checking
typecheck:
	mypy src

# Run pytest with coverage
test:
	pytest

# Run all checks (lint, format-check, typecheck, test)
check:
	ruff check src tests
	ruff format --check src tests
	mypy src
	pytest

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

