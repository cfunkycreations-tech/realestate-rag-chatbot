.PHONY: dev test lint typecheck
dev:
	docker compose up --build
test:
	cd backend && python -m pytest -q
lint:
	cd frontend && npm run lint
typecheck:
	cd frontend && npm run typecheck
