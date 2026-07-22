COMPOSE_PROJECT_NAME ?= hub
PROFILES ?= mqtt core
COMPOSE_FILES = -f docker-compose.yml -f docker-compose.dev.yml
VOLUMES = $(COMPOSE_PROJECT_NAME)_data $(COMPOSE_PROJECT_NAME)_mqtt_data \
          $(COMPOSE_PROJECT_NAME)_observer_data

.PHONY: build up down logs backup restore test test-cov test-unit test-frontend \
        e2e-build e2e-up e2e-down e2e-seed e2e-test

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
# Coverage is opt-in (use test-cov). Dev loop runs in parallel across cores.
# `test` runs the backend suite then the frontend (vitest) suite.
test:
	pytest -nauto --no-cov
	$(MAKE) test-frontend

test-cov:
	pytest --cov=meshcore_hub --cov-report=term-missing

test-unit:
	pytest -nauto --no-cov tests/test_common/ tests/test_api/ tests/test_collector/ tests/test_web/

test-frontend:
	npm run test:frontend

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
