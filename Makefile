.PHONY: dev test lint typecheck
# Use the repository's virtual environment, never an arbitrary system Python.
PYTHON := $(if $(wildcard .venv/Scripts/python.exe),.venv/Scripts/python.exe,.venv/bin/python)
dev:
	docker compose up --build
test:
	$(PYTHON) -m pytest -q backend/tests
lint:
	cd frontend && npm run lint
typecheck:
	cd frontend && npm run typecheck
