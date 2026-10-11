PY ?= python

.PHONY: up down install migrate run worker beat test lint format typecheck security imports schema check ci lint-migrations

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
	$(PY) scripts/deploy_check.py

ci: lint typecheck security imports lint-migrations test schema check

# Lints only the migrations that are new compared with BASE (default: the main branch), because
# old migrations already ran. Findings are real deploy risks: read them before ignoring one.
BASE ?= origin/main
lint-migrations:
	DJANGO_SETTINGS_MODULE=config.settings.test $(PY) manage.py lintmigrations --no-cache \
		--git-commit-id $(BASE) --ignore-initial-migrations --exclude-apps django_celery_beat \
		--sql-analyser postgresql --ignore-name 0006_course_files  # uploads: widening a varchar is metadata only
