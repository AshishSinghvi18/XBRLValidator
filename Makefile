.PHONY: help install dev lint format mypy typecheck test test-fast test-cov test-conformance \
       build clean docker docker-worker docker-up docker-down run-api run-worker \
       check import-lint all ci

PYTHON ?= python3
PIP ?= pip
APP_NAME = xbrl-validator
SRC_DIR = src
TEST_DIR = tests

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Installation ────────────────────────────────────────────────────────────────

install: ## Install production dependencies
	$(PIP) install -e .

dev: ## Install all dependencies (dev + conformance + ai)
	$(PIP) install -e ".[dev,conformance,ai]"

# ── Code Quality ────────────────────────────────────────────────────────────────

lint: ## Run ruff linter
	ruff check $(SRC_DIR) $(TEST_DIR)

format: ## Format code with ruff and black
	ruff check --fix $(SRC_DIR) $(TEST_DIR)
	black $(SRC_DIR) $(TEST_DIR)

mypy: ## Run mypy type checker
	mypy $(SRC_DIR)

typecheck: mypy ## Alias for mypy

import-lint: ## Check import architecture constraints
	lint-imports

check: lint mypy import-lint ## Run all static checks (lint + mypy + import-lint)

# ── Testing ─────────────────────────────────────────────────────────────────────

test: ## Run all tests
	pytest $(TEST_DIR) -v

test-fast: ## Run tests excluding slow and conformance
	pytest $(TEST_DIR) -v -m "not slow and not conformance and not large_file"

test-cov: ## Run tests with coverage report
	pytest $(TEST_DIR) -v --cov=$(SRC_DIR) --cov-report=term-missing --cov-report=html

test-conformance: ## Run XBRL conformance suite tests
	pytest $(TEST_DIR) -v -m conformance --timeout=600 -n auto

test-security: ## Run security-focused tests
	pytest $(TEST_DIR) -v -m security --timeout=120

bench: ## Run benchmark tests
	pytest $(TEST_DIR) -v -m benchmark --benchmark-only

# ── Build & Package ─────────────────────────────────────────────────────────────

build: clean ## Build distribution packages
	$(PYTHON) -m build

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true

# ── Docker ──────────────────────────────────────────────────────────────────────

docker: ## Build API server Docker image
	docker build -t $(APP_NAME):latest -f Dockerfile .

docker-worker: ## Build Celery worker Docker image
	docker build -t $(APP_NAME)-worker:latest -f Dockerfile.worker .

docker-up: ## Start full stack with Docker Compose
	docker compose up -d

docker-down: ## Stop Docker Compose stack
	docker compose down -v

docker-logs: ## Tail Docker Compose logs
	docker compose logs -f

# ── Run Services ────────────────────────────────────────────────────────────────

run-api: ## Run FastAPI development server
	uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000

run-worker: ## Run Celery worker
	celery -A src.api.worker worker --loglevel=info --concurrency=4

# ── CI Pipeline ─────────────────────────────────────────────────────────────────

ci: check test-cov ## Run full CI pipeline (checks + tests with coverage)

all: dev check test-cov build ## Full build: install, check, test, package
