PYTHON ?= python

.PHONY: db-up db-down migrate backend frontend test test-backend test-frontend

db-up:
	docker compose up -d

db-down:
	docker compose down

migrate:
	cd backend && $(PYTHON) -m alembic upgrade head

backend:
	cd backend && $(PYTHON) -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev

test-backend:
	cd backend && $(PYTHON) -m pytest

test-frontend:
	cd frontend && npm test

test: test-backend test-frontend
