# AI Resume Screening Platform

Progress so far: **Phase 2** (Environment Setup) + **Phase 3** (Authentication).

This stands up the full local dev environment — FastAPI, PostgreSQL, Redis,
and a React (Vite + TS + Tailwind) frontend, all orchestrated via Docker
Compose — plus JWT-based authentication with role-based access control.

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

## Authentication (Phase 3)

The API now has JWT-based auth with three roles: `admin`, `recruiter`, `viewer`.
The **first account ever registered becomes admin automatically** (bootstrap);
every registration after that is restricted to `recruiter`/`viewer` — requesting
`admin` returns `403 Forbidden`.

### 1. Apply the database migration (creates the `users` table)

```bash
make migrate
```

### 2. Register the first (admin) user

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"founder@company.com","password":"supersecret1","full_name":"Founder"}'
```

### 3. Log in (returns a JWT)

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=founder@company.com&password=supersecret1"
```

### 4. Call a protected route

```bash
TOKEN="<paste access_token from step 3>"
curl -s http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer $TOKEN"
```

You can also use Swagger UI's **Authorize** button at http://localhost:8000/docs —
paste your email/password there and it calls `/login` for you automatically.

### Creating new migrations

Whenever you add/change a model under `app/infrastructure/db/models/`:

```bash
make migration name="add jobs table"   # generates a new versions/*.py file
make migrate                            # applies it
```

## Running Tests

```bash
make test    # runs the full pytest suite (unit + API) inside the backend container
make lint    # runs ruff over app/ and tests/
```

Tests run against an in-memory SQLite database (not the real Postgres), so
`make test` works even before `make migrate` has been run.

