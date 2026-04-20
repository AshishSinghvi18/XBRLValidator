.PHONY: install dev lint type-check test test-unit test-streaming test-integration test-all clean docker

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

type-check:
	mypy src/

test:
	pytest tests/unit/ -v

test-unit:
	pytest tests/unit/ -v

test-streaming:
	pytest tests/unit/streaming/ -v

test-integration:
	pytest tests/integration/ -v

test-all:
	pytest tests/ -v --timeout=300

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov/

docker:
	docker build -t xbrl-validator .

docker-worker:
	docker build -t xbrl-validator-worker -f Dockerfile.worker .
