.PHONY: help install dev lint format test test-cov clean build docs serve

PYTHON ?= python
PIP ?= pip

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install package in production mode
	$(PIP) install .

dev: ## Install package in development mode with all extras
	$(PIP) install -e ".[dev]"

lint: ## Run all linters
	ruff check spawn_agent/ tests/
	mypy spawn_agent/ --ignore-missing-imports
	black --check spawn_agent/ tests/

format: ## Auto-format code
	black spawn_agent/ tests/
	ruff check --fix spawn_agent/ tests/

test: ## Run tests
	pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage
	pytest tests/ -v --tb=short --cov=spawn_agent --cov-report=term-missing --cov-report=html

clean: ## Remove build artifacts
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

build: clean ## Build distribution packages
	$(PYTHON) -m build

docs: ## Build documentation (placeholder)
	@echo "Documentation build not yet configured"

serve: ## Start the agent with example config
	spawn-agent serve --config config/spawn_agent.example.yml
