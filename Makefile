.PHONY: help install dev dev-backend dev-frontend test test-backend test-frontend \
        build build-backend build-frontend demo lint clean docker-up docker-down

help:  ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install:  ## Install backend + frontend deps
	cd backend && python3 -m venv .venv && .venv/bin/pip install --index-url https://pypi.org/simple/ -r requirements.txt
	cd frontend && npm install

dev:  ## Run BE and FE locally (two terminals — use `make docker-up` for one-command)
	@echo "Run these in two terminals:"
	@echo "  make dev-backend"
	@echo "  make dev-frontend"

dev-backend:  ## Run FastAPI with reload
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

dev-frontend:  ## Run Vite dev server
	cd frontend && npm run dev

test: test-backend test-frontend  ## Run all tests

test-backend:  ## Backend pytest
	cd backend && .venv/bin/python -m pytest tests/ -v

test-frontend:  ## Frontend typecheck (no unit tests in v1)
	cd frontend && npm run typecheck

build: build-backend build-frontend  ## Build production artefacts

build-backend:  ## Validate backend startup
	cd backend && .venv/bin/python -c "from app.main import app; print('backend ok:', len(app.routes), 'routes')"

build-frontend:  ## Production Vite build
	cd frontend && npm run build

demo:  ## Run the CLI demo conversation (requires GROQ_API_KEY)
	cd backend && .venv/bin/python -m examples.demo_conversation

lint:  ## Ruff check
	cd backend && .venv/bin/ruff check app/ tests/ examples/

docker-up:  ## Build + run BE+FE via docker compose
	docker compose up --build

docker-down:  ## Stop docker compose services
	docker compose down

clean:  ## Remove caches and build artefacts
	rm -rf backend/.pytest_cache backend/.ruff_cache backend/__pycache__
	find backend -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/dist frontend/.vite
