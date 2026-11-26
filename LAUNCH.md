# Production Launch Checklist

This document details the mandatory steps, verification gates, and procedures required to deploy the E-Commerce AI Customer Support Platform into production.

---

## 1. Environment and Secrets Configuration

- [ ] **Database credentials**:
  - Replace development passwords in `.env` with high-entropy credentials stored in a secrets manager (e.g., AWS Secrets Manager, Google Secret Manager, HashiCorp Vault).
  - Ensure Postgres is bound to private VPC subnets only, never exposed to public internet.
- [ ] **JWT secret key**:
  - Generate a secure 256-bit cryptographic secret (`openssl rand -hex 32`) for `SECRET_KEY`.
  - Rotate the development key before launch.
- [ ] **AI model credentials**:
  - Provision production Gemini API key and configure quota alerts.
  - Set `AGENT_MODEL=gemini-2.5-flash` or approved production model identifier.
- [ ] **Environment flags**:
  - Set `APP_ENV=production`.
  - Set `DEBUG=false`.
  - Set `VITE_DEMO_MODE=false` in frontend environment so sample banners are disabled.
  - Set `VITE_API_BASE_URL` to the public production API URL (e.g., `https://api.example.com`).

---

## 2. Custom Domain, DNS, and TLS Setup

- [ ] **DNS records**:
  - Configure `A` and `AAAA` records pointing frontend to edge CDN / host.
  - Configure API domain (e.g., `api.example.com`) pointing to load balancer / reverse proxy.
- [ ] **TLS / SSL certificates**:
  - Provision automated Let's Encrypt or ACM TLS certificates for all domains.
  - Enforce HTTPS redirect (HTTP 301 to HTTPS).
  - Configure HTTP Strict Transport Security (`HSTS`: `max-age=31536000; includeSubDomains; preload`).
- [ ] **Security headers**:
  - `Content-Security-Policy`: Restrict script and style sources to self and trusted origins.
  - `X-Content-Type-Options: nosniff`.
  - `X-Frame-Options: DENY`.
  - `Referrer-Policy: strict-origin-when-cross-origin`.

---

## 3. Database and Migrations

- [ ] **Migration execution**:
  - Run database migration pipeline: `alembic upgrade head`.
  - Verify all tables, partial unique indexes (such as `uq_refunds_one_active_per_order`), and constraints exist.
- [ ] **Connection pooling**:
  - Configure PgBouncer or connection pool sizing in `db.py` to match database CPU and memory capacity.
- [ ] **Backups and point-in-time recovery**:
  - Enable daily automated snapshots with 30-day retention.
  - Enable WAL archiving for Point-In-Time Recovery (PITR).
  - Perform test restore drill on staging database.

---

## 4. Backend Service Health and Monitoring

- [ ] **Process supervision**:
  - Deploy FastAPI using Gunicorn with Uvicorn workers (`uvicorn.workers.UvicornWorker`).
  - Configure systemd or container orchestrator with restart policy `unless-stopped`.
- [ ] **Health checks**:
  - Configure load balancer probe to query `GET /health` every 10 seconds.
  - Confirm `/health` validates DB connectivity and reports `status: "ok"`.
- [ ] **Structured logging**:
  - Validate JSON logs stream to stdout without sensitive tokens or passwords.
  - Ingest stdout into log aggregation system (e.g. CloudWatch, Datadog, Grafana Loki).
  - Configure alerts on `5xx` error spikes, failed payment attempts, and database query latency.

---

## 5. AI Support Safety and Escalation Guardrails

- [ ] **Deterministic tool authority**:
  - Verify that the LLM cannot disburse funds or bypass policy independently.
  - Verify all financial actions execute through `services/refunds.py`.
- [ ] **Escalation threshold**:
  - Confirm `AUTO_REFUND_LIMIT` is set to 5000.00 INR (or local currency limit).
  - Ensure amounts above threshold escalate to human staff.
- [ ] **Static policy alignment**:
  - Review `backend/app/agent/policy.md` against company policies.
  - Verify return window (30 days from delivery) and non-returnable categories (grocery).
- [ ] **Customer disclosure notice**:
  - Confirm the UI displays "AI assistant" labels and accuracy notices on automated messages.

---

## 6. Legal and Compliance Sign-Off

- [ ] **Legal counsel review**:
  - Obtain formal lawyer sign-off on `/terms` and `/privacy` text.
  - Remove draft warning banner in `Privacy.jsx` and `Terms.jsx` once approved.
- [ ] **Company and contact details**:
  - Verify legal entity name, postal address, and contact email addresses in `src/config/legal.js`.
- [ ] **Data retention schedule**:
  - Confirm 180-day retention schedule for customer support chat transcripts and audit events.
  - Ensure compliance with applicable personal data protection laws.

---

## 7. Frontend Assets and Quality Gate

- [ ] **Asset verification**:
  - Verify SVG and PNG favicons load properly across Chrome, Safari, Firefox, and mobile browsers.
  - Confirm `apple-touch-icon.png`, `icon-192.png`, and `icon-512.png` are referenced in `site.webmanifest`.
  - Confirm theme-color is set to `#0f766e` in `index.html`.
- [ ] **Responsive layouts**:
  - Test UI on mobile (375px width) and desktop (1280px width).
  - Verify no text overflow, horizontal scroll, or broken alignment.
- [ ] **Design compliance**:
  - Zero emojis across UI, documentation, and error messages.
  - Zero em dashes or en dashes (use standard punctuation).
  - Max `rounded-md` (6px) on cards, buttons, and inputs.
  - No decorative gradients or purple/violet tones.

---

## 8. Pre-Launch Automated Verification Commands

Execute the following commands before cutting any release tag:

```bash
# 1. Run all backend tests
pytest backend/tests

# 2. Run frontend syntax lint
npm --prefix frontend run lint

# 3. Run frontend unit tests
npm --prefix frontend test

# 4. Run automated design and launch check with production build
npm --prefix frontend run build
```

Every command must pass with exit code `0`.
