.PHONY: install dev lint test test-unit test-integration test-security build clean docker

install:
	pip install -e .

dev:
	pip install -e ".[dev,conformance]"

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

typecheck:
	mypy --strict src/

test:
	pytest tests/unit -v --tb=short

test-unit:
	pytest tests/unit -v --tb=short --cov=src --cov-report=term-missing

test-integration:
	pytest tests/integration -v --tb=short

test-security:
	pytest tests/security -v --tb=short

test-all:
	pytest tests/ -v --tb=short --cov=src

build:
	python -m build

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

docker:
	docker build -t xbrl-validator .

docker-compose:
	docker-compose up -d

check-imports:
	lint-imports

check-error-codes:
	python scripts/check_error_codes.py

ci: lint typecheck test check-imports
