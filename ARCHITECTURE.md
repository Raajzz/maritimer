# ARCHITECTURE.md — Maritimer (Port-Call Management)

Status: Phase 1 design. Companion docs: `SCHEMA.md`, `API.md`, `STATE_MACHINES.md`, `PROGRESS.md`.
Anything not written in these files is not decided. When implementation finds a conflict between
code and these docs, the docs win unless PROGRESS.md records an agreed change.

---

## 1. What the system does (one paragraph)

A shipowner (Owner) picks a Port Agent (Agent) serving a port and sends a port-call request. On
acceptance a **Port Call** is created: the aggregate that every other record hangs off. The Agent
issues a **PDA** (proforma estimate, USD), the Owner approves it and records an **advance**. The Agent
sources local **Merchants** (vendors) via vendor-service requests, who upload **INR invoices**. After
departure the Agent generates an **FDA** from accepted invoices plus the agency fee, converted to USD
at recorded **FX rates**, with per-line **variance** vs the PDA. The Owner may **dispute** FDA lines;
the FDA cannot be finalized while any dispute is open. Finalizing creates a **Settlement** (refund to
Owner or balance due from Owner) tracked to closure. PDA, FDA and settlement statements are generated
as **PDFs**. **Chat** runs Owner↔Agent (per port call) and Agent↔Merchant (per vendor request).
Owners **rate** agents after close. **Admin** verifies users/companies and manages master data. Every
state transition is a server-side service function running in a DB transaction and written to an
append-only **audit log**.

---

## 2. System components

```
┌──────────────────────────┐    Firebase ID token (Bearer)    ┌────────────────────────────┐
│  React SPA (Vite)        │ ───────────────────────────────▶ │ Django + DRF (gunicorn)    │
│  Firebase JS SDK (Google)│ ◀─────────────────────────────── │ firebase-admin verifies    │
│  React Router, fetch     │          JSON over HTTPS         │ token → local User         │
└──────────────────────────┘                                  │ services/ (transitions)    │
        Vercel                                                │ WeasyPrint (PDF)           │
                                                              └─────┬──────────────┬───────┘
                                                                    │              │
                                                           ┌────────▼──────┐  ┌────▼──────────────┐
                                                           │ PostgreSQL 16 │  │ S3-compatible     │
                                                           │ (Neon)        │  │ object storage    │
                                                           └───────────────┘  │ (Cloudflare R2)   │
                                                                              └───────────────────┘
```

| Concern | Choice | Why |
|---|---|---|
| Frontend | React 18, functional components, Vite, React Router v6 | Required. Vite for fast builds and simple static deploy. |
| Data fetching | Small `api.js` wrapper around `fetch` + one `useQuery`-style hook (`useResource`) with polling option | "Lightweight data-fetching approach". No Redux/TanStack. State lives in the URL and server; components derive from props. |
| Auth | Firebase Auth, Google provider only | Required. Backend never trusts client role claims; Django is source of truth. |
| Backend | Django 5 + DRF, Python 3.12 | Required. |
| DB | PostgreSQL 16 | Required. NUMERIC for all money. |
| Files | `django-storages` S3 backend → Cloudflare R2 in prod, `FileSystemStorage` in dev | S3-compatible, free 10 GB, zero egress fees. |
| PDF | WeasyPrint from Django templates | HTML/CSS templates shared with the frontend's design tokens. |
| Background work | None in v1 (PDF generated synchronously on demand, cached by version) | Avoids a worker + broker on a free tier. Design keeps a `generated_documents` table so a worker can be added later. |
| Realtime | Polling (chat every 5 s while thread open; dashboards every 60 s) | Acceptable per spec; no websockets infra. |

---

## 3. Backend architecture

### 3.1 Django apps (bounded contexts)

```
backend/
  config/            settings (base/dev/prod), urls, wsgi, asgi
  apps/
    core/            BaseModel (created_at/updated_at), Money helpers, enums, exceptions, audit
    accounts/        User, Organization, profiles, memberships, verification documents, onboarding
    masterdata/      Country, Location, Port, ServiceCategory, Currency, CargoType, FxRate
    vessels/         Vessel
    requests/        Request (generic), RequestRolePolicy, typed detail tables, policy layer
    portcalls/       PortCall, transitions, timeline
    disbursements/   DisbursementAccount (PDA/FDA), LineItem, FDA builder, variance
    invoices/        VendorInvoice (+ lines)
    payments/        Payment, Settlement, payment provider abstraction
    disputes/        Dispute, DisputeEvent
    documents/       StoredFile, GeneratedDocument, PDF rendering
    chat/            ChatThread, Participant, Message, ReadReceipt
    ratings/         Rating
    dashboards/      read-only aggregate queries per role
    adminpanel/      admin-only endpoints (approvals, master data, bootstrap)
```

Each app has: `models.py`, `services.py` (all writes), `selectors.py` (reads), `serializers.py`,
`views.py`, `permissions.py`, `urls.py`, `tests/`.

### 3.2 Service layer rule (non-negotiable)

Views never call `.save()` on domain models. Every write goes through a function in `services.py`:

```python
@transaction.atomic
def issue_pda(*, actor: User, account: DisbursementAccount) -> DisbursementAccount:
    check_permission(actor, "disbursement.issue", account)        # raises PermissionDenied
    account = DisbursementAccount.objects.select_for_update().get(pk=account.pk)
    assert_transition(account, "ISSUED")                           # STATE_MACHINES.md, raises InvalidTransition
    ...
    audit(actor=actor, action="pda.issued", entity=account, port_call=account.port_call,
          from_state="DRAFT", to_state="ISSUED")
    return account
```

- `select_for_update()` on the aggregate row (port call, account, dispute) before transitions.
- Transition tables live in one module per state machine (`<app>/transitions.py`) and mirror
  STATE_MACHINES.md exactly; tests assert the table equals the doc.
- Audit entries are written in the same transaction (`audit_log` table, append-only).

### 3.3 Authentication & authorization pipeline

1. `FirebaseAuthentication` (DRF auth class): reads `Authorization: Bearer <idToken>`, verifies with
   `firebase_admin.auth.verify_id_token` (checks signature, expiry, project, revocation optional).
2. Maps to `User` by `firebase_uid`; if none, by verified `email` (admin pre-provisioned accounts),
   setting `firebase_uid`; otherwise creates `User(status=NEW)`. Updates `display_name`, `photo_url`,
   `last_login_at`.
3. Permission classes, applied in order on every view:
   - `IsAuthenticated`
   - `IsApproved` — `user.status == APPROVED` and (user is ADMIN or `user.organization.verification_status == APPROVED`). Only the `auth/*` and `onboarding/*` endpoints opt out of this.
   - `HasRole(...)` — role gate per endpoint, see API.md matrix.
   - Object-level scoping in selectors: every queryset is filtered by the actor's organization
     (owner sees own port calls, agent sees calls where they are the agent, merchant sees calls
     where they have an accepted vendor request or an invoice). There is no "list everything" path
     for non-admins.
4. Request directionality is a **policy table** (`request_role_policies`), checked in
   `requests/policy.py`. Enabling Merchant→Agent requests later is one row flip.

### 3.4 Money and FX

- All amounts: `DecimalField(max_digits=18, decimal_places=2)` + `currency_code` FK on the same row.
  Never `float`. Never a bare amount column without a currency.
- Rates: `DecimalField(max_digits=20, decimal_places=10)`. Convention: `rate` = units of
  `quote_currency` per 1 unit of `base_currency`; `amount_quote = amount_base × rate`.
  For INR→USD: base=INR, quote=USD, rate≈0.0120.
- Rounding: `ROUND_HALF_UP` to the currency's `minor_units` (from `currencies`), applied once per
  line, then totals are sums of rounded lines (so the PDF foots exactly).
- Every converted line stores `fx_rate_id` (provenance) **and** `fx_rate_applied` (the exact decimal
  used), so a regenerated FDA PDF reproduces the original numbers even if rate rows are later added.
  `fx_rates` rows are immutable (no update endpoint; corrections are new rows).
- FX rate sourcing in v1: Admin/Agent enters rates manually (`source=MANUAL`) and an optional
  management command pulls daily rates from a provider (`source=<PROVIDER>`); the FDA builder picks
  the latest rate with `as_of <= port_call.atd` per currency pair, and the agent may override per
  FDA with an explicit rate id. Selection rule is recorded in audit metadata.
- Settlement math (all USD, Decimal):
  `advance_total = Σ CONFIRMED payments kind=ADVANCE`;
  `balance = fda_total − advance_total`;
  `balance > 0 → BALANCE_DUE (owner pays)`, `< 0 → REFUND_DUE (agent refunds |balance|)`, `= 0 → NIL`.
  `outstanding = |balance| − Σ CONFIRMED payments(kind ∈ {BALANCE, REFUND} on this settlement)`;
  settlement closes when `outstanding == 0`.

### 3.5 Documents / PDF

- `documents/pdf.py` renders Django templates (`templates/pdf/pda.html`, `fda.html`,
  `settlement.html`) with WeasyPrint. Templates use the same CSS tokens as the SPA.
- Generation is on demand (`GET .../pdf`): if a `generated_documents` row exists for the exact
  (entity, version, status) tuple, return its file; otherwise render, store, record, return.
  Issued/Final documents are therefore immutable artifacts.
- FDA PDF appends a "Supporting invoices" section listing each vendor invoice with a signed link;
  if the invoice file is a PDF it is merged as an appendix (pypdf) — attachment, else link.
- Downloads return a 302 to a short-lived signed URL (R2/S3) in prod, or stream from disk in dev.

### 3.6 Storage

- `StoredFile` row per object: key, bucket, content type, size, sha256, uploader. Entities reference
  files by FK; no polymorphic attachments table.
- Uploads go through Django (`POST /files`, multipart, ≤ 15 MB, allow-list of content types) in v1.
  Presigned direct-to-R2 uploads are a drop-in later (same `StoredFile` row).

### 3.7 Audit log

`audit_log(actor_user_id, actor_role, action, entity_type, entity_id, port_call_id, from_state,
to_state, changes JSONB, metadata JSONB, ip, created_at)`. Written by `core.audit.audit()` inside the
service transaction. The DB role used by the app has no UPDATE/DELETE on this table in prod (set in
the migration via `RunSQL` guarded by env). `GET /port-calls/{id}/timeline` reads from it.

---

## 4. Frontend architecture

```
frontend/src/
  main.jsx, App.jsx                     Router + providers (AuthProvider only)
  lib/api.js                            fetch wrapper: base URL, bearer token, error envelope, JSON
  lib/firebase.js                       Firebase init, signInWithPopup(GoogleAuthProvider), onIdTokenChanged
  lib/money.js                          format(amount, currency) using Intl; variance helpers (pure fns)
  hooks/useAuth.js                      current user/me (one context, the only global state)
  hooks/useResource.js                  {data, error, loading, refetch} with optional pollMs
  styles/tokens.css                     design tokens (CSS variables) — see §5
  styles/base.css                       reset, typography, utilities
  components/ui/                        Button, Card, Badge(status), Table(responsive→cards), Form fields,
                                        Modal/Sheet (bottom sheet on mobile), Tabs, EmptyState, Money
  components/layout/                    AppShell (sidebar ≥1024px / bottom tab bar <1024px), TopBar, PageHeader
  routes/                               route components by role
    auth/      SignIn, ChooseRole, Onboarding(Owner|Agent|Merchant), PendingReview
    owner/     Dashboard, Discovery(Agents), AgentProfile, Vessels, NewRequest, PortCall, PDAReview,
               FDAReview(+dispute), Payments, Rate
    agent/     Dashboard(pipeline), Requests, PortCall, PDAEditor, VendorRequests, Invoices,
               FDAEditor, Disputes, Settlement
    merchant/  Dashboard, Requests, InvoiceUpload, Invoices
    admin/     Dashboard, Approvals, Users, Organizations, MasterData(Locations, Ports, Services, FX)
    shared/    ChatPanel, Timeline, DocumentList, NotFound
```

Rules: hooks only for auth context, data fetching, and genuinely local UI state (open sheet,
form draft). Everything else is props and derived values. Role-based routing: `RequireRole` wrapper
reads `useAuth().me.role`/`status` and redirects (`NEW → /choose-role`, `ONBOARDING → /onboarding`,
`PENDING_REVIEW|REJECTED → /pending`, `APPROVED → /<role>`). The backend enforces the same
rules; the frontend only routes.

---

## 5. Design brief (for Phase 3)

Reference kits could not be fetched (Figma requires auth; Basic UX page is a wireframe-kit portfolio
without specs). Follow this written brief instead.

**Style:** clean, minimal, generous whitespace, card-based layouts, clear typography, simple outline
iconography (Lucide icons, 1.5 px stroke). CRM-dashboard patterns: left sidebar nav on desktop,
top bar with page title + primary action, KPI tiles row, pipeline/kanban for the agent board,
dense but readable tables that collapse to cards on mobile.

**Tokens (`styles/tokens.css`):**

```css
:root {
  --color-primary: #0B3C5D;      /* nav, headings, primary buttons */
  --color-accent:  #0E8A9A;      /* links, active states, secondary actions */
  --color-cta:     #FF6B1A;      /* primary CTA + alerts needing action */
  --color-success: #2E9E5B;
  --color-error:   #D93636;
  --color-bg:      #F4F7FA;
  --color-text:    #1A2530;
  --color-surface: #FFFFFF;
  --color-muted:   #5B6B7A;      /* secondary text, AA on white (6.1:1) */
  --color-border:  #DDE4EB;
  --color-primary-soft: #E6EEF4; --color-accent-soft: #E3F3F5;
  --color-cta-soft: #FFEDE3;     --color-success-soft: #E6F5EC; --color-error-soft: #FBE7E7;
  --font-sans: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-mono: ui-monospace, "SF Mono", Menlo, monospace;   /* money, references */
  --text-xs: 0.75rem; --text-sm: 0.875rem; --text-md: 1rem; --text-lg: 1.125rem;
  --text-xl: 1.375rem; --text-2xl: 1.75rem;
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px; --space-6: 24px; --space-8: 32px;
  --radius-sm: 6px; --radius-md: 10px; --radius-lg: 14px;
  --shadow-card: 0 1px 2px rgba(26,37,48,.06), 0 1px 6px rgba(26,37,48,.04);
  --sidebar-w: 248px; --topbar-h: 56px; --tabbar-h: 60px;
}
```

**Contrast (WCAG AA, computed):** text `#1A2530` on `#F4F7FA` ≈ 14:1; white on primary `#0B3C5D`
≈ 11:1; **white on accent `#0E8A9A` is only 4.1:1, so solid accent buttons use `#0B7380` (5.6:1) and
accent text uses `#0A6570`**; **white on CTA `#FF6B1A` is only ≈ 2.9:1, so CTA buttons use text `#1A2530`
on `#FF6B1A` (5.45:1)** or the CTA color is used for borders/icons with dark text.
A dark theme (toggle: light / dark / system) is defined in `frontend/src/styles/tokens.css` with
every pair ≥ 6.8:1. Error `#D93636` on white ≈ 4.9:1 (OK). Success `#2E9E5B` on white ≈
3.6:1 → use for icons/badges with dark text, not for body text.

**Status badge mapping:** neutral (grey) = draft/pending; accent = in progress (PDA sent, in port);
cta = needs your action (approve PDA, open dispute, confirm payment); success = approved/settled/
closed; error = declined/rejected/cancelled.

**Responsive:** mobile-first CSS; breakpoints 640 / 1024 px. `<1024`: bottom tab bar (4 primary
destinations + "More"), full-width cards, tables become stacked key/value cards, actions in a bottom
sheet. `≥1024`: fixed sidebar, 12-col grid, max content width 1280 px. Touch targets ≥ 44 px.

---

## 6. Deployment (decision)

**Chosen stack:** Backend on **Render** (Docker web service, free tier) · Postgres on **Neon** (free
tier) · Frontend on **Vercel** (free) · Files on **Cloudflare R2** (free 10 GB).

Why this and not the alternatives:
- Render runs a Dockerfile on the free tier, which we need because WeasyPrint requires system
  libraries (pango, cairo, gdk-pixbuf) that buildpacks don't ship. Railway also works but has no
  permanent free tier (trial credit → $5/mo).
- Render's own free Postgres is time-limited (expires after 30 days on the free plan); Neon's free
  tier is persistent, has branching for previews, and is plain Postgres 16. If you prefer one
  dashboard, Render Postgres at ~$7/mo is a drop-in: only `DATABASE_URL` changes.
- Vercel serves the Vite build globally with SPA rewrites and preview deploys per branch.
- R2 is S3-API compatible (works with `django-storages` S3 backend unchanged), free egress, so
  PDF downloads cost nothing.
- Known trade-off: Render free web services spin down after 15 min idle (first request ~30 s). A
  free cron ping (e.g. cron-job.org) or Render's $7 starter removes it. Documented in Phase 4.

Local dev: `docker-compose` with `db` (postgres:16), `backend` (Django runserver, FileSystemStorage,
Firebase service account mounted), `frontend` (Vite dev server). Phase 4 writes the files and
step-by-step instructions, env var lists, Firebase setup, CORS, migrations, seed, bootstrap-admin.

---

## 7. Security notes

- No endpoint relies on client-provided role/org; everything derives from the token → User → Org.
- Approval enforced by the `IsApproved` permission on every router except `auth` and `onboarding`.
- Object scoping in selectors (not just permission classes) so list endpoints can't leak.
- Uploads: content-type allow-list (pdf, png, jpg, webp), size cap, random storage keys, served via
  signed URLs only.
- CORS restricted to the Vercel domain(s); CSRF not used (token auth, no cookies).
- Secrets only via environment (Firebase service account JSON as base64 env var).
- Rate limiting: DRF throttle on chat message POST and file upload.

---

## 8. Future-proofing already in the schema

- Any-role-to-any-role requests: policy table row flip.
- Many users per organization: drop one unique constraint (`organization_members.user_id`).
- Agents rating merchants: `ratings.ratee_organization_id` is generic; `vendor_request_id` context column exists.
- AI document verification: `verification_documents.review_source` (HUMAN | AUTOMATED) + `review_metadata JSONB`.
- Real payment gateway: `payments.provider`, `provider_reference`, `provider_payload`.
- Background jobs: `generated_documents` is a job-friendly table; add Celery/RQ without schema change.
