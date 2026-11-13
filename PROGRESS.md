# PROGRESS.md

Single source of truth for where the project is. Update at every model switch.

## Status

| Phase | Owner model | State |
|---|---|---|
| 1 — Architecture, schema, API, state machines | Fable | **DONE** — approved by the user on 2026-11-13 |
| 2 — Backend (models, migrations, services, APIs, auth, permissions, PDF, tests, seed) | Opus | **DONE** — 96 tests passing |
| 3 — Frontend (tokens, layout, role routing, all flows, responsive) | Opus | **DONE** — build passes; UI flows scripted in a headless browser at 1280px and 390px |
| 4 — Deployment configs, docs, E2E walkthrough checklist | Opus | **DONE** — render.yaml, vercel.json, docker-compose, DEPLOY.md, WALKTHROUGH.md, README.md. Not yet deployed (needs your accounts) |

## Files that define the design

- `ARCHITECTURE.md` — components, service-layer rules, auth pipeline, money/FX rules, PDF, storage, audit, frontend structure, design brief + tokens, deployment decision (Render + Neon + Vercel + R2).
- `SCHEMA.md` — ER diagram, every table/column/constraint/index, decisions D1–D16, DB-enforced invariants.
- `API.md` — every endpoint per role, conventions, payloads, role matrix.
- `STATE_MACHINES.md` — user onboarding, request, port call, PDA, FDA, vendor invoice, payment, settlement, dispute; cross-machine guards to test.

## Phase 2 — what was built (`backend/`)

| Area | Where |
|---|---|
| Settings (base/dev/test/prod), env-driven; storage switch local ↔ S3/R2 | `config/settings/*.py`, `backend/.env.example` |
| All tables from SCHEMA.md with every CHECK / UNIQUE / partial index; citext; per-year reference sequences | `apps/*/models.py`, `apps/*/migrations/`, `apps/core/references.py` |
| Audit log (append-only in code; `core.0099` revokes UPDATE/DELETE/TRUNCATE in prod when `AUDIT_LOG_REVOKE_ROLE` is set) | `apps/core/models.py`, `apps/core/audit.py` |
| Firebase ID-token auth → local User; pre-provisioned users link on first verified sign-in | `apps/core/authentication.py` |
| Permission layers: `IsApproved` on every endpoint except auth/onboarding, role gates, org-scoped selectors (404 outside scope) | `apps/core/permissions.py`, `apps/portcalls/selectors.py` |
| State machines as tables mirroring STATE_MACHINES.md; a test parses the doc's Mermaid diagrams and compares | `apps/*/transitions.py`, `tests/test_state_machines.py` |
| Services (all writes, `transaction.atomic` + `select_for_update` + audit) | `apps/*/services.py` |
| FX selection, Decimal money, ROUND_HALF_UP per line, applied-rate storage | `apps/core/money.py`, `apps/masterdata/services.py` |
| PDA/FDA lines, versioning, FDA builder, variance, finalize → settlement | `apps/disbursements/services.py` |
| Payments (two-sided record/confirm), settlement math, payment provider abstraction (`PROVIDERS`) | `apps/payments/services.py` |
| Disputes incl. ADJUSTED via FDA revision (EDIT_LINE / CREDIT_LINE), reopen once | `apps/disputes/services.py` |
| PDFs (WeasyPrint), cached per (entity, status); FDA appends invoice PDFs/images | `apps/documents/pdf.py`, `templates/pdf/*.html` |
| Every endpoint in API.md | `config/api_urls.py`, `apps/*/views.py` |
| Management commands: `bootstrap_admin`, `seed_masterdata`, `seed_demo`, `expire_requests` | `apps/adminpanel/management/commands/` |
| Tests (93): permissions, approval gating, scoping, policy layer, every transition table, money/FX, settlement math, disputes, DB invariants, full API lifecycle, PDFs | `backend/tests/` |
| Dockerfile (WeasyPrint system libs) + `docker-compose.yml` (db + backend) | `backend/Dockerfile`, `docker-compose.yml` |

### How to run locally (no Docker)

```bash
brew install postgresql@16 pango && brew services start postgresql@16
psql -d postgres -c "create role maritimer login superuser password 'maritimer'; create database maritimer owner maritimer;"
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib   # macOS only: lets WeasyPrint find pango
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo                  # or: seed_masterdata + bootstrap_admin --email you@gmail.com
.venv/bin/python manage.py runserver
.venv/bin/pytest                                      # 93 passed
curl -H "Authorization: Bearer dev:agent.demo@maritimer.test" localhost:8000/api/v1/dashboard
```

`seed_demo` accepts `--admin-email --owner-email --agent-email --merchant-emails a,b,c` so real Google accounts can demo each role.
It creates: 1 call fully CLOSED (PDA → advance → 4 INR invoices → FDA → one ADJUSTED and one REJECTED dispute → final → refund → paid vendors → rating),
1 DISPUTED, 1 DEPARTED (ready for FDA), 1 IN_PORT with a pending vendor request, 1 PDA_APPROVED with an unconfirmed advance,
1 PDA_SENT, 1 pending port-call request, and 1 merchant applicant awaiting admin approval.

## Clarifications made during implementation

These were needed to implement the docs as written. Each one is implemented, tested and reversible, and none changes the schema.
C1–C3 touch a state machine or FX/money behaviour. They were flagged for Fable review at the end of Phase 2.
On 2026-11-13 the user chose to continue on Opus without that review, so **C1–C3 stand as implemented**.
A future Fable pass may fold them into STATE_MACHINES.md and API.md.

| # | Topic | What the docs say | What was implemented | Why |
|---|---|---|---|---|
| C1 | FDA `discard` | §4b text: "previous version regains is_current=true and ISSUED status is unchanged", but `revise` already moved it to SUPERSEDED and the diagram has no SUPERSEDED → ISSUED edge | Added FDA event `restore` (SUPERSEDED → ISSUED) used only by `discard`. `discard` is refused if the draft carries dispute adjustments (`resolved_in_account`), because voiding it would orphan a RESOLVED dispute's adjustment line | The text and the diagram contradict each other; the test whitelists this one edge (`KNOWN_CLARIFICATIONS`) |
| C2 | FX inverse quotes | "picks the latest rate with as_of ≤ ATD per currency pair" | If only the opposite pair exists (e.g. USD→INR 83.5), the inverse is applied: `fx_rate_id` = that row, `fx_rate_applied` = round(1/rate, 10dp). The newer of direct/inverse wins; a tie prefers direct | Agents usually quote "1 USD = 83.5 INR". Provenance and the exact applied rate are still stored, so FDAs stay reproducible |
| C3 | FDA generate with a missing rate | API.md §9: response includes `warnings` "e.g. invoice currency without a rate" | Missing rates **fail** generation with `400 fx_rate_missing` and `details.missing_pairs`. Warnings are used for non-blocking issues, such as PDA lines with no invoice or no agency fee | Silently omitting an invoice from an FDA would understate what the owner owes |
| C4 | Version numbers after discard | not specified | New versions use max(version)+1, so a VOID draft keeps its number (v1 ISSUED, v2 VOID, v3 DRAFT) | `UNIQUE(port_call, kind, version)` and unique `reference` |
| C5 | Merchant view of a port call | API.md §8: `GET /port-calls/{id}` for any "party" | Merchants get a restricted shape: no owner, PDA/FDA, advance or settlement. PDA/FDA/settlement/dispute endpoints return 403/404 to merchants | Owner↔agent financials are confidential from vendors |
| C6 | Resubmission after rejection | §1 has `resubmit (self)` but API.md has no endpoint | The first onboarding write (`PUT /onboarding/*`, `POST /onboarding/documents`) by a REJECTED user performs `resubmit` (user → ONBOARDING, org → DRAFT), audited | Keeps API.md unchanged |
| C7 | `choose-role` creates the org shell | `organizations.country_code` and `legal_name` are NOT NULL | `POST /auth/choose-role` also accepts optional `legal_name` and `country_code` (defaults: "`<email>` (draft)" and IN). Completeness requires a real legal name | Schema constraints |
| C8 | PDF endpoints | "302 to signed URL" | Default 302 is kept. `?redirect=false` returns `{file: FileRef, cached}` JSON. Previews (DRAFT, open settlement) stream the PDF bytes directly | Browsers can't attach a Bearer header when following a cross-origin redirect, so the SPA needs the JSON form |
| C9 | Dev sign-in | Google sign-in only | `Authorization: Bearer dev:<email>` is accepted only when `AUTH_DEV_TOKENS=true` (dev/test settings). `config.settings.prod` forces it off | Local demo and tests without Firebase |
| C10 | Coverage | not specified | Selecting a port automatically adds its location to the org's locations | Keeps discovery by location and by port consistent |
| C11 | Merchant discovery | API.md has `/agents` but no way for an agent to find merchants for vendor requests (flow 5) | Added `GET /merchants?port_id=&service_category_id=&q=&sort=` (AGENT, ADMIN), same shape as `/agents` | Flow 5 cannot work without it |
| C12 | Reference data during onboarding | API.md §3: master-data reads need an approved user | `GET /countries, /locations, /ports, /service-categories, /cargo-types, /currencies` need only sign-in. FX rates, discovery and everything else still require approval | Onboarding has to list ports and services before the user is approved; this data isn't sensitive |

Smaller additions, none of which changes a contract:
- `GET /dashboard` agent KPIs add `payments_to_confirm`.
- The dispute detail response adds `fda {id, version, status, reference}` after an ADJUSTED resolution, as API.md §12 asks.
- `POST /requests` accepts an optional `expires_at`.
- Agents never see a merchant's DRAFT invoices.
- The `users` table has no `password` or `last_login` columns. They aren't in SCHEMA.md, and the Django admin site is not installed.

## Follow-ups (not blocking)

| # | Item |
|---|---|
| F1 | `docker build` / `docker compose up` were **not run**: Docker is not installed on this machine. Everything was verified natively on macOS with Homebrew Postgres 16, Python 3.14 and Node 24. The production start path (`bin/start.sh` with prod settings and gunicorn) was run locally and works. |
| F6 | Real Google sign-in was not exercised because there's no Firebase project yet. Token verification is covered by tests that mock `verify_id_token`, including the pre-provisioned-user linking. Confirm it with DEPLOY.md §1 and §6. |
| F7 | Nothing has been deployed to Render, Neon, Vercel or R2. That needs your accounts; follow DEPLOY.md step by step. |
| F8 | Owners can read a PDA while it is still DRAFT (API returns it; the UI labels it Draft). Restrict to ISSUED+ if drafts should be private to the agent. |
| F2 | The OpenAPI schema at `/api/schema` generates, but most views are plain `APIView`s without `serializer_class`, so request and response bodies are missing. API.md is the contract. Annotate with `@extend_schema` if typed client generation is wanted. |
| F3 | No background worker: PDFs render synchronously on first request and are then cached. `expire_requests` needs a scheduler (Render cron job) in Phase 4. |
| F4 | Agent→merchant ratings are modelled (`ratings.vendor_request_id`, `merchant_profiles.rating_*`) but `rate()` only allows owner→agent in v1, as specified. |
| F5 | Owner → *any* agent: the request is allowed even if the agent doesn't list that port. `port_served_by_recipient` is recorded in audit metadata, matching STATE_MACHINES §2 "warn only". |

## Open questions (non-blocking; defaults applied in Phase 1)

| # | Question | Default applied |
|---|---|---|
| Q1 | Should the Owner be able to pick an FX rate / contest the rate used, or only the amounts? | Owner can dispute any line, including on FX grounds; rate choice is the agent's. |
| Q2 | Should agents be able to add non-invoice-backed lines to the FDA (e.g. port dues paid directly)? | Yes. The PDF labels these lines "Agent-paid". |
| Q3 | PDA supplement after approval (scope change mid-call)? | Not in v1. |
| Q4 | Dispute window before the agent may finalize? | `FDA_DISPUTE_WINDOW_DAYS=0`. |
| Q5 | Should admin be able to act on behalf of a party? | No, except confirm/cancel payments. |
| Q6 | Multi-currency settlement other than USD? | Column exists; UI offers USD only. |
| Q7 (new) | Demo access: Google-only sign-in means each role needs its own Google account. | `seed_demo --owner-email … --agent-email …` pre-provisions real Gmail addresses. In local dev, the frontend can offer a dev role picker using `dev:` tokens. |

## Phase 3 — what was built (`frontend/`)

- React 18 + Vite + React Router 6 + Firebase JS SDK + lucide icons. No state library: one auth context, `useResource` (fetch with optional polling) and `useAction` (mutations). Everything else is props and derived values.
- `src/styles/tokens.css` holds the palette and spacing tokens from ARCHITECTURE §5; contrast notes are inline. `base.css` is mobile-first:
  - sidebar at 1024px and up, bottom tab bar plus "More" below;
  - tables collapse to cards under 640px, modals become bottom sheets, touch targets are 44px.
- Routing follows `/auth/me.next_step`: sign-in → choose role → onboarding → under review → the role's app. A dev sign-in picker appears only with `VITE_DEV_AUTH=true`.
- Screens for every flow in the brief:
  - Owner: discovery (location → port → agents; sort and filter by rating, name, ID), agent profile, request form, vessels, dashboard.
  - Agent: pipeline kanban with KPIs and attention list, PDA/FDA line editor (server-computed USD), vendor requests, invoice review, FX rates.
  - Merchant: dashboard, invoice creation with file upload.
  - Shared: port-call page with role-aware tabs (Overview, PDA, Vendors, Invoices, FDA with variance, Payments and settlement, Disputes, Chat, Documents, Timeline), dispute page with history and resolve/reject/reopen, chat polling every 5 s, PDFs.
  - Admin: approvals with document review, organizations (create plus pre-approved users), master data plus request policies, audit log.
- Buttons are driven by `allowed_actions` from the API; the server re-checks every action.
- Verified by:
  - `vite build` and `vitest`.
  - A Playwright crawl of 66 screens (4 roles × desktop/phone): no runtime errors and no horizontal overflow.
  - Scripted click-throughs: onboarding → admin approval; PDA approve → advance → confirm; invoice accept → FDA generate/issue → owner dispute → agent adjust → re-issue → finalize → settlement; merchant accepts and invoices with a file on a phone; chat.

## Phase 4 — what was built

- `docker-compose.yml`: db, backend and frontend.
- `backend/bin/start.sh`: migrate, seed master data, optional admin bootstrap, gunicorn.
- `render.yaml`: Render blueprint, Docker, free plan, health check.
- `frontend/vercel.json`: SPA rewrites and caching headers.
- `frontend/Dockerfile` for local development.
- Production settings: health-check redirect exemption and automatic Render hostname.
- Docs:
  - `README.md`: overview, architecture, local setup, demo accounts, tests.
  - `DEPLOY.md`: exact steps for Firebase, Neon, R2, Render and Vercel; environment variable reference; CORS and security checklist; troubleshooting.
  - `WALKTHROUGH.md`: end-to-end checklist per role.

## What's next

1. Deploy following DEPLOY.md (F7) and run WALKTHROUGH.md against production, including real Google sign-in (F6).
2. Optional Fable pass to fold clarifications C1–C12 into the design docs.
3. Optional hardening: `@extend_schema` for typed OpenAPI (F2), hide draft PDAs from owners (F8), add a Render cron job for `expire_requests` (F3).

## Design changes requested

None beyond the clarifications table above.

## Done log

- 2026-11-13 — Phase 1 docs written (ARCHITECTURE.md, SCHEMA.md, API.md, STATE_MACHINES.md).
- 2026-11-13 — User approved Phase 1 and started Phase 2.
- 2026-11-13 — Phase 2 backend complete: all endpoints and services, demo seed runs end to end. Clarifications C1–C10 recorded above.
- 2026-11-13 — User continued on Opus without the Fable review; C1–C3 accepted as implemented.
- 2026-11-13 — Phase 3 frontend complete. Added C11 (merchant discovery) and C12 (reference data during onboarding). Backend at 96 tests.
- 2026-11-13 — Phase 4 deployment configs and docs complete. Not yet deployed.
