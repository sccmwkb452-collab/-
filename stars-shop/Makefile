# Developer shortcuts. Production deployment: see docs/DEPLOY.md.
PY ?= backend/.venv/bin/python

.PHONY: infra install migrate seed api worker bot webapp admin test test-backend test-frontend lint build admin-link

infra:            ## Postgres + Redis for local development
	docker compose -f docker-compose.dev.yml up -d

install:          ## Python venv + npm workspaces
	python3 -m venv backend/.venv
	$(PY) -m pip install -r backend/requirements-dev.txt ruff
	npm install

migrate:
	cd backend && .venv/bin/alembic upgrade head

seed:
	cd backend && .venv/bin/python -m starshop.cli seed

api:              ## http://127.0.0.1:8000 (docs at /api/docs)
	cd backend && .venv/bin/uvicorn starshop.api.app:app --reload --port 8000

worker:
	cd backend && .venv/bin/python -m starshop.worker

bot:
	cd backend && .venv/bin/python -m starshop.bot

webapp:           ## http://localhost:5173 (signed test user, no Telegram needed)
	VITE_DEV_AUTH=1 npm run dev -w webapp

admin:            ## http://localhost:5174/admin/ (log in with `make admin-link`)
	npm run dev -w admin

admin-link:
	cd backend && .venv/bin/python -m starshop.cli admin-link $${TG:-100001} | sed 's#5173#5174#'

test: test-backend test-frontend

test-backend:     ## needs PostgreSQL (TEST_DATABASE_URL, default stars_test)
	cd backend && .venv/bin/python -m pytest -q

test-frontend:
	npm run typecheck && npm test

lint:
	cd backend && .venv/bin/ruff check starshop tests && .venv/bin/ruff format --check starshop tests

build:
	npm run build
