# AI Resume Screening Platform — Phase 2: Environment Setup

This phase stands up the full local dev environment: FastAPI, PostgreSQL,
Redis, and a React (Vite + TS + Tailwind) frontend, all orchestrated via
Docker Compose. No business logic yet — this is a connectivity smoke test.

## Prerequisites

- Docker & Docker Compose v2
- (Optional, for running things outside Docker) Python 3.12+, Node 20+

## Quick Start

```bash
# 1. Copy the backend env template
cp backend/.env.example backend/.env

# 2. Build and start everything
make up

# 3. Check that all services are healthy
make health
```

Expected output from `make health`:

```json
{
    "status": "ok",
    "postgres": {"status": "ok", "detail": null},
    "redis": {"status": "ok", "detail": null}
}
```

Then open:
- Frontend: http://localhost:5173
- Backend docs (Swagger UI): http://localhost:8000/docs
- Backend health endpoint: http://localhost:8000/api/health

## Common Commands

| Command | Purpose |
|---|---|
| `make up` | Build images and start all services in the background |
| `make down` | Stop all services |
| `make logs` | Tail logs from every service |
| `make ps` | List running containers |
| `make backend-shell` | Open a shell inside the backend container |
| `make clean` | Stop everything and remove volumes (wipes Postgres data) |

## Running the Backend Without Docker (optional)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Note: without Docker, `POSTGRES_HOST`/`REDIS_HOST` in `.env` must point to
`localhost` instead of the Docker service names `postgres`/`redis`.

## Running the Frontend Without Docker (optional)

```bash
cd frontend
npm install
npm run dev
```
