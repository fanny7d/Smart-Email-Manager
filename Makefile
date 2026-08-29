.PHONY: sync migrate migration-check api worker cli-test cli-acceptance test lint secret-check security-audit package-build openapi web-install web-dev web-build extension-build compose-config scale-check verify

sync:
	uv sync --all-groups

migrate:
	uv run sem-migrate

migration-check:
	uv run alembic check

api:
	uv run sem-api

worker:
	uv run sem-worker

cli-test:
	uv run sem system health

cli-acceptance:
	uv run python scripts/accept_cli.py

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run mypy
	pnpm lint:markdown

secret-check:
	uv run python scripts/check_secrets.py

security-audit:
	uv run --with pip-audit pip-audit --progress-spinner off --skip-editable
	pnpm audit --registry=https://registry.npmjs.org --audit-level high

package-build:
	uv build

openapi:
	uv run sem-openapi

web-install:
	pnpm install

web-dev:
	pnpm --dir web dev

web-build:
	pnpm --dir web build

extension-build:
	pnpm --dir extension build

compose-config:
	docker compose --env-file .env.production.example config --quiet

scale-check:
	uv run python scripts/benchmark_scale.py --accounts 10000

verify: lint secret-check test migration-check openapi web-build extension-build package-build compose-config scale-check
