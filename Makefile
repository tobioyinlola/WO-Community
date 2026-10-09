PY ?= python

.PHONY: up down install migrate run worker beat test lint format typecheck security imports schema check ci

up:
	docker compose up -d db redis mail storage

down:
	docker compose down

install:
	$(PY) -m pip install -e ".[dev]"

migrate:
	$(PY) manage.py migrate

run:
	$(PY) manage.py runserver

worker:
	celery -A config worker -l info -Q critical,default,email,media,exports,analytics

beat:
	celery -A config beat -l info

test:
	pytest

lint:
	ruff check .
	black --check .

format:
	ruff check --fix .
	black .

typecheck:
	mypy apps config

security:
	bandit -q -c pyproject.toml -r apps config
	pip-audit

imports:
	lint-imports

schema:
	$(PY) manage.py spectacular --file docs/api/openapi.yaml --validate --fail-on-warn

check:
	DJANGO_SETTINGS_MODULE=config.settings.production $(PY) manage.py check --deploy --fail-level WARNING

ci: lint typecheck security imports test schema check
