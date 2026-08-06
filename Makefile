.PHONY: up down logs ps backend-shell frontend-shell health clean \
	prod-check prod-build prod-up prod-down prod-logs prod-ps prod-migrate prod-grafana \
	k8s-validate k8s-secrets k8s-apply k8s-migrate k8s-status k8s-delete

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

migrate:
	$(COMPOSE) exec backend alembic upgrade head

# Usage: make migration name="add jobs table"
migration:
	$(COMPOSE) exec backend alembic revision --autogenerate -m "$(name)"

test:
	$(COMPOSE) exec backend sh -c "pip install -q -r requirements-dev.txt && pytest -v"

lint:
	$(COMPOSE) exec backend sh -c "pip install -q ruff && ruff check app tests"

clean:
	$(COMPOSE) down -v --remove-orphans

# --- Production (Phase 21) ---
# Deliberately separate targets against a separate compose file, so a
# production command can never be run by muscle memory for a dev one.

PROD_COMPOSE = docker compose -f infra/docker-compose.prod.yml

prod-check:
	@test -f backend/.env.prod || (echo "Missing backend/.env.prod — copy backend/.env.prod.example and fill it in" && exit 1)
	@! grep -q "CHANGE_ME" backend/.env.prod || (echo "backend/.env.prod still contains CHANGE_ME placeholders — fill them in before deploying" && exit 1)
	@# Compose resolves ${VAR} interpolation from a .env beside the compose
	@# file — NOT from a service's env_file. Symlinking means one file
	@# serves both purposes and the two can never drift apart.
	@ln -sf ../backend/.env.prod infra/.env
	@grep -q "^POSTGRES_PASSWORD=." infra/.env || (echo "POSTGRES_PASSWORD is empty in backend/.env.prod" && exit 1)
	@grep -q "^GRAFANA_PASSWORD=." infra/.env || (echo "GRAFANA_PASSWORD is empty in backend/.env.prod" && exit 1)
	@grep -q "^JWT_SECRET_KEY=." infra/.env || (echo "JWT_SECRET_KEY is empty in backend/.env.prod" && exit 1)
	@echo "Production env looks configured."

prod-build: prod-check
	$(PROD_COMPOSE) build

prod-up: prod-check
	$(PROD_COMPOSE) up -d --build

prod-down:
	$(PROD_COMPOSE) down

prod-logs:
	$(PROD_COMPOSE) logs -f

prod-ps:
	$(PROD_COMPOSE) ps

prod-migrate:
	$(PROD_COMPOSE) exec backend alembic upgrade head

# Grafana is bound to loopback only, so it is reached through an SSH
# tunnel rather than being published. Printed as a reminder of that.
prod-grafana:
	@echo "Grafana is bound to 127.0.0.1 only. From a remote host:"
	@echo "  ssh -L 3000:localhost:3000 user@your-server"
	@echo "Then open http://localhost:3000"

# --- Kubernetes (Phase 22) ---

K8S_NS = resume-screening

# Schema validation plus assertions on the security properties the
# manifests claim. Runs without a cluster, so it belongs in CI.
k8s-validate:
	python3 k8s/validate.py

k8s-secrets:
	./k8s/generate-secrets.sh

k8s-apply: k8s-validate
	@test -f k8s/secret.generated.yaml || (echo "Run 'make k8s-secrets' first" && exit 1)
	kubectl apply -f k8s/base/00-namespace.yaml
	kubectl apply -f k8s/secret.generated.yaml
	kubectl apply -f k8s/base/
	@echo "Applied. Run 'make k8s-migrate' before the backend serves traffic."

# Migrations run as a Job rather than an initContainer: with 3 replicas an
# initContainer means three pods racing, and a bad migration crash-loops
# every replica instead of failing once, visibly.
k8s-migrate:
	kubectl delete job db-migrate -n $(K8S_NS) --ignore-not-found
	kubectl apply -f k8s/base/10-migration-job.yaml
	kubectl wait --for=condition=complete --timeout=300s job/db-migrate -n $(K8S_NS)
	kubectl logs job/db-migrate -n $(K8S_NS)

k8s-status:
	kubectl get pods,svc,ingress,hpa,pvc -n $(K8S_NS)

k8s-delete:
	@echo "This deletes the namespace AND its PersistentVolumeClaims."
	@echo "All candidate data and the vector index will be lost."
	@read -p "Type the namespace name to confirm: " c && [ "$$c" = "$(K8S_NS)" ]
	kubectl delete namespace $(K8S_NS)
