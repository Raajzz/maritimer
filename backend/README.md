# Maritimer backend

Django 5.2 + DRF + PostgreSQL 16. Design: `../ARCHITECTURE.md`, `../SCHEMA.md`, `../API.md`, `../STATE_MACHINES.md`.

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env            # optional; dev defaults work with a local Postgres
# macOS: brew install pango postgresql@16 && export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo
.venv/bin/python manage.py runserver
```

Or with Docker from the repo root: `docker compose up --build`.

## Commands

| Command | Purpose |
|---|---|
| `manage.py bootstrap_admin --email you@gmail.com` | Create the first Admin (links on first Google sign-in) |
| `manage.py seed_masterdata` | Countries, currencies, locations, ports, service categories, cargo types, request policies (idempotent; safe in prod) |
| `manage.py seed_demo [--owner-email … --agent-email … --merchant-emails a,b,c --admin-email …]` | Demo orgs, users and port calls at every stage |
| `manage.py expire_requests` | Expire overdue PENDING requests (schedule it) |
| `pytest` | Test suite |

## Layout

`apps/<context>/` holds `models.py`, `transitions.py` (state tables), `services.py` (every write: permission check → lock → transition → audit, in one transaction), `views.py`, plus `selectors.py` where scoping lives. Routes are in `config/api_urls.py`.

## Auth in development

With `AUTH_DEV_TOKENS=true` (dev/test settings only) any request may use `Authorization: Bearer dev:<email>`.
Production settings force this off and require a Firebase ID token.
