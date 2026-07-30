.PHONY: up down logs ps backend-shell frontend-shell health clean

COMPOSE = docker compose -f infra/docker-compose.yml

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

backend-shell:
	$(COMPOSE) exec backend /bin/bash

frontend-shell:
	$(COMPOSE) exec frontend /bin/sh

health:
	curl -s http://localhost:8000/api/health | python3 -m json.tool

clean:
	$(COMPOSE) down -v --remove-orphans
