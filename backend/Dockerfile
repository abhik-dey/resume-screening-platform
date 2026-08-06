FROM python:3.12-slim

WORKDIR /app

# System deps for asyncpg build + healthcheck tooling
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# requirements.lock is copied too, because requirements-dev.txt now layers
# on top of it (-r requirements.lock). Omitting it breaks the dev image the
# same way Phase 3 broke on a missing alembic.ini: the file exists on the
# host, so it works locally, and the container has never seen it.
COPY requirements.txt requirements-dev.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini pytest.ini pyproject.toml ./
COPY tests ./tests

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
