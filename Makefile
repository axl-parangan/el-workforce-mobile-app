COMPOSE := docker compose
RUN := $(COMPOSE) run --rm backend
MOBILE := cd mobile &&

.DEFAULT_GOAL := help
.PHONY: help env build up down logs ps shell bash dbshell migrate makemigrations \
	createsuperuser test lint format check mobile-install mobile-start mobile-check

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

env: ## Create .env from .env.example (does not overwrite)
	@test -f .env && echo ".env already exists" || (cp .env.example .env && echo "Created .env")

# --- Backend (Docker) ------------------------------------------------------------

build: ## Build the backend image
	$(COMPOSE) build

up: ## Start db + backend in the background
	$(COMPOSE) up -d

down: ## Stop containers (keeps the database volume)
	$(COMPOSE) down

logs: ## Follow container logs
	$(COMPOSE) logs -f

ps: ## Show container status
	$(COMPOSE) ps

shell: ## Django shell
	$(RUN) python manage.py shell

bash: ## Bash shell in the backend container
	$(RUN) bash

dbshell: ## psql shell
	$(COMPOSE) exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

migrate: ## Apply database migrations
	$(RUN) python manage.py migrate

makemigrations: ## Create new migrations
	$(RUN) python manage.py makemigrations

createsuperuser: ## Create an admin user
	$(RUN) python manage.py createsuperuser

test: ## Run backend tests (pass args with ARGS="-k health")
	$(RUN) pytest $(ARGS)

lint: ## Lint backend with ruff
	$(RUN) ruff check .
	$(RUN) ruff format --check .

format: ## Format backend with ruff
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

check: ## Django system checks + missing-migration check
	$(RUN) python manage.py check
	$(RUN) python manage.py makemigrations --check --dry-run

# --- Mobile (runs on the host) ---------------------------------------------------

mobile-install: ## Install mobile dependencies
	$(MOBILE) npm ci

mobile-start: ## Start the Expo dev server
	$(MOBILE) npx expo start

mobile-check: ## Typecheck, lint and format-check the mobile app
	$(MOBILE) npm run typecheck && npm run lint && npm run format:check
