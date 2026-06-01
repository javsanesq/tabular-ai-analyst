PYTHON ?= python3

.PHONY: install test api db-upgrade db-revision docker-up docker-down docker-config benchmark ui-build lint smoke-e2e

install:
	cd api && $(PYTHON) -m pip install -e .[dev]

test:
	PYTHONPATH=api/src APP_ENV=test DATABASE_URL=sqlite+pysqlite:///:memory: DATA_DIR=data/test $(PYTHON) -m pytest -q

api:
	cd api && PYTHONPATH=src uvicorn tabular_analyst.main:app --reload --host 0.0.0.0 --port 8000

db-upgrade:
	cd api && PYTHONPATH=src alembic upgrade head

db-revision:
	cd api && PYTHONPATH=src alembic revision --autogenerate -m "$(m)"

docker-up:
	cp -n .env.example .env || true
	docker compose up --build

docker-down:
	docker compose down

docker-config:
	docker compose config

benchmark:
	PYTHONPATH=api/src APP_ENV=test DATABASE_URL=sqlite+pysqlite:///:memory: DATA_DIR=data/test $(PYTHON) scripts/run_benchmark.py

ui-build:
	cd ui && npm install && npm run build

lint:
	cd api && $(PYTHON) -m compileall src
	cd ui && npm run typecheck

smoke-e2e:
	scripts/smoke_docker.sh
