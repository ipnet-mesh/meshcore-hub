ifneq (,$(wildcard ./.env))
    include .env
    export
endif

COMPOSE_PROJECT_NAME ?= hub-dev
PROFILES ?= mqtt core
COMPOSE_FILES = -f docker-compose.yml -f docker-compose.dev.yml
VOLUMES = $(COMPOSE_PROJECT_NAME)_hub_data $(COMPOSE_PROJECT_NAME)_mqtt_broker_data \
          $(COMPOSE_PROJECT_NAME)_prometheus_data $(COMPOSE_PROJECT_NAME)_alertmanager_data \
          $(COMPOSE_PROJECT_NAME)_packetcapture_data

.PHONY: build up down logs backup restore

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
