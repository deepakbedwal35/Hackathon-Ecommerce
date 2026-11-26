# E-Commerce AI Customer Support Platform

Foundation and infrastructure skeleton for an enterprise e-commerce AI customer support platform.

## Architecture & Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, psycopg 3, pydantic-settings, structlog, pytest, httpx, argon2-cffi, pyjwt
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
│   │   ├── api/                # API routers (health.py, auth.py)
│   │   ├── core/               # config, db, logging, middleware, errors, security, deps, rate_limit
│   │   ├── models/             # SQLAlchemy ORM models (users, orders, tickets, etc.)
│   │   ├── schemas/            # Pydantic schemas (error.py, auth.py)
│   │   ├── services/           # Domain business logic & ownership helpers (access.py)
│   │   └── main.py             # FastAPI app factory and router wiring
│   ├── scripts/                # Database utility scripts (seed.py)
│   ├── tests/                  # Pytest suite (conftest.py, test_health.py, test_schema.py, test_seed.py, test_auth.py, test_access.py)
│   ├── Dockerfile              # Python 3.12 slim container definition
│   └── requirements.txt        # Production & testing dependencies
├── frontend/                   # React + Vite JavaScript application scaffold
├── docs/                       # Architecture & schema documentation (schema.md)
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

Start the PostgreSQL 16 database and FastAPI backend:

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Start PostgreSQL and Backend services
docker compose up -d db
docker compose up --build backend
```

- **Liveness Probe**: [http://localhost:8000/health](http://localhost:8000/health) (returns `{"status": "ok"}`)
- **Readiness Probe**: [http://localhost:8000/health/db](http://localhost:8000/health/db) (returns `{"status": "ok", "database": "connected"}`)
- **OpenAPI Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative Docs**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

### 2. Running Migrations & Seeding

Database migrations use Alembic, reading `DATABASE_URL` dynamically from the application settings:

```bash
cd backend
source .venv/bin/activate

# Apply migrations
alembic upgrade head

# Seed initial users, orders, items, refunds, and tickets
python -m scripts.seed

# Wipe and re-seed from scratch
python -m scripts.seed --reset
```

---

### 3. Authentication & RBAC

The API uses stateless HS256 JWT tokens with database-backed user validation on every request.

#### Seeded Accounts

All accounts share the default demo password: `LocalDevDemo123!` (or value from `SEED_PASSWORD` env var):

| Role | Email | Capabilities |
| :--- | :--- | :--- |
| **Customer 1** | `customer1@example.com` | Own orders & tickets only |
| **Customer 2** | `customer2@example.com` | Own orders & tickets only |
| **Support Agent** | `agent1@example.com` | View all customer tickets & orders, request info, add internal notes |
| **System Admin** | `admin1@example.com` | Full staff permissions plus approve/reject refunds and reassign escalations |

#### Authorizing in Swagger UI (`/docs`)

1. Open [http://localhost:8000/docs](http://localhost:8000/docs)
2. Send a `POST /api/v1/auth/login` request with e.g. `customer1@example.com` and `LocalDevDemo123!`.
3. Copy the returned `access_token` string.
4. Click the green **Authorize** button in the top right of the Swagger UI.
5. In the **HTTPBearer (http, Bearer)** input box, paste the token and click **Authorize**.
6. All subsequent requests (e.g. `GET /api/v1/auth/me`) will automatically include the `Authorization: Bearer <token>` header.

---

### 4. Running Backend Tests

Tests run against a dedicated `support_test` database on Docker Postgres (never modifying dev data):

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
pytest -v
```

The test suite validates:
- Liveness & database readiness health probes (`/health`, `/health/db`)
- Schema constraints (case-insensitive unique email, 1 active refund per order, idempotency key, numeric money check)
- Seed script idempotency & relative dates
- Authentication flows (`/register`, `/login`, `/me`, `/logout`)
- Constant-time dummy verification on unknown emails
- In-memory rate limiting (blocks 6th failed attempt in 60s with `Retry-After`)
- Role-based access control (`require_customer`, `require_staff`)
- Ownership checks (`get_order_for_user`, `get_ticket_for_user`) returning identical 404s for cross-customer and nonexistent records

---

### 5. Running the Frontend

```bash
cd frontend
npm install
npm run dev
```

Visit [http://localhost:5173](http://localhost:5173) to view the development server.

---

## API Endpoints Reference

### Public & Authentication (`/api/v1/auth`)
| Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/register` | Public | Register new customer account (role=customer) |
| `POST` | `/api/v1/auth/login` | Public | Authenticate user & issue JWT bearer token |
| `GET` | `/api/v1/auth/me` | Authenticated | Retrieve profile of authenticated user |
| `POST` | `/api/v1/auth/logout` | Authenticated | Stateless token logout audit |

### Customer APIs (`/api/v1`)
| Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/refunds` | Customer | Request refund with policy evaluation & mock rails |
| `GET` | `/api/v1/refunds` | Customer | List authenticated customer's own refunds |
| `GET` | `/api/v1/refunds/{id}` | Customer | Retrieve specific customer refund with progress |
| `GET` | `/api/v1/tickets` | Customer | List customer support tickets with `review_status` |
| `GET` | `/api/v1/tickets/{id}` | Customer | Get customer ticket detail (notes excluded) |
| `GET` | `/api/v1/tickets/{id}/messages` | Customer | List customer-visible messages on ticket |
| `POST` | `/api/v1/tickets/{id}/messages` | Customer | Reply to ticket; auto-reopens `more_info_requested` |

### Public Meta Configuration (`/api/v1/meta`)
| Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/meta/enums` | Public | Single source of truth for ticket, order, refund, and escalation enums |
| `GET` | `/api/v1/meta/config` | Public | Public policy configuration (`refund_review_mode`, `auto_refund_limit`, `return_window_days`) |

### Staff Operations & Dashboard (`/api/v1/staff`)
| Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/staff/overview` | Staff | Ticket counts by status, queue depths, pending total, and top 5 queues |
| `GET` | `/api/v1/staff/tickets` | Staff | Paginated ticket queue with SLA sort & search |
| `GET` | `/api/v1/staff/tickets/{id}` | Staff | Full ticket context (order, refunds, notes, escalations, `allowed_transitions`) |
| `PATCH` | `/api/v1/staff/tickets/{id}` | Staff | Transition ticket status/priority with strict invariants |
| `GET` | `/api/v1/staff/tickets/{id}/messages` | Staff | List all messages on ticket with optional `after` timestamp cursor |
| `POST` | `/api/v1/staff/tickets/{id}/messages`| Staff | Post customer-visible staff reply on ticket |
| `GET` | `/api/v1/staff/tickets/{id}/notes` | Staff | List internal, staff-only notes on ticket |
| `POST` | `/api/v1/staff/tickets/{id}/notes` | Staff | Append internal note to ticket (audit tracked) |
| `GET` | `/api/v1/staff/escalations` | Staff | Paginated escalation queue with SLA priority sort |
| `GET` | `/api/v1/staff/escalations/{id}` | Staff | Full escalation context with passed verification checks |
| `POST` | `/api/v1/staff/escalations/{id}/assign` | Staff | Assign escalation (agent to self, admin to any staff) |
| `POST` | `/api/v1/staff/escalations/{id}/decision` | Staff | Approve/reject (admin only) or request info (agent or admin) |

---

## Refund Review Modes & Role Permissions

Configured via `REFUND_REVIEW_MODE`:
- `above_limit` (default): Eligible refunds at or below `AUTO_REFUND_LIMIT` (5,000.00 INR) auto-process; amounts strictly above escalate for admin review.
- `all`: Every policy-eligible refund request escalates to human review before any money moves; expired or non-returnable orders still reject immediately without escalating.

| Action | Customer | Support Agent | Admin |
| :--- | :---: | :---: | :---: |
| View all customer tickets & escalations | No (403) | Yes | Yes |
| Reply to tickets & add internal notes | Own tickets only | Yes | Yes |
| Request more info on an escalation | No (403) | Yes | Yes |
| Assign escalation | No (403) | Self only | Any staff user |
| Approve or reject escalated refund | No (403) | No (403) | Yes |

---

## Error Response Standard

All API errors return a standard JSON envelope with a tracking `request_id`:

```json
{
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "Invalid email or password.",
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
