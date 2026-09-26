# Shortcuts for common tasks. Run `make` (or `make help`) to list them.
# Recipes are plain `uv` commands and help uses make's own $(info), so this works the same from
# PowerShell, cmd or Git Bash (Windows make runs recipes in cmd or sh depending on the PATH).

.DEFAULT_GOAL := help
.PHONY: help install dev run test lint format check lock key

PORT ?= 8000

help:
	$(info Usage: make [target])
	$(info )
	$(info   install   Install dependencies (uv sync))
	$(info   dev       Start the dev server with auto-reload, docs at http://127.0.0.1:$(PORT)/docs)
	$(info   run       Start the server like production (no reload, listens on 0.0.0.0))
	$(info   test      Run the tests)
	$(info   lint      Check code with ruff (lint + format check))
	$(info   format    Format code and apply safe lint fixes)
	$(info   check     Everything CI runs: locked sync, lint and tests)
	$(info   lock      Update uv.lock after changing dependencies)
	$(info   key       Generate a random SERVICE_API_KEY)
	$(info )
	$(info   Override the port with e.g. make dev PORT=8080)
	@exit 0

install:
	uv sync

dev:
	uv run fastapi dev app/main.py --port $(PORT)

run:
	uv run uvicorn app.main:app --host 0.0.0.0 --port $(PORT)

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

check:
	uv sync --locked
	uv run ruff check .
	uv run ruff format --check .
	uv run pytest

lock:
	uv lock

key:
	@uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
