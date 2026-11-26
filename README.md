# E-Commerce AI Customer Support Platform

Foundation and infrastructure skeleton (Part 1) for an enterprise e-commerce AI customer support platform.

## Architecture & Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, psycopg 3, pydantic-settings, structlog, pytest, httpx
- **Frontend**: React + Vite, plain JavaScript (JSX, no TypeScript)
- **Database**: PostgreSQL 16 via Docker Compose
- **Logging**: Structured JSON output directly to `stdout` with sensitive field masking and request ID tracking

---

## Directory Layout

```text
/
├── backend/
│   ├── alembic/                # Alembic database migrations configuration
│   ├── alembic.ini             # Alembic INI connecting to DATABASE_URL
│   ├── app/
│   │   ├── agent/              # AI agent modules (empty __init__.py)
│   │   ├── api/                # API route handlers (health.py)
│   │   ├── core/               # config, db, logging, middleware, errors
│   │   ├── models/             # SQLAlchemy ORM models (empty __init__.py)
│   │   ├── schemas/            # Pydantic schemas (error.py)
│   │   ├── services/           # Domain business logic (empty __init__.py)
│   │   └── main.py             # FastAPI app factory and router wiring
│   ├── tests/                  # Pytest test suite (conftest.py, test_health.py)
│   ├── Dockerfile              # Python 3.12 slim container definition
│   └── requirements.txt        # Production & testing dependencies
├── frontend/                   # React + Vite JavaScript application scaffold
├── docker-compose.yml          # PostgreSQL 16 (with healthcheck) + Backend
├── .env.example                # Configuration template (placeholders only)
├── .gitignore                  # Git ignore rules (.env, node_modules, .venv)
└── README.md                   # Setup and operational instructions
```

---

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) & Docker Compose
- [Python 3.12+](https://www.python.org/) (for local backend development)
- [Node.js 18+](https://nodejs.org/) & npm (for local frontend development)

---

### 1. Quick Start (Docker Compose)

Start the PostgreSQL 16 database and FastAPI backend with a single command:

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Start PostgreSQL and Backend services
docker compose up --build
```

The backend automatically waits for PostgreSQL to pass its healthcheck (`pg_isready`) before launching.

- **Liveness Probe**: [http://localhost:8000/health](http://localhost:8000/health) (returns `{"status": "ok"}`)
- **Readiness Probe**: [http://localhost:8000/health/db](http://localhost:8000/health/db) (returns `{"status": "ok", "database": "connected"}`)
- **OpenAPI Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative Docs**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

### 2. Running Migrations

Database migrations are powered by Alembic and read `DATABASE_URL` dynamically from the application settings:

```bash
# Using local virtualenv:
cd backend
source .venv/bin/activate  # or activate your venv
alembic upgrade head

# Generate a new migration:
alembic revision --autogenerate -m "create_initial_tables"

# Or run migrations inside Docker:
docker compose exec backend alembic upgrade head
```

---

### 3. Running Backend Tests

Tests run using `pytest` and an in-memory SQLite database (`StaticPool`) so tests execute rapidly without requiring an active PostgreSQL container:

```bash
# From repository root or backend directory:
cd backend
source .venv/bin/activate
pip install -r requirements.txt
pytest -v
```

The test suite validates:
- `GET /health` returns status code `200` with `{"status": "ok"}`
- `GET /health/db` returns status code `200` with database connectivity
- `GET /health/db` returns status code `503` in the standard error shape on connection failure
- Unknown routes return status code `404` adhering to the uniform error schema
- Validation errors return status code `422` with a valid `request_id` and error details
- `X-Request-ID` propagation across all responses

---

### 4. Running the Frontend

The frontend is a lightweight React + Vite scaffold using plain JavaScript (JSX):

```bash
cd frontend
npm install
npm run dev
```

Visit [http://localhost:5173](http://localhost:5173) to view the development server.

---

## Error Response Standard

All API errors return a standard JSON envelope with a tracking `request_id`:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": null,
    "request_id": "8bbbb949-a681-4228-91c6-2c5ea0244799"
  }
}
```

The `X-Request-ID` HTTP header is also returned in every response.

---

## Structured Logging & Masking

Logs are emitted in structured JSON format exclusively to `stdout`. The custom structlog processor automatically redacts values for keys named:
- `password`
- `token`
- `authorization`
- `email`
- `content`
