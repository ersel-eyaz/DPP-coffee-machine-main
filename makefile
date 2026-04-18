# -------- Settings (portable) --------
ifeq ($(OS),Windows_NT)
  # Adjust if Git is installed elsewhere:
  SHELL := C:/Program Files/Git/bin/bash.exe
  .SHELLFLAGS := -lc
else
  SHELL := /usr/bin/env bash
  .SHELLFLAGS := -eu -o pipefail -c
endif

COMPOSE ?= docker compose

COMPOSE_BASE  := -f docker-compose.yml
COMPOSE_NGROK := -f docker-compose.ngrok.yml
PROFILE_FULL  := --profile full
PROFILE_DB    := --profile db

# Read NGROK host from file
NGROK ?= $(strip $(shell [ -f .ngrok-host ] && tr -d '\r\n' < .ngrok-host || true))

# change credentials/names
DB_NAME := dpp_prototype
DB_USER := root
DB_PASS := example
DB_URI_LOCAL  := mongodb://$(DB_USER):$(DB_PASS)@127.0.0.1:27017/$(DB_NAME)?authSource=admin
DB_URI_DOCKER := mongodb://$(DB_USER):$(DB_PASS)@mongo:27017/$(DB_NAME)?authSource=admin

# Pick compose files depending on NGROK presence
ifeq ($(strip $(NGROK)),)
  COMPOSE_FILES := $(COMPOSE_BASE)
else
  COMPOSE_FILES := $(COMPOSE_BASE) $(COMPOSE_NGROK)
endif

# -------- Help --------
.PHONY: help
help:
	@echo ""
	@echo "Full Docker dev:"
	@echo "  make docker-up [NGROK=host]        # up -d all services; uses ngrok override if NGROK set"
	@echo "  make docker-build                  # (re)build backend/frontend images"
	@echo "  make docker-logs                   # tail backend logs"
	@echo "  make docker-down                   # stop and remove containers"
	@echo "  make docker-down-all               # down + remove named volumes"
	@echo ""
	@echo "Seed tasks (Docker):"
	@echo "  make seed-init-docker              # run seeder with example data via container HTTP"
	@echo "  make seed-clear-docker             # clear DB in Docker"
	@echo ""
	@echo "Ngrok shortcuts:"
	@echo "  make docker-up-ngrok NGROK=your-subdomain.ngrok-free.app"
	@echo "  echo your-subdomain.ngrok-free.app > .ngrok-host  # auto-used next runs"
	@echo ""

# -------- Full Docker dev --------
.PHONY: docker-build docker-up docker-down docker-down-all docker-logs docker-health
docker-build:
	$(COMPOSE) $(COMPOSE_FILES) $(PROFILE_FULL) build

docker-up:
	@echo ">> Compose files: $(COMPOSE_FILES)"
	@if [ -n "$(NGROK)" ]; then echo ">> Using ngrok override with NGROK=$(NGROK)"; fi
	# keep Docker's nice progress output:
	NGROK="$(NGROK)" $(COMPOSE) $(COMPOSE_FILES) $(PROFILE_FULL) up -d

docker-down:
	$(COMPOSE) $(COMPOSE_FILES) $(PROFILE_FULL) down

docker-down-all:
	$(COMPOSE) $(COMPOSE_FILES) $(PROFILE_FULL) down -v

docker-logs:
	$(COMPOSE) $(COMPOSE_FILES) logs -f backend

docker-health:
	$(COMPOSE) $(COMPOSE_FILES) exec -T backend curl -fsS http://localhost:8000/health || true

# -------- Seed tasks (Docker) --------
define SEED_DOCKER_HTTP
	@echo ">> Ensuring backend is up…"; \
	$(COMPOSE) $(COMPOSE_FILES) up -d backend; \
	echo ">> Seeding $(1) inside Docker via API at http://backend:8000"; \
	$(COMPOSE) $(COMPOSE_FILES) run --rm \
	  -e API_BASE_URL=http://backend:8000 \
	  -e MONGODB_URI="$(DB_URI_DOCKER)" \
	  backend pdm run python -m dpp.seed $(1)
endef

.PHONY: seed-init-docker seed-clear-docker
seed-init-docker:   ; $(call SEED_DOCKER_HTTP,init)
seed-clear-docker:  ; $(call SEED_DOCKER_HTTP,clear)

# -------- Ngrok convenience --------
.PHONY: docker-up-ngrok
docker-up-ngrok:
	# Pass NGROK via make var (portable)
	$(MAKE) docker-up NGROK=$(NGROK)
