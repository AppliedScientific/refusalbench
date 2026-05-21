.PHONY: venv install test lint typecheck ci fmt clean

venv:
	python3 -m venv .venv
	@echo "Run: source .venv/bin/activate"

install:
	pip install -e ".[dev,stats]"

test:
	pytest --cov=refusalbench --cov-report=term-missing

lint:
	ruff check src tests
	ruff format --check src tests

typecheck:
	mypy --strict src/refusalbench

ci: lint typecheck test

fmt:
	ruff format src tests
	ruff check --fix src tests

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage build dist
	find . -name __pycache__ -prune -exec rm -rf {} +
