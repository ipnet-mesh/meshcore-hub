COMPOSE_PROJECT_NAME ?= hub
PROFILES ?= mqtt core
COMPOSE_FILES = -f docker-compose.yml -f docker-compose.dev.yml
VOLUMES = $(COMPOSE_PROJECT_NAME)_data $(COMPOSE_PROJECT_NAME)_mqtt_data \
          $(COMPOSE_PROJECT_NAME)_observer_data

.PHONY: build up down logs backup restore test test-cov test-unit test-frontend \
        test-db-up test-db-down e2e-build e2e-up e2e-down e2e-seed e2e-test

build:
	docker compose $(COMPOSE_FILES) --profile all build --no-cache

up:
	docker compose $(COMPOSE_FILES) $(foreach p,$(PROFILES),--profile $(p)) up -d --force-recreate

down:
	docker compose $(COMPOSE_FILES) --profile all down --remove-orphans

logs:
	docker compose $(COMPOSE_FILES) --profile all logs -f

backup:
	@mkdir -p backup
	@for vol in $(VOLUMES); do \
		echo "Backing up $$vol..."; \
		docker run --rm -v $$vol:/data -v $(PWD)/backup:/backup \
			alpine tar czf /backup/$$vol-$$(date +%Y%m%d-%H%M%S).tar.gz -C / data; \
	done
	@echo "Backups saved to $(PWD)/backup/"

restore:
	@if [ -z "$(FILE)" ]; then echo "Usage: make restore FILE=backup/<tarball>"; exit 1; fi
	@vol=$$(basename $(FILE) | sed 's/-[0-9]\{8\}-[0-9]\{6\}\.tar\.gz//'); \
	echo "Restoring $$vol from $(FILE)..."; \
	docker run --rm -v $$vol:/data -v $(PWD)/backup:/backup \
		alpine sh -c "cd / && tar xzf /backup/$$(basename $(FILE))"

# --- Tests ---------------------------------------------------------------
# Backend tests run against PostgreSQL and Redis: `test`, `test-cov`, and
# `test-unit` start the throwaway test stack automatically and stop it again
# afterwards — even when pytest fails (EXIT trap). Set TEST_POSTGRES_URL /
# TEST_REDIS_URL to point at your own instances and the automatic up/down is
# skipped. For direct pytest runs, start it manually with `make test-db-up`.
# Coverage is opt-in (use test-cov). Dev loop runs in parallel across cores.
# `test` runs the backend suite then the frontend (vitest) suite.
test:
	set -e; \
	if [ -z "$$TEST_POSTGRES_URL" ]; then \
		$(MAKE) --no-print-directory test-db-up; \
		trap '$(MAKE) --no-print-directory test-db-down' EXIT; \
	fi; \
	pytest -nauto --no-cov; \
	$(MAKE) --no-print-directory test-frontend

test-cov:
	set -e; \
	if [ -z "$$TEST_POSTGRES_URL" ]; then \
		$(MAKE) --no-print-directory test-db-up; \
		trap '$(MAKE) --no-print-directory test-db-down' EXIT; \
	fi; \
	pytest --cov=meshcore_hub --cov-report=term-missing

test-unit:
	set -e; \
	if [ -z "$$TEST_POSTGRES_URL" ]; then \
		$(MAKE) --no-print-directory test-db-up; \
		trap '$(MAKE) --no-print-directory test-db-down' EXIT; \
	fi; \
	pytest -nauto --no-cov tests/test_common/ tests/test_api/ tests/test_collector/ tests/test_web/

test-frontend:
	npm run test:frontend

# Throwaway PostgreSQL (127.0.0.1:55432) + Redis (127.0.0.1:55433) for the
# backend suite (dev-only creds, ephemeral tmpfs storage). Redis is required
# cache infrastructure — pytest fails fast with a hint if either is
# unreachable. The project name is pinned so a COMPOSE_PROJECT_NAME set in
# .env (the dev stack) can never make `down` target the dev services.
TEST_DB_COMPOSE = docker compose -f docker-compose.test-db.yml -p meshcore-hub-test-db

test-db-up:
	$(TEST_DB_COMPOSE) up -d --wait

test-db-down:
	$(TEST_DB_COMPOSE) down -v --remove-orphans

# --- E2E (Playwright) ---------------------------------------------------
# Self-contained throwaway stack (own ephemeral Postgres, isolated volumes).
#   make e2e-build && make e2e-up   # start the stack (build first time)
#   make e2e-test                   # seeds data, then runs the Playwright suite
#   make e2e-down                   # tears everything down (destroys the DB)
E2E_COMPOSE = docker compose -f e2e/docker-compose.test.yml

e2e-build:
	$(E2E_COMPOSE) build

e2e-up:
	$(E2E_COMPOSE) up -d

e2e-down:
	$(E2E_COMPOSE) down -v --remove-orphans

e2e-seed:
	$(E2E_COMPOSE) exec -T collector python /seed_data.py

e2e-test:
	npm run test:e2e
