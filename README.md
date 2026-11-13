# Maritimer — port-call management

Shipowners, port agents and local vendors run a port call end to end in one place:

- Discover an agent and request a port call.
- Agree the PDA (proforma estimate) and record the advance.
- Source vendors, collect INR invoices and build the FDA (final account) in USD with recorded FX rates.
- Settle line-item disputes and close the settlement.

Every step is audited, and the PDA, FDA and settlement statement are generated as PDFs.

| Role | Can do |
|---|---|
| Owner | Find agents by location/port (rating, name, ID), send requests, approve PDAs, record advances and balances, dispute FDA lines, rate agents |
| Port agent | Pipeline of all calls across owners, PDA/FDA editing, vendor requests, invoice review, FX rates, dispute resolution, settlement |
| Merchant | Accept service requests, negotiate in chat, issue invoices with files, see payments |
| Admin | Approve users and documents, create organizations directly, master data, request policies, audit log |

## Repository

```
ARCHITECTURE.md      components, service-layer rules, auth, money/FX, PDF, design tokens, deployment decision
SCHEMA.md            PostgreSQL schema (ER diagram, every table, decisions D1–D16, DB invariants)
API.md               REST API per role
STATE_MACHINES.md    request, port call, PDA, FDA, invoice, payment, settlement, dispute, onboarding
PROGRESS.md          status, clarifications made during implementation, follow-ups
DEPLOY.md            step-by-step production deployment (Render + Neon + Vercel + Cloudflare R2 + Firebase)
WALKTHROUGH.md       end-to-end demo checklist for every role
backend/             Django 5.2 + DRF + PostgreSQL 16 + WeasyPrint
frontend/            React 18 + Vite + React Router + Firebase Auth
docker-compose.yml   local Postgres + API + frontend
render.yaml          Render blueprint for the API
```

## Architecture in one picture

```
React SPA (Vercel) ──Firebase ID token──▶ Django REST API (Render, Docker)
  Firebase Auth (Google)                    ├─ verifies token (firebase-admin) → local User/role/approval
                                            ├─ services.py: permission → row lock → state machine → audit, in one transaction
                                            ├─ WeasyPrint PDFs, cached per document status
                                            ├─ PostgreSQL 16 (Neon): NUMERIC money, CHECK/partial-unique invariants
                                            └─ S3-compatible storage (Cloudflare R2): invoices, documents, PDFs
```

Key rules, detailed in ARCHITECTURE.md:
- **Approval is enforced on the server.** Only approved users with an approved organization can call anything beyond auth and onboarding.
- **Money is never a float.** Amounts are `NUMERIC(18,2)` with a currency on every row and travel as JSON strings. Each converted line stores the FX rate row and the exact rate applied, so FDAs are reproducible.
- **Every state change goes through one service function.** It checks permissions, locks the row, validates against a transition table that a test compares to STATE_MACHINES.md, and writes an append-only audit entry.
- **Request directions are configuration.** Which role may send which request to which role is a policy table, so opening a new direction needs no schema change.

## Run locally

### Option A — Docker

```bash
docker compose up --build
docker compose exec backend python manage.py seed_demo
open http://localhost:5173          # use the "Development sign-in" buttons
```

### Option B — native (macOS shown)

```bash
brew install postgresql@16 pango && brew services start postgresql@16
psql -d postgres -c "create role maritimer login superuser password 'maritimer'" -c "create database maritimer owner maritimer"

cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib     # lets WeasyPrint find pango on macOS
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo
.venv/bin/python manage.py runserver                    # http://localhost:8000/api/v1/health

cd ../frontend
cp .env.example .env.local                              # VITE_DEV_AUTH=true for the demo sign-in picker
npm install && npm run dev                              # http://localhost:5173
```

Local development accepts `Authorization: Bearer dev:<email>` so you can switch roles without Google accounts. Production settings always disable it.

### Demo accounts (`seed_demo`)

| Role | Email |
|---|---|
| Admin | admin@maritimer.test |
| Owner | owner.demo@maritimer.test |
| Port agent | agent.demo@maritimer.test |
| Merchant (pilots/tugs) | pilots.demo@maritimer.test |
| Merchant (supplies) | supplies.demo@maritimer.test |
| Merchant (customs) | customs.demo@maritimer.test |

In production, pass one real Google account per role: `seed_demo --owner-email … --agent-email …`. Google signs in the base account, so Gmail `+` aliases don't count as separate accounts. See DEPLOY.md §6.

## Tests

```bash
cd backend && .venv/bin/pytest          # 96 tests: permissions, state machines vs the doc, money/FX, settlement, disputes, invariants, API flow, PDFs
cd frontend && npm test                 # formatting helpers
```

## Management commands

| Command | Purpose |
|---|---|
| `bootstrap_admin --email you@gmail.com` | Create the first Admin (links on first Google sign-in) |
| `seed_masterdata` | Countries, currencies, locations, ports, services, cargo types, request policies (idempotent) |
| `seed_demo [--owner-email … --agent-email … --merchant-emails a,b,c --admin-email …]` | Demo data at every pipeline stage |
| `expire_requests` | Expire overdue pending requests (schedule it) |

## Deploy

See **DEPLOY.md**: Render (API, Docker) + Neon (Postgres) + Vercel (frontend) + Cloudflare R2 (files) + Firebase (Google sign-in). All of them have a free tier.
